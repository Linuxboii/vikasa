from __future__ import annotations

from pathlib import Path

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
