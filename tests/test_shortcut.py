from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_shortcut_set_installs_one_biome_shortcut_by_default(monkeypatch, tmp_path) -> None:
    from evolution_sim import shortcut

    calls = []
    monkeypatch.setattr(shortcut, "install_desktop_shortcut",
                        lambda **kwargs: calls.append(kwargs) or tmp_path / kwargs["name"])
    installed = shortcut.install_shortcut_set(desktop=tmp_path, name="My Vikasa", seed=5)
    assert [call["mode"] for call in calls] == ["biome"]
    assert [path.name for path in installed] == ["My Vikasa"]
    calls.clear()
    shortcut.install_shortcut_set(desktop=tmp_path, modes=("demo", "risk"))
    assert [call["mode"] for call in calls] == ["demo", "risk"]


def test_demo_shortcut_script_launches_demo_mode_with_its_icon(monkeypatch, tmp_path) -> None:
    from evolution_sim import shortcut

    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_bytes(b"")
    scripts = []

    def fake_run(command, **_kwargs):
        scripts.append(command[-1])
        link = tmp_path / "Vikasa Demo.lnk"
        link.write_bytes(b"x" * 200)
        return subprocess.CompletedProcess(command, 0, stdout=f"{link}\n", stderr="")

    monkeypatch.setattr(shortcut, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(shortcut.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(shortcut, "_godot_binary", lambda _explicit: "godot.exe")
    monkeypatch.setattr(shortcut.shutil, "which", lambda _name: "powershell.exe")
    monkeypatch.setattr(shortcut.subprocess, "run", fake_run)
    link = shortcut.install_desktop_shortcut(desktop=tmp_path, name="Vikasa Demo", mode="demo")
    assert link.name == "Vikasa Demo.lnk"
    script = scripts[0]
    assert "-m evolution_sim.cli demo" in script
    assert "vikasa-demo.ico" in script
    assert "Demo mode" in script
    with pytest.raises(ValueError):
        shortcut.install_desktop_shortcut(desktop=tmp_path, mode="nope")
