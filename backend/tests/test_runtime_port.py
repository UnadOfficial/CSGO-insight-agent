"""The uvicorn listener and the GSI sink URL must agree on one port.

They previously carried independent defaults (19871 for the listener, 8000 for
the GSI sink). A launcher that did not export ``CSGO_INSIGHT_PORT`` pointed
CS:GO's GSI at a port nothing was listening on, so ``is_gsi_ready()`` never
became true and recording aborted after the full 120 s gate with
``RECORDING_GSI_NOT_READY`` — even though the game had started correctly.
"""

import pytest

from app.obs_director import _resolve_gsi_sink_url
from app.runtime_port import DEFAULT_BACKEND_PORT, resolve_backend_port


@pytest.fixture(autouse=True)
def _clear_port_env(monkeypatch):
    for name in (
        "CSGO_INSIGHT_PORT",
        "CSGO_INSIGHT_GSI_URL",
        "CSGO_INSIGHT_BACKEND_GSI_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_port_matches_the_desktop_shell_and_packaging():
    # frontend/src-tauri/src/lib.rs and packaging/windows/*.bat all pin 19871.
    assert DEFAULT_BACKEND_PORT == 19871
    assert resolve_backend_port() == DEFAULT_BACKEND_PORT


def test_env_port_overrides_the_default(monkeypatch):
    monkeypatch.setenv("CSGO_INSIGHT_PORT", "18000")
    assert resolve_backend_port() == 18000


@pytest.mark.parametrize("value", ["", "   ", "not-a-port", "0", "-1", "70000", "12.5"])
def test_unusable_port_falls_back_to_the_default(monkeypatch, value):
    """A malformed value must not desync GSI from the listener."""
    monkeypatch.setenv("CSGO_INSIGHT_PORT", value)
    assert resolve_backend_port() == DEFAULT_BACKEND_PORT


def test_gsi_sink_follows_the_listener_port(monkeypatch):
    assert _resolve_gsi_sink_url() == f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}/api/gsi/csgo"

    monkeypatch.setenv("CSGO_INSIGHT_PORT", "18000")
    assert _resolve_gsi_sink_url() == "http://127.0.0.1:18000/api/gsi/csgo"


def test_gsi_sink_tracks_the_port_the_listener_would_bind(monkeypatch):
    """The regression: sink port and resolved listener port must never diverge."""
    for value in (None, "8000", "18000", "garbage"):
        if value is None:
            monkeypatch.delenv("CSGO_INSIGHT_PORT", raising=False)
        else:
            monkeypatch.setenv("CSGO_INSIGHT_PORT", value)
        assert _resolve_gsi_sink_url().endswith(f":{resolve_backend_port()}/api/gsi/csgo")


def test_explicit_gsi_url_still_wins(monkeypatch):
    monkeypatch.setenv("CSGO_INSIGHT_GSI_URL", "http://127.0.0.1:9999/api/gsi/csgo")
    assert _resolve_gsi_sink_url() == "http://127.0.0.1:9999/api/gsi/csgo"


def test_legacy_backend_gsi_url_env_is_honoured(monkeypatch):
    monkeypatch.setenv(
        "CSGO_INSIGHT_BACKEND_GSI_URL", "http://127.0.0.1:9998/api/gsi/csgo"
    )
    assert _resolve_gsi_sink_url() == "http://127.0.0.1:9998/api/gsi/csgo"
