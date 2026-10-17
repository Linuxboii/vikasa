"""Local, read-only-by-default HTTP bridge for the Godot 4 living-biome client."""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import numpy as np

from evolution_sim.analytics.trait_space import population_genetics
from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.behavior import ActionName
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EVENT_KINDS, EnvironmentEvent

DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 32_768

# Compact presentation stream. The JSON /state document carries explanations and
# history; /frame carries only what the renderer needs every few hundredths of a
# second, as little-endian float32 so the client can decode it without parsing.
FRAME_VERSION = 2.0
FRAME_HEADER = 24
CREATURE_STRIDE = 18
RESOURCE_STRIDE = 4
BEHAVIOR_CODES = tuple(action.value for action in ActionName)
WEATHER_CODES = (
    "drought", "abundance", "heat", "cold", "storm", "flood", "wildfire", "disease",
    "redistribute",
)
if set(WEATHER_CODES) != set(EVENT_KINDS):  # pragma: no cover - import-time contract
    raise RuntimeError("bridge weather codes must cover every environmental event kind")
FLAG_ALPHA = 1
FLAG_INJURED = 2
FLAG_YOUNG = 4
FLAG_STARVING = 8
FLAG_BELIEVER = 16
FRAME_INTERVAL = 0.033
STATE_INTERVAL = 0.4
FEED_LENGTH = 240
MAX_FOOD_BURST = 24
# The GUI's slim document: what legends, milestones and captions need for every
# animal. Full detail (drives, utilities, genome…) is sent only for the focus.
LITE_CREATURE_FIELDS = (
    "id", "age", "generation", "founder", "offspring", "fights_won", "food_acquired",
    "behavior", "behavior_reason", "alpha",
)
# Append-only series the client merges itself; only rows newer than its cursor
# travel. Re-sending them whole cost ~95% of every document.
HISTORY_KEYS = ("history", "birth_history")


def _next_simulation_deadline(deadline: float, tick_interval: float, now: float) -> float:
    """Schedule one tick without carrying an unbounded catch-up backlog."""
    planned = deadline + tick_interval
    if now > planned:
        return now + min(0.002, tick_interval * 0.1)
    return planned


def _encode(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _lite(state: dict[str, Any]) -> dict[str, Any]:
    lite = {key: value for key, value in state.items()
            if key != "creatures" and key not in HISTORY_KEYS}
    lite["creatures"] = [
        {field: creature[field] for field in LITE_CREATURE_FIELDS}
        for creature in state["creatures"]
    ]
    lite["lite"] = True
    return lite


def decode_frame(payload: bytes) -> dict[str, Any]:
    """Decode a /frame payload; the reference reader for tests and tooling."""
    values = np.frombuffer(payload, dtype="<f4")
    if values.size < FRAME_HEADER or values[0] != FRAME_VERSION:
        raise ValueError("not a Vikasa presentation frame")
    count, resources = int(values[2]), int(values[3])
    creature_stride, resource_stride = int(values[4]), int(values[5])
    body = values[FRAME_HEADER:FRAME_HEADER + count * creature_stride].reshape(
        count, creature_stride)
    food = values[FRAME_HEADER + count * creature_stride:].reshape(resources, resource_stride)
    weather = int(values[12])
    return {
        "version": float(values[0]),
        "tick": int(values[1]),
        "paused": bool(values[6]),
        "ticks_per_second": float(values[7]),
        "actual_ticks_per_second": float(values[8]),
        "season_phase": float(values[9]),
        "weather": WEATHER_CODES[weather] if weather >= 0 else None,
        "feed_seq": int(values[19]),
        "creatures": [
            {
                "id": int(row[0]), "x": float(row[1]), "y": float(row[2]),
                "vx": float(row[3]), "vy": float(row[4]), "energy_ratio": float(row[5]),
                "behavior": BEHAVIOR_CODES[int(row[6])], "size": float(row[7]),
                "speed": float(row[8]), "perception": float(row[9]),
                "aggression": float(row[10]), "resilience": float(row[11]),
                "sociability": float(row[12]), "flags": int(row[13]),
                "founder": int(row[14]), "generation": int(row[15]), "age": int(row[16]),
                "injury": float(row[17]),
            }
            for row in body
        ],
        "resources": [
            {"id": int(row[0]), "x": float(row[1]), "y": float(row[2]), "energy": float(row[3])}
            for row in food
        ],
    }


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

    def _reply_bytes(self, payload: bytes, content_type: str = "application/octet-stream") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

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
        elif self.path == "/stream":
            self._stream_frames()
        elif self.path == "/frame":
            self._reply_bytes(self.server.bridge.frame_bytes())
        elif self.path.split("?", 1)[0] == "/state":
            query = parse_qs(urlsplit(self.path).query)
            def number(key: str) -> int | None:
                value = query.get(key, [None])[0]
                return int(value) if value and value.lstrip("-").isdigit() else None

            since = {key: value for key, value in
                     (("history", number("hs")), ("birth_history", number("bs")))
                     if value is not None}
            payload = self.server.bridge.state_bytes(
                lite=query.get("lite", ["0"])[0] == "1", focus=number("focus"),
                since=since or None,
            )
            self._reply_bytes(payload, "application/json; charset=utf-8")
        else:
            self._reply(404, {"error": "Unknown endpoint"})

    def _stream_frames(self) -> None:
        """Push every new presentation frame, length-prefixed, on one connection.

        Polling costs the client a request per frame; a push stream costs it a
        non-blocking socket read. The connection ends when either side closes.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        bridge = self.server.bridge
        last: bytes | None = None
        try:
            while bridge.running:
                frame = bridge.wait_for_frame(last, timeout=1.0)
                if frame is None or frame is last:
                    continue
                self.wfile.write(struct.pack("<I", len(frame)) + frame)
                last = frame
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

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
        self._published_state_bytes: bytes | None = None
        self._published_lite_bytes: bytes | None = None
        self._published_frame: bytes | None = None
        self._frame_ready = threading.Condition()
        self._founders: dict[int, int] = {}
        self._feed: deque[dict[str, Any]] = deque(maxlen=FEED_LENGTH)
        self._feed_seq = 0
        self._event_source: list[dict[str, Any]] | None = None
        self._event_consumed = 0
        self._chronicle_marker: dict[str, Any] | None = None
        self._reset_event_cursor()
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
        # Hand the GIL over more often so HTTP readers are not starved by ticks.
        sys.setswitchinterval(0.001)
        self._publish_state()
        self._set_frame(self._build_frame())
        self._http_thread.start()
        self._sim_thread.start()

    def stop(self) -> None:
        self.running = False
        self._stop.set()
        with self._frame_ready:
            self._frame_ready.notify_all()
        self._http.shutdown()
        self._http.server_close()
        self._http_thread.join(timeout=2.0)
        self._sim_thread.join(timeout=2.0)

    def _run_simulation(self) -> None:
        deadline = time.monotonic()
        state_at = frame_at = deadline
        while not self._stop.wait(0.002):
            if self.paused:
                deadline = time.monotonic()
                continue
            now = time.monotonic()
            tick_interval = 1.0 / self.ticks_per_second
            if now >= deadline:
                with self.lock:
                    self._advance(1)
                    self._tick_times.append(time.monotonic())
                    # Two cadences: a cheap binary frame for smooth motion and
                    # the full explanatory document at a calmer rate. Building
                    # the document holds the GIL, so it must not run every tick.
                    if time.monotonic() - frame_at >= FRAME_INTERVAL:
                        self._set_frame(self._build_frame())
                        frame_at = time.monotonic()
                    if time.monotonic() - state_at >= STATE_INTERVAL:
                        self._publish_state()
                        state_at = time.monotonic()
                deadline = _next_simulation_deadline(
                    deadline, tick_interval, time.monotonic()
                )

    def _advance(self, count: int) -> None:
        for _ in range(count):
            self.engine.step(1)
            self._collect_events()

    def _reset_event_cursor(self) -> None:
        """Start reading a (new) engine's event sources from their current end."""
        self._event_source = self.engine.recent_events
        self._event_consumed = len(self.engine.recent_events)
        chronicle = self.engine.culture.chronicle
        self._chronicle_marker = chronicle[-1] if chronicle else None

    def _push_event(self, tick: int, kind: str, text: str, **extra: Any) -> None:
        self._feed_seq += 1
        self._feed.append({"seq": self._feed_seq, "tick": tick, "kind": kind, "text": text,
                           **extra})

    def _collect_events(self) -> None:
        """Move per-tick engine events into a sequenced feed the GUI cannot miss.

        The engine clears ``recent_events`` at the start of every tick by binding
        a new list, so list identity tells us whether the source rolled over.
        """
        engine = self.engine
        if engine.recent_events is not self._event_source:
            self._event_source = engine.recent_events
            self._event_consumed = 0
        for item in self._event_source[self._event_consumed:]:
            self._push_event(int(item.get("tick", engine.tick)), str(item.get("kind", "event")),
                             str(item.get("text", "")), creature_id=item.get("creature_id"))
        self._event_consumed = len(self._event_source)
        chronicle = engine.culture.chronicle
        fresh: list[dict[str, Any]] = []
        for item in reversed(chronicle):
            if item is self._chronicle_marker:
                break
            fresh.append(item)
        for item in reversed(fresh):
            self._push_event(int(item["tick"]), str(item["kind"]), str(item["text"]),
                             tradition_id=item.get("tradition_id"))
        if chronicle:
            self._chronicle_marker = chronicle[-1]

    def founder_of(self, creature_id: int) -> int:
        """Maternal-line root (first recorded parent, repeatedly): a stable dynasty key."""
        if creature_id in self._founders:
            return self._founders[creature_id]
        trail = [creature_id]
        cursor = creature_id
        while cursor not in self._founders:
            parents = self.engine.lineage.parents_of(cursor)
            if parents is None:
                self._founders[cursor] = cursor
                break
            cursor = parents[0]
            trail.append(cursor)
        root = self._founders[cursor]
        for item in trail:
            self._founders[item] = root
        return root

    def _publish_state(self) -> None:
        # Serialise the slim document once per publication; the full document
        # is serialised lazily, only if a legacy client asks for it.
        state = self._build_state()
        self._published_state = state
        self._published_state_bytes = None
        self._published_lite_bytes = _encode(_lite(state))

    def state_bytes(self, *, lite: bool = False, focus: int | None = None,
                    since: dict[str, int] | None = None) -> bytes:
        live = self._sim_thread.is_alive() and self._published_state is not None
        state = self._published_state if live else self._build_state()
        if lite:
            payload = (self._published_lite_bytes if live and self._published_lite_bytes
                       else _encode(_lite(state)))
            # Splice per-client parts into the pre-serialised document.
            extra = b""
            cursors = since or {}
            for key in HISTORY_KEYS:
                after = cursors.get(key)
                rows = state[key] if after is None else [r for r in state[key] if r["tick"] > after]
                extra += b',"' + key.encode() + b'":' + _encode(rows)
            if since is not None:
                extra += b',"history_since":' + _encode(since)
            detail = next((c for c in state["creatures"] if c["id"] == focus), None)
            if detail is not None:
                extra += b',"focus":' + _encode(detail)
            return payload[:-1] + extra + b"}"
        if not live:
            return _encode(state)
        if self._published_state_bytes is None:
            self._published_state_bytes = _encode(state)
        return self._published_state_bytes

    def state(self) -> dict[str, Any]:
        # HTTP reads a completed immutable-by-convention publication; a slow
        # engine tick cannot make a GUI poll queue behind the simulation lock.
        if self._sim_thread.is_alive() and self._published_state is not None:
            return self._published_state
        return self._build_state()

    def _set_frame(self, frame: bytes) -> None:
        with self._frame_ready:
            self._published_frame = frame
            self._frame_ready.notify_all()

    def wait_for_frame(self, last: bytes | None, timeout: float) -> bytes | None:
        """Block until a frame other than ``last`` is published (or timeout)."""
        with self._frame_ready:
            self._frame_ready.wait_for(
                lambda: self._published_frame is not last or not self.running, timeout)
            return self._published_frame

    def frame_bytes(self) -> bytes:
        if self._sim_thread.is_alive() and self._published_frame is not None:
            return self._published_frame
        return self._build_frame()

    def _build_frame(self) -> bytes:
        with self.lock:
            engine = self.engine
            creatures = [engine.creatures[key] for key in sorted(engine.creatures)]
            resources = [engine.resources[key] for key in sorted(engine.resources)]
            out = np.zeros(
                FRAME_HEADER + CREATURE_STRIDE * len(creatures) + RESOURCE_STRIDE * len(resources),
                dtype="<f4",
            )
            environment = engine.environment
            events = environment.active_events
            weather = events[0] if events else None
            max_energy = engine.config.energy.maximum
            out[:FRAME_HEADER] = (
                FRAME_VERSION, engine.tick, len(creatures), len(resources),
                CREATURE_STRIDE, RESOURCE_STRIDE, float(self.paused), self.ticks_per_second,
                self._measured_rate(), (engine.tick % 384) / 96.0,
                environment.temperature, environment.rainfall,
                WEATHER_CODES.index(weather.kind) if weather else -1,
                weather.intensity if weather else 0.0,
                (max(0, weather.end_tick - engine.tick) / max(1, weather.duration)
                 if weather else 0.0),
                engine.config.world.width, engine.config.world.height,
                engine.total_births, engine.total_deaths, self._feed_seq,
                environment.food_multiplier, environment.health_pressure, max_energy, 0.0,
            )
            young_age = engine.config.behavior.dependent_age_ticks
            offset = FRAME_HEADER
            for item in creatures:
                flags = (
                    (FLAG_ALPHA if item.alpha else 0)
                    | (FLAG_INJURED if item.injury > 0.12 else 0)
                    | (FLAG_YOUNG if item.parents is not None and item.age < young_age else 0)
                    | (FLAG_STARVING if item.starvation_ticks > 0 else 0)
                    | (FLAG_BELIEVER if item.belief_id is not None else 0)
                )
                genes = item.genome.values
                temperament = item.temperament
                out[offset:offset + CREATURE_STRIDE] = (
                    item.id, item.position[0], item.position[1],
                    item.velocity[0], item.velocity[1],
                    max(0.0, min(1.0, item.energy / max_energy)),
                    BEHAVIOR_CODES.index(item.behavior_state.action.value),
                    genes[0], genes[1], genes[2], temperament.aggression,
                    temperament.resilience, temperament.sociability, flags,
                    self.founder_of(item.id), engine.lineage.generation_of(item.id),
                    item.age, item.injury,
                )
                offset += CREATURE_STRIDE
            for food in resources:
                out[offset:offset + RESOURCE_STRIDE] = (
                    food.id, food.position[0], food.position[1], food.energy)
                offset += RESOURCE_STRIDE
            return out.tobytes()

    def _measured_rate(self) -> float:
        if len(self._tick_times) > 1 and not self.paused:
            return round((len(self._tick_times) - 1)
                         / max(0.001, self._tick_times[-1] - self._tick_times[0]), 1)
        return 0.0

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
                        "generation": engine.lineage.generation_of(item.id),
                        "founder": self.founder_of(item.id),
                        "haplotypes": item.genome.haplotypes,
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
                "actual_ticks_per_second": self._measured_rate(),
                "feed": list(self._feed)[-60:],
                "feed_seq": self._feed_seq,
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
                "population_genetics": (population_genetics(
                    [item.genome.haplotypes for item in engine.creatures.values()],
                    loci=len(engine.config.genome.architecture.dominance))
                    if engine.config.genome.architecture is not None else None),
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
            self._founders.clear()
            self._reset_event_cursor()
            self._push_event(0, "restart", "A fresh founding population entered the habitat.")
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
                self._advance(count)
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
        elif action == "food_burst":
            return self._food_burst(value)
        else:
            raise ValueError(
                "action must be pause, resume, restart, speed, step, weather, food, or food_burst")
        self._publish()
        return {"ok": True, "action": action}

    def _publish(self) -> None:
        self._collect_events()
        self._publish_state()
        self._set_frame(self._build_frame())

    def _food_burst(self, value: dict[str, Any]) -> dict[str, Any]:
        """Scatter a ring of audited external food on a deterministic golden-angle spiral.

        No engine random numbers are consumed, so the intervention is reproducible
        from its logged parameters alone.
        """
        x = float(value.get("x", 0.5))
        y = float(value.get("y", 0.5))
        count = int(value.get("count", 8))
        radius = float(value.get("radius", 0.06))
        engine = self.engine
        energy = float(value.get("energy", engine.config.resources.energy_value))
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError("food coordinates must be normalized to zero through one")
        if not 1 <= count <= MAX_FOOD_BURST:
            raise ValueError(f"food burst count must be between 1 and {MAX_FOOD_BURST}")
        if not 0.0 <= radius <= 0.25:
            raise ValueError("food burst radius must be between 0 and 0.25")
        if energy <= 0.0 or energy > engine.config.energy.maximum:
            raise ValueError("food energy is outside the valid range")
        room = engine.config.resources.maximum_count - len(engine.resources)
        if room <= 0:
            raise ValueError("the configured food-patch limit has been reached")
        width, height = engine.config.world.width, engine.config.world.height
        scale = min(width, height)
        placed = 0
        for index in range(min(count, room)):
            distance = radius * scale * np.sqrt((index + 0.5) / count)
            angle = index * 2.399963229728653
            point = np.array([
                min(max(x * width + distance * np.cos(angle), 0.0), float(width)),
                min(max(y * height + distance * np.sin(angle), 0.0), float(height)),
            ])
            engine.add_food(point, energy)
            placed += 1
        self._publish()
        return {"ok": True, "action": "food_burst", "placed": placed}


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
