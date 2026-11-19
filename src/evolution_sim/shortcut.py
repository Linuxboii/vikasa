"""Install a native desktop shortcut for the Vikasa laboratory."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from evolution_sim.bridge import _godot_binary

ASSETS = Path(__file__).resolve().parent / "assets"

# mode -> (default shortcut name, description, icon file)
SHORTCUTS: dict[str, tuple[str, str, str]] = {
    "app": ("Vikasa", "Open Vikasa: the 3D Living Biome, Species Risk Checker, Conservation "
            "Planner and Demo mode in one place", "vikasa-biome.ico"),
    "biome": ("Vikasa 3D", "Launch Vikasa Living Biome 3D", "vikasa-biome.ico"),
    "demo": ("Vikasa Demo", "Launch Vikasa Demo mode: presenter hub with the 3D Living Biome "
             "on autopilot", "vikasa-demo.ico"),
    "risk": ("Vikasa Risk Checker", "Launch the Vikasa Species Risk Checker: will a species "
             "keep up with warming here?", "vikasa-risk.ico"),
}


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def install_desktop_shortcut(
    *,
    project_root: str | Path | None = None,
    desktop: str | Path | None = None,
    name: str = "Vikasa",
    config: str | Path | None = None,
    seed: int = 2026,
    mode: str = "app",
) -> Path:
    """Create a Windows .lnk that launches Vikasa without a console window.

    ``mode`` picks what the shortcut opens: ``app`` (the Vikasa home screen, from which
    everything else launches), ``biome`` (straight into the 3D Living Biome), ``demo``
    (the presenter Demo hub) or ``risk`` (the Species Risk Checker).
    """
    if mode not in SHORTCUTS:
        raise ValueError(f"mode must be one of {', '.join(SHORTCUTS)}")
    if os.name != "nt":
        raise RuntimeError("Desktop shortcut installation currently supports Windows")
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    config_path = (
        Path(config).resolve() if config is not None else root / "config" / "showcase.json"
    )
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration does not exist: {config_path}")
    godot_binary = Path(_godot_binary(None))
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        raise FileNotFoundError(f"GUI Python executable does not exist: {pythonw}")
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise RuntimeError("Windows PowerShell is required to create the shortcut")

    desktop_path = Path(desktop).resolve() if desktop is not None else None
    if desktop_path is not None:
        desktop_path.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(character for character in name if character not in '<>:"/\\|?*').strip()
    if not safe_name:
        raise ValueError("Shortcut name must contain a filename-safe character")

    desktop_expression = (
        _ps_quote(desktop_path)
        if desktop_path is not None
        else "$shell.SpecialFolders.Item('Desktop')"
    )
    if mode == "biome":
        arguments = (
            f'-m evolution_sim.cli godot --config "{config_path}" --seed {seed} '
            f'--godot-path "{godot_binary}"'
        )
    else:
        arguments = f"-m evolution_sim.cli {mode}"
    description = SHORTCUTS[mode][1]
    icon_file = ASSETS / SHORTCUTS[mode][2]
    icon = f"{icon_file},0" if icon_file.is_file() else f"{godot_binary},0"
    script = "; ".join(
        (
            "$shell = New-Object -ComObject WScript.Shell",
            f"$desktop = {desktop_expression}",
            f"$path = Join-Path $desktop {_ps_quote(safe_name + '.lnk')}",
            "$link = $shell.CreateShortcut($path)",
            f"$link.TargetPath = {_ps_quote(pythonw)}",
            f"$link.Arguments = {_ps_quote(arguments)}",
            f"$link.WorkingDirectory = {_ps_quote(root)}",
            "$link.WindowStyle = 1",
            f"$link.Description = {_ps_quote(description)}",
            f"$link.IconLocation = {_ps_quote(icon)}",
            "$link.Save()",
            "Write-Output $path",
        )
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Could not create the desktop shortcut: {exc}") from exc
    shortcut = Path(result.stdout.strip().splitlines()[-1])
    if not shortcut.is_file():
        raise RuntimeError(f"Windows did not create the shortcut: {shortcut}")
    return shortcut


def install_shortcut_set(
    *,
    desktop: str | Path | None = None,
    name: str = "Vikasa",
    config: str | Path | None = None,
    seed: int = 2026,
    modes: tuple[str, ...] = ("app",),
) -> list[Path]:
    """Install Vikasa desktop shortcuts: by default the single Vikasa home-screen shortcut.

    Pass ``modes`` to add optional direct shortcuts (biome, demo, risk).
    Re-running replaces existing shortcuts of the same names.
    """
    installed = []
    for mode in modes:
        label = name if mode == "app" else SHORTCUTS[mode][0]
        installed.append(install_desktop_shortcut(desktop=desktop, name=label, config=config,
                                                  seed=seed, mode=mode))
    return installed
