"""Local Vikasa app: home screen, Species Risk Checker and the presenter Demo hub.

Runs on 127.0.0.1 only, needs no internet for bundled places, and launches the
Godot Living Biome as a child process for "Watch it in 3D" and the demo tour.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import mimetypes
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from evolution_sim.climate import risk
from evolution_sim.climate.data import (
    SSP_WARMING,
    fetch_power_monthly,
    region_from_power,
    resolve_region,
    save_region,
)

WEB_DIR = Path(__file__).resolve().parent / "web"
EVIDENCE_DIR = risk.ROOT / "docs" / "results" / "climate-rescue-2026-10-18"
DEFAULT_PORT = 8787
APP_PROTOCOL = 3  # bump when pages or routes change, so an older running copy is replaced
EXAMPLE_WATCHLIST = WEB_DIR / "watchlist-example.csv"
PLACE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

LAUNCHES: dict[str, tuple[str, list[str]]] = {
    "biome": ("Living Biome showcase", ["--config", "config/showcase.json"]),
    "biome-demo": ("Living Biome · Demo autopilot",
                   ["--config", "config/showcase.json", "--demo"]),
    "climate-demo": ("Warming biome · Western Ghats", ["--config", "config/climate-demo.json"]),
}


class RiskApp:
    """State shared by request handlers: live checks, custom places and Godot."""

    def __init__(self, *, root: Path | None = None, launch_godot: bool = True) -> None:
        self.root = Path(root) if root is not None else risk.ROOT / "exports" / "risk"
        self.live = risk.LiveChecks(root=self.root / "live")
        self.custom_dir = self.root / "places"
        self.launch_godot = launch_godot
        self.godot: subprocess.Popen | None = None
        self.godot_label = ""
        self.lock = threading.Lock()
        self.reference = risk.load_reference()
        self._stats: dict[str, Any] | None = None

    # ------------------------------------------------------------------ places
    def place_spec(self, key: str) -> str:
        """Bundled key, or the JSON file of a place fetched on this machine."""
        if key.startswith("custom:"):
            name = key.removeprefix("custom:")
            if not PLACE_KEY.match(name):
                raise ValueError("invalid custom place key")
            path = self.custom_dir / f"{name}.json"
            if not path.is_file():
                raise ValueError(f"No fetched place named {name!r}")
            return str(path)
        resolve_region(key)
        return key

    def meta(self) -> dict[str, Any]:
        rows = risk.places()
        if self.custom_dir.is_dir():
            for path in sorted(self.custom_dir.glob("*.json")):
                region = resolve_region(str(path))
                rows.insert(0, {"key": f"custom:{path.stem}", "name": region.name,
                                "latitude": region.latitude, "longitude": region.longitude,
                                "annual_mean_c": region.annual_mean_c,
                                "seasonal_amplitude_c": region.seasonal_amplitude_c,
                                "trend_c_per_decade": region.trend_c_per_decade,
                                "monthly_c": list(region.monthly_c), "kind": "fetched"})
        heritable = self.reference["heritable"]
        return {"places": rows, "presets": list(risk.SPECIES_PRESETS),
                "preset_note": risk.PRESET_NOTE,
                "tolerance_modes": {key: label for key, (label, _) in
                                    risk.TOLERANCE_MODES.items()},
                "ssps": {name: {"median_2081_2100_c": values[0],
                                "rate_c_per_year": risk.ssp_rate_c_per_year(name)}
                         for name, values in SSP_WARMING.items()},
                "reference": {"critical_rate": heritable["critical_rate"],
                              "ci95": heritable["ci95"], "logistic": heritable["logistic"],
                              "control_logistic": self.reference["control"]["logistic"],
                              "control_critical_rate":
                                  self.reference["control"]["critical_rate"],
                              "curve": heritable["curve"],
                              "rescue_gain": self.reference["rescue_gain"]},
                "godot": self.godot_status(),
                "evidence_available": (EVIDENCE_DIR / "index.html").is_file()}

    def stats(self) -> dict[str, Any]:
        """Live project statistics for the demo's engineering chapter."""
        if self._stats is None:
            root = risk.ROOT
            tests = sum(path.read_text(encoding="utf-8", errors="ignore").count("def test_")
                        for path in (root / "tests").rglob("*.py"))
            python = sum(len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
                         for path in (root / "src").rglob("*.py"))
            godot = sum(len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
                        for pattern in ("*.gd", "*.gdshader")
                        for path in (root / "godot").rglob(pattern))
            criteria = []
            summary = EVIDENCE_DIR / "summary.json"
            if summary.is_file():
                criteria = [{"id": row["id"], "statement": row["statement"],
                             "passed": bool(row["passed"])}
                            for row in json.loads(summary.read_text(encoding="utf-8"))
                            .get("criteria", [])]
            self._stats = {"tests": tests, "python_lines": python, "godot_lines": godot,
                           "criteria": criteria}
        return self._stats

    def fetch_place(self, body: dict[str, Any]) -> dict[str, Any]:
        name = str(body.get("name", "")).strip()[:60]
        lat, lon = float(body["latitude"]), float(body["longitude"])
        if not name:
            raise ValueError("Give the place a name")
        key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "place"
        raw, url = fetch_power_monthly(lat, lon, 1981, dt.date.today().year - 1)
        region = region_from_power(key, name, lat, lon, raw, url,
                                   dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        save_region(region, self.custom_dir / f"{key}.json")
        return {"key": f"custom:{key}", "name": region.name}

    # ------------------------------------------------------------------ estimates
    def estimate(self, query: dict[str, str]) -> dict[str, Any]:
        spec = self.place_spec(query.get("place", "hyderabad"))
        return risk.instant_estimate(
            spec, generation_years=float(query.get("generation_years", 1)),
            tolerance=query.get("tolerance", "local"), ssp=query.get("ssp", "SSP5-8.5"),
            reference=self.reference)

    def start_live(self, body: dict[str, Any]) -> dict[str, Any]:
        job = self.live.start(self.place_spec(str(body.get("place", "hyderabad"))),
                              generation_years=float(body.get("generation_years", 1)),
                              tolerance=body.get("tolerance", "local"),
                              ssp=str(body.get("ssp", "SSP5-8.5")),
                              seeds=int(body.get("seeds", 4)))
        return job.snapshot()

    # ------------------------------------------------------------------ planner
    def plan(self, body: dict[str, Any]) -> dict[str, Any]:
        from evolution_sim.climate import planner

        rows = planner.read_watchlist(str(body.get("csv", "")))
        extra = []
        if self.custom_dir.is_dir():
            extra = [resolve_region(str(path)) for path in sorted(self.custom_dir.glob("*.json"))]
        result = planner.triage(rows, ssp=str(body.get("ssp", "SSP5-8.5")), extra_places=extra,
                                allow_paths=False)
        return {"result": result, "html": planner.render_html(result),
                "csv": planner.to_csv(result)}

    # ------------------------------------------------------------------ Godot
    def godot_status(self) -> dict[str, Any]:
        running = self.godot is not None and self.godot.poll() is None
        return {"running": running, "label": self.godot_label if running else ""}

    def _spawn(self, label: str, arguments: list[str]) -> dict[str, Any]:
        if not self.launch_godot:
            return {"launched": False, "label": label, "arguments": arguments}
        with self.lock:
            if self.godot is not None and self.godot.poll() is None:
                self.godot.terminate()
                try:
                    self.godot.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.godot.kill()
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.godot = subprocess.Popen(
                [sys.executable, "-m", "evolution_sim.cli", "godot", "--seed", "2026",
                 *arguments], cwd=risk.ROOT, creationflags=flags)
            self.godot_label = label
        return {"launched": True, "label": label}

    def launch(self, what: str) -> dict[str, Any]:
        if what not in LAUNCHES:
            raise ValueError(f"unknown launch target {what!r}")
        label, arguments = LAUNCHES[what]
        return self._spawn(label, list(arguments))

    def watch(self, body: dict[str, Any]) -> dict[str, Any]:
        spec = self.place_spec(str(body.get("place", "hyderabad")))
        region = resolve_region(spec)
        target = self.root / "watch" / f"{region.key}.json"
        risk.write_watch_config(target, spec,
                                generation_years=float(body.get("generation_years", 1)),
                                tolerance=body.get("tolerance", "local"),
                                ssp=str(body.get("ssp", "SSP5-8.5")))
        label = f"{region.name} · {body.get('ssp', 'SSP5-8.5')} in fast-forward"
        result = self._spawn(label, ["--config", str(target)])
        return {**result, "config": str(target)}

    def stop_godot(self) -> None:
        with self.lock:
            if self.godot is not None and self.godot.poll() is None:
                self.godot.terminate()


def _handler(app: RiskApp, server_ref: dict[str, ThreadingHTTPServer]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VikasaRisk/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # pythonw has no stderr
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value: Any, status: int = 200) -> None:
            self._send(status, json.dumps(value, allow_nan=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _file(self, path: Path) -> None:
            if not path.is_file():
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind == "application/json":
                kind += "; charset=utf-8"
            self._send(200, path.read_bytes(), kind)

        def _body(self) -> dict[str, Any]:
            # Only same-machine pages may post: a JSON content type forces a CORS
            # preflight (which this server never approves) and a foreign Origin is refused.
            kind = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if kind != "application/json":
                raise ValueError("requests must be application/json")
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
                raise ValueError("cross-origin requests are not accepted")
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 400_000:
                raise ValueError("request body too large")
            raw = self.rfile.read(length) if length else b"{}"
            value = json.loads(raw or b"{}")
            if not isinstance(value, dict):
                raise ValueError("request body must be a JSON object")
            return value

        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = {key: values[-1] for key, values in parse_qs(url.query).items()}
            try:
                if url.path in ("/", "/home"):
                    self._file(WEB_DIR / "home.html")
                elif url.path == "/risk":
                    self._file(WEB_DIR / "risk.html")
                elif url.path == "/demo":
                    self._file(WEB_DIR / "demo.html")
                elif url.path == "/plan":
                    self._file(WEB_DIR / "plan.html")
                elif url.path == "/api/plan/example":
                    self._send(200, EXAMPLE_WATCHLIST.read_bytes(), "text/csv; charset=utf-8")
                elif url.path == "/api/meta":
                    self._json(app.meta())
                elif url.path == "/api/estimate":
                    self._json(app.estimate(query))
                elif url.path.startswith("/api/live/"):
                    self._json(app.live.get(url.path.rsplit("/", 1)[-1]).snapshot())
                elif url.path == "/api/version":
                    from evolution_sim import __version__

                    self._json({"app_protocol": APP_PROTOCOL, "version": __version__})
                elif url.path == "/api/stats":
                    self._json(app.stats())
                elif url.path == "/api/godot":
                    self._json(app.godot_status())
                elif url.path.startswith("/evidence/"):
                    relative = url.path.removeprefix("/evidence/") or "index.html"
                    target = (EVIDENCE_DIR / relative).resolve()
                    if EVIDENCE_DIR.resolve() not in target.parents and target != (
                            EVIDENCE_DIR / "index.html").resolve():
                        raise ValueError("path outside the evidence folder")
                    self._file(target)
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except KeyError:
                self._json({"error": "unknown job"}, HTTPStatus.NOT_FOUND)
            except (ValueError, OSError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            try:
                body = self._body()
                if url.path == "/api/live":
                    self._json(app.start_live(body))
                elif url.path == "/api/plan":
                    self._json(app.plan(body))
                elif url.path == "/api/watch":
                    self._json(app.watch(body))
                elif url.path == "/api/launch":
                    self._json(app.launch(str(body.get("what", ""))))
                elif url.path == "/api/stop-godot":
                    app.stop_godot()
                    self._json({"ok": True})
                elif url.path == "/api/fetch":
                    self._json(app.fetch_place(body))
                elif url.path == "/api/quit":
                    self._json({"ok": True})
                    app.stop_godot()
                    threading.Thread(target=server_ref["server"].shutdown, daemon=True).start()
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    return Handler


class _ExclusiveServer(ThreadingHTTPServer):
    """One Vikasa per port. On Windows, SO_REUSEADDR lets a second process bind a port
    that is already serving, so an older copy would never be detected or replaced."""

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def make_server(app: RiskApp, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    holder: dict[str, ThreadingHTTPServer] = {}
    server = _ExclusiveServer(("127.0.0.1", port), _handler(app, holder))
    holder["server"] = server
    return server


def _running_protocol(port: int) -> int | None:
    """App protocol of a Vikasa server already on this port; 0 if it predates versioning."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=3) as reply:
            return int(json.loads(reply.read()).get("app_protocol", 0))
    except urllib.error.HTTPError:
        return 0
    except (OSError, ValueError):
        return None


def _ask_to_quit(port: int) -> None:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}",
                                     headers={"Content-Type": "application/json"})
    with contextlib.suppress(OSError):
        urllib.request.urlopen(request, timeout=3).close()


def serve(*, page: str = "/", port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    app = RiskApp()
    server = None
    asked_to_quit = False
    for _ in range(20):
        try:
            server = make_server(app, port)
            break
        except OSError:
            if not asked_to_quit:
                running = _running_protocol(port)
                if running is not None and running < APP_PROTOCOL:
                    # An older Vikasa is still running: shut it down and take over.
                    _ask_to_quit(port)
                    asked_to_quit = True
                    time.sleep(0.5)
                    continue
                # The current version is already running (a second click): just open it.
                if open_browser:
                    webbrowser.open(f"http://127.0.0.1:{port}{page}")
                return 0
            time.sleep(0.5)
    if server is None:
        return 2
    url = f"http://127.0.0.1:{server.server_address[1]}{page}"
    print(f"Vikasa is ready at {url}  (Ctrl+C or the Quit button stops it)", flush=True)
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_godot()
        server.server_close()
    return 0
