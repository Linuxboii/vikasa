from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evolution_sim.bridge import _godot_binary
from evolution_sim.shortcut import install_desktop_shortcut


def test_installer_creates_launchable_windows_shortcut(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]

    shortcut = install_desktop_shortcut(
        project_root=root,
        desktop=tmp_path,
        name="Vikasa Test",
        config=root / "config" / "showcase.json",
        seed=77,
    )

    assert shortcut == tmp_path / "Vikasa Test.lnk"
    assert shortcut.exists()
    assert shortcut.stat().st_size > 100

    escaped_shortcut = str(shortcut).replace("'", "''")
    powershell = f"""
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut('{escaped_shortcut}')
    [pscustomobject]@{{
      TargetPath = $link.TargetPath
      Arguments = $link.Arguments
      WorkingDirectory = $link.WorkingDirectory
      Description = $link.Description
    }} | ConvertTo-Json -Compress
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell],
        check=True,
        capture_output=True,
        text=True,
    )
    details = json.loads(result.stdout)

    assert Path(details["TargetPath"]) == Path(sys.executable).with_name("pythonw.exe")
    assert "evolution_sim.cli godot" in details["Arguments"]
    assert "--godot-path" in details["Arguments"]
    assert "Living Biome" in details["Description"]
    assert details["WorkingDirectory"] == str(root)


def test_godot_runtime_is_discovered_from_user_winget_install(tmp_path, monkeypatch) -> None:
    winget = (
        tmp_path
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "GodotEngine.GodotEngine_Microsoft.Winget.Source_test"
    )
    winget.mkdir(parents=True)
    binary = winget / "Godot_v4.7.2-stable_win64.exe"
    binary.write_bytes(b"runtime placeholder")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("VIKASA_GODOT_BINARY", raising=False)
    monkeypatch.setattr("evolution_sim.bridge.shutil.which", lambda _name: None)

    assert _godot_binary(None) == str(binary)
