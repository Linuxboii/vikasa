"""Install a native desktop shortcut for the Vikasa laboratory."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from evolution_sim.bridge import _godot_binary


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def install_desktop_shortcut(
    *,
    project_root: str | Path | None = None,
    desktop: str | Path | None = None,
    name: str = "Vikasa",
    config: str | Path | None = None,
    seed: int = 2026,
) -> Path:
    """Create a Windows .lnk that launches Vikasa without a console window."""
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
    arguments = (
        f'-m evolution_sim.cli godot --config "{config_path}" --seed {seed} '
        f'--godot-path "{godot_binary}"'
    )
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
            "$link.Description = 'Launch Vikasa Living Biome 3D'",
            f"$link.IconLocation = {_ps_quote(str(godot_binary) + ',0')}",
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
