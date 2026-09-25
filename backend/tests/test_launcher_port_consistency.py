"""Every launcher must publish one backend port before starting the backend.

The listener, the GSI sink URL and the browser URL are all derived from
``CSGO_INSIGHT_PORT``. A launcher that leaves it unset relies on each consumer's
own default, which is exactly how the sink and the listener drifted apart and
recording aborted with "CS:GO 未在限定时间内进入游戏画面".
"""

from pathlib import Path

import pytest

from app.runtime_port import DEFAULT_BACKEND_PORT

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_PACKAGING = REPO_ROOT / "packaging" / "windows"
LAUNCH_PS1 = WINDOWS_PACKAGING / "Launch-CSGOInsight.ps1"
DEV_PS1 = WINDOWS_PACKAGING / "dev_desktop.ps1"
PORTABLE_PS1 = WINDOWS_PACKAGING / "package_portable.ps1"
TAURI_LIB_RS = REPO_ROOT / "frontend" / "src-tauri" / "src" / "lib.rs"


@pytest.fixture(scope="module")
def launch_ps1() -> str:
    return LAUNCH_PS1.read_text(encoding="utf-8")


def test_installed_launcher_defaults_to_the_shared_port(launch_ps1):
    """The Start Menu / Desktop shortcut path must match the backend default."""
    assert f"$port = {DEFAULT_BACKEND_PORT}" in launch_ps1
    assert "$port = 8000" not in launch_ps1


def test_installed_launcher_exports_the_resolved_port(launch_ps1):
    """Exporting it is what keeps the GSI sink pointed at the live listener."""
    assert '$env:CSGO_INSIGHT_PORT = "$port"' in launch_ps1
    # The export has to happen before the backend is started.
    assert launch_ps1.index('$env:CSGO_INSIGHT_PORT = "$port"') < launch_ps1.index(
        "& $py -m app.run_server"
    )


def test_dev_browser_launcher_pins_the_port_it_proxies_to():
    """Vite proxies /api to :8000, so dev must declare that same port."""
    dev = DEV_PS1.read_text(encoding="utf-8")
    assert "$devPort = 8000" in dev
    assert '$env:CSGO_INSIGHT_PORT = "$devPort"' in dev
    assert '"--port", "$devPort"' in dev


def test_portable_launcher_pins_the_shared_port():
    portable = PORTABLE_PS1.read_text(encoding="utf-8")
    assert f'set "CSGO_INSIGHT_PORT={DEFAULT_BACKEND_PORT}"' in portable


def test_desktop_shell_pins_the_shared_port():
    lib_rs = TAURI_LIB_RS.read_text(encoding="utf-8")
    assert f'.env("CSGO_INSIGHT_PORT", "{DEFAULT_BACKEND_PORT}")' in lib_rs
