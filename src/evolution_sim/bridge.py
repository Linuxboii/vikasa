"""Local, read-only-by-default HTTP bridge for the Godot 4 living-biome client."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EVENT_KINDS, EnvironmentEvent

DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 32_768


def _next_simulation_deadline(deadline: float, tick_interval: float, now: float) -> float:
    """Schedule one tick without carrying an unbounded catch-up backlog."""
    planned = deadline + tick_interval
    if now > planned:
        return now + min(0.002, tick_interval * 0.1)
    return planned


class _BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], bridge: GodotSimulationServer) -> None:
        self.bridge = bridge
        super().__init__(address, _BridgeHandler)


class _BridgeHandler(BaseHTTPRequestHandler):
    server: _BridgeServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _reply(self, status: int, value: dict[str, Any]) -> None:
        payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._reply(200, {"ok": True, "service": "vikasa-godot-bridge"})
        elif self.path == "/state":
            self._reply(200, self.server.bridge.state())
        else:
            self._reply(404, {"error": "Unknown endpoint"})

    def do_POST(self) -> None:
        if self.path != "/command":
            self._reply(404, {"error": "Unknown endpoint"})
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > MAX_REQUEST_BYTES:
            self._reply(413, {"error": "Command body must be between 1 and 32768 bytes"})
            return
        try:
            command = json.loads(self.rfile.read(size))
            if not isinstance(command, dict):
                raise ValueError("Command must be a JSON object")
            result = self.server.bridge.command(command)
            self._reply(200, result)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._reply(400, {"error": str(exc)})


class GodotSimulationServer:
    """Own the Python engine while the Godot client controls time and presentation."""

    def __init__(
        self, config: SimulationConfig, *, seed: int = 2026, port: int = DEFAULT_PORT
    ) -> None:
        self.engine = SimulationEngine(config, seed=seed)
        self.port = port
        self.lock = threading.RLock()
        self.paused = False
        self.ticks_per_second = 48.0
        self._tick_times: deque[float] = deque(maxlen=256)
        self._published_state: dict[str, Any] | None = None
        self.running = True
        self._stop = threading.Event()
        self._http = _BridgeServer(("127.0.0.1", port), self)
        self._http_thread = threading.Thread(
            target=self._http.serve_forever, name="vikasa-godot-http", daemon=True
        )
        self._sim_thread = threading.Thread(
            target=self._run_simulation, name="vikasa-simulation", daemon=True
        )

    def start(self) -> None:
        self._published_state = self._build_state()
        self._http_thread.start()
        self._sim_thread.start()

    def stop(self) -> None:
        self.running = False
        self._stop.set()
        self._http.shutdown()
        self._http.server_close()
        self._http_thread.join(timeout=2.0)
        self._sim_thread.join(timeout=2.0)

    def _run_simulation(self) -> None:
        deadline = time.monotonic()
        published_at = deadline
        while not self._stop.wait(0.002):
            if self.paused:
                deadline = time.monotonic()
                continue
            now = time.monotonic()
            tick_interval = 1.0 / self.ticks_per_second
            if now >= deadline:
                with self.lock:
                    self.engine.step(1)
                    self._tick_times.append(time.monotonic())
                    if time.monotonic() - published_at >= 0.16:
                        self._published_state = self._build_state()
                        published_at = time.monotonic()
                deadline = _next_simulation_deadline(
                    deadline, tick_interval, time.monotonic()
                )

    def state(self) -> dict[str, Any]:
        # HTTP reads a completed immutable-by-convention publication; a slow
        # engine tick cannot make a GUI poll queue behind the simulation lock.
        if self._sim_thread.is_alive() and self._published_state is not None:
            return self._published_state
        return self._build_state()

    def _build_state(self) -> dict[str, Any]:
        with self.lock:
            engine = self.engine
            snapshot_by_id = {item.id: item for item in engine.snapshot().creatures}
            creatures = []
            for item in (engine.creatures[key] for key in sorted(engine.creatures)):
                view = snapshot_by_id[item.id]
                creatures.append(
                    {
                        "id": item.id,
                        "position": [float(item.position[0]), float(item.position[1])],
                        "velocity": [float(item.velocity[0]), float(item.velocity[1])],
                        "age": item.age,
                        "energy": round(item.energy, 3),
                        "energy_ratio": max(
                            0.0, min(1.0, item.energy / engine.config.energy.maximum)
                        ),
                        "hunger": round(item.hunger, 3),
                        "satisfaction": round(item.satisfaction, 3),
                        "satisfaction_vector": {
                            "energy": round(item.satisfaction_vector[0], 3),
                            "offspring": round(item.satisfaction_vector[1], 3),
                            "food": round(item.satisfaction_vector[2], 3),
                            "fights": round(item.satisfaction_vector[3], 3),
                        },
                        "size": item.genome.values[0],
                        "speed": item.genome.values[1],
                        "perception": item.genome.values[2],
                        "metabolism": item.genome.values[3],
                        "aggression": item.temperament.aggression,
                        "resilience": item.temperament.resilience,
                        "sociability": item.temperament.sociability,
                        "alpha": item.alpha,
                        "fights_won": item.fights_won,
                        "fights_lost": item.fights_lost,
                        "offspring": item.offspring_count,
                        "food_acquired": round(item.food_acquired, 2),
                        "injury": round(item.injury, 3),
                        "starvation_ticks": item.starvation_ticks,
                        "belief_id": item.belief_id,
                        "parents": list(item.parents) if item.parents else [],
                        "behavior": view.behavior,
                        "behavior_reason": view.behavior_reason[:240],
                        "behavior_started_tick": view.behavior_started_tick,
                        "drives": dict(
                            zip(
                                (
                                    "survival",
                                    "foraging",
                                    "mating",
                                    "offspring_care",
                                    "danger_avoidance",
                                    "territory",
                                ),
                                view.drives,
                                strict=True,
                            )
                        ),
                        "behavior_scores": {
                            action: float(score) for action, score in view.behavior_scores
                        },
                        "target_kind": view.target_kind,
                        "target_id": view.target_id,
                        "target_position": (
                            [float(value) for value in view.target_position]
                            if view.target_position is not None else None
                        ),
                        "home_range": {
                            "center": list(view.home_center),
                            "radius": view.home_radius,
                        },
                        "dependent_ids": list(view.dependent_ids),
                    }
                )
            resources = [
                {
                    "id": item.id,
                    "position": [float(item.position[0]), float(item.position[1])],
                    "energy": round(item.energy, 2),
                }
                for item in (engine.resources[key] for key in sorted(engine.resources))
            ]
            traditions = []
            for item in engine.culture.traditions:
                followers = [key for key in item.followers if key in engine.creatures]
                traditions.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "signal": item.signal,
                        "ritual": item.ritual,
                        "founder_id": item.founder_id,
                        "founded_tick": item.founded_tick,
                        "followers": len(followers),
                        "ritual_count": item.ritual_count,
                        "cohesion": round(len(followers) / max(1, len(engine.creatures)), 3),
                    }
                )
            mean_satisfaction = sum(item.satisfaction for item in engine.creatures.values()) / max(
                1, len(engine.creatures)
            )
            starving = sum(item.starvation_ticks > 0 for item in engine.creatures.values())
            events = [item.to_dict() for item in engine.environment.active_events]
            chronicles = (engine.culture.chronicle + engine.recent_events)[-40:]
            return {
                "version": 1,
                "seed": engine.seed,
                "tick": engine.tick,
                "paused": self.paused,
                "ticks_per_second": self.ticks_per_second,
                "actual_ticks_per_second": (
                    round((len(self._tick_times) - 1)
                          / max(0.001, self._tick_times[-1] - self._tick_times[0]), 1)
                    if len(self._tick_times) > 1 and not self.paused else 0.0
                ),
                "world": {
                    "width": engine.config.world.width,
                    "height": engine.config.world.height,
                    "maximum_age": engine.config.maximum_age,
                    "maximum_energy": engine.config.energy.maximum,
                },
                "population": len(creatures),
                "food_count": len(resources),
                "births": engine.tick_births,
                "deaths": engine.tick_deaths,
                "total_births": engine.total_births,
                "total_deaths": engine.total_deaths,
                "development": engine.metrics.development(engine),
                "mean_satisfaction": round(mean_satisfaction, 3),
                "alpha_count": sum(item.alpha for item in engine.creatures.values()),
                "starving_count": starving,
                "fight_count": sum(item.fights_won for item in engine.creatures.values()),
                "death_causes": dict(engine.death_causes),
                "environment": {
                    "season": engine.environment.season,
                    "temperature": engine.environment.temperature,
                    "rainfall": engine.environment.rainfall,
                    "food_pressure": engine.environment.food_multiplier,
                    "seasonal_productivity": engine.environment.seasonal_food_multiplier,
                    "metabolic_pressure": engine.environment.metabolic_multiplier,
                    "health_pressure": engine.environment.health_pressure,
                    "active_events": events,
                },
                "creatures": creatures,
                "resources": resources,
                "habitat": ({"summary": engine.habitat.summary(),
                             "columns": engine.config.ecology.columns,
                             "rows": engine.config.ecology.rows,
                             "capacity": engine.config.ecology.capacity,
                             "biomass": engine.habitat.biomass.tolist(),
                             "water": engine.habitat.water.tolist()}
                            if engine.habitat is not None else None),
                "fights": list(engine.combat_events),
                "external_food_energy": engine.external_food_energy,
                "interventions": list(engine.interventions[-24:]),
                "traditions": traditions,
                "chronicle": chronicles,
                "history": [sample.to_row() for sample in engine.metrics.samples[-240:]],
                "birth_history": list(engine.metrics.birth_cohorts[-180:]),
                "weather_history": list(engine.environment.history[-24:]),
            }

    def command(self, value: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return self._apply_command(value)

    def _apply_command(self, value: dict[str, Any]) -> dict[str, Any]:
        action = value.get("action")
        if action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
            self._tick_times.clear()
        elif action == "restart":
            self.engine = SimulationEngine(self.engine.config, seed=self.engine.seed)
            self._tick_times.clear()
            self.paused = False
        elif action == "speed":
            speed = float(value.get("ticks_per_second", 48))
            if not 0.25 <= speed <= 120.0:
                raise ValueError("ticks_per_second must be between 0.25 and 120")
            self.ticks_per_second = speed
            self._tick_times.clear()
        elif action == "step":
            count = int(value.get("count", 1))
            if not 1 <= count <= 100:
                raise ValueError("step count must be between 1 and 100")
            with self.lock:
                self.engine.step(count)
        elif action == "weather":
            kind = str(value.get("kind", ""))
            if kind not in EVENT_KINDS:
                raise ValueError(f"unsupported environmental event: {kind}")
            intensity = float(value.get("intensity", 1.0))
            duration = int(value.get("duration", 40))
            if not 0.05 <= intensity <= 4.0 or not 1 <= duration <= 20_000:
                raise ValueError("weather intensity or duration is outside its safe range")
            with self.lock:
                event = EnvironmentEvent(
                    kind, self.engine.tick + 1, duration, intensity, label="Godot field control"
                )
                self.engine.environment.schedule(event)
                self.engine.recent_events.append(
                    {
                        "tick": self.engine.tick,
                        "kind": "weather",
                        "text": f"Field study scheduled {kind} pressure for {duration} ticks.",
                        "creature_id": None,
                    }
                )
        elif action == "food":
            x = float(value.get("x", 0.5))
            y = float(value.get("y", 0.5))
            energy = float(value.get("energy", self.engine.config.resources.energy_value))
            with self.lock:
                if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                    raise ValueError("food coordinates must be normalized to zero through one")
                if len(self.engine.resources) >= self.engine.config.resources.maximum_count:
                    raise ValueError("the configured food-patch limit has been reached")
                if energy <= 0.0 or energy > self.engine.config.energy.maximum:
                    raise ValueError("food energy is outside the valid range")
                self.engine.add_food(
                    np.array([x * self.engine.config.world.width,
                              y * self.engine.config.world.height]),
                    energy)
        else:
            raise ValueError("action must be pause, resume, restart, speed, step, weather, or food")
        self._published_state = self._build_state()
        return {"ok": True, "action": action}


def _godot_binary(explicit: str | None) -> str:
    candidates = [explicit, os.environ.get("VIKASA_GODOT_BINARY")]
    candidates.extend([shutil.which("godot4"), shutil.which("godot")])
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_packages = (
            Path(local_app_data)
            / "Microsoft"
            / "WinGet"
            / "Packages"
        )
        winget_binaries = list(
            winget_packages.glob(
                "GodotEngine.GodotEngine_*/Godot_v*-stable_win64.exe"
            )
        )

        def version_key(path: Path) -> tuple[int, ...]:
            match = re.search(r"Godot_v([0-9.]+)-stable", path.name)
            return tuple(int(part) for part in match.group(1).split(".")) if match else ()

        candidates.extend(
            str(path)
            for path in sorted(winget_binaries, key=version_key, reverse=True)
        )
    candidates.extend(
        [
            str(
                Path(__file__).resolve().parents[2]
                / "tmp"
                / "godot-runtime"
                / "Godot_v4.7.2-stable_win64.exe"
            ),
            r"C:\Program Files\Godot\Godot_v4.4-stable_win64.exe",
            r"C:\Program Files\Godot\Godot_v4.5-stable_win64.exe",
        ]
    )
    for candidate in candidates:
        if candidate and (Path(candidate).is_file() or shutil.which(candidate)):
            return str(candidate)
    raise RuntimeError(
        "Godot 4 was not found. Set VIKASA_GODOT_BINARY or pass "
        "--godot-path to the Godot 4 executable."
    )


def launch_godot(
    config: SimulationConfig,
    *,
    seed: int,
    godot_path: str | None = None,
    project_path: Path | None = None,
) -> int:
    binary = _godot_binary(godot_path)
    project = project_path or Path(__file__).resolve().parents[2] / "godot"
    if not (project / "project.godot").is_file():
        raise RuntimeError(f"Godot project not found: {project}")
    bridge = GodotSimulationServer(config, seed=seed)
    try:
        bridge.start()
        time.sleep(0.15)
        process = subprocess.Popen([binary, "--path", str(project)])
        return process.wait()
    finally:
        bridge.stop()


def serve_bridge(config: SimulationConfig, *, seed: int, port: int = DEFAULT_PORT) -> None:
    bridge = GodotSimulationServer(config, seed=seed, port=port)
    bridge.start()
    print(f"Vikasa local 3D bridge ready at http://127.0.0.1:{port}/state")
    try:
        while bridge.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


def run_bridge():
    """Run the bridge server in a separate thread for testing purposes."""
    config = SimulationConfig()
    bridge_thread = threading.Thread(
        target=serve_bridge,
        args=(config,),
        kwargs={"seed": 2026, "port": DEFAULT_PORT},
        daemon=True,
    )
    bridge_thread.start()
    return bridge_thread
