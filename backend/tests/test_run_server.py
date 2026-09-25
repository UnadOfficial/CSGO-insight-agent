from app import run_server
from app.runtime_port import DEFAULT_BACKEND_PORT


def test_portable_launcher_uses_supported_uvicorn_config(monkeypatch):
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, app, **kwargs):
            captured["app"] = app
            captured["kwargs"] = kwargs

    class FakeServer:
        def __init__(self, config):
            captured["config"] = config
            self.should_exit = False

        def run(self):
            captured["ran"] = True

    shutdown_callbacks = []
    monkeypatch.setattr(run_server, "_install_windows_selector_loop", lambda: None)
    monkeypatch.setattr(run_server.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(run_server.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(
        "app.shutdown_state.register_server_shutdown",
        shutdown_callbacks.append,
    )
    monkeypatch.setenv("CSGO_INSIGHT_PORT", "19871")

    run_server.main()

    assert captured["app"] == "app.main:app"
    assert captured["kwargs"] == {
        "host": "127.0.0.1",
        "port": 19871,
        "loop": "asyncio",
        "http": "h11",
        "log_level": "info",
        "access_log": True,
    }
    assert captured["ran"] is True
    assert len(shutdown_callbacks) == 1


def test_launcher_defaults_to_the_shared_port(monkeypatch):
    """With CSGO_INSIGHT_PORT unset the listener must still use the shared default.

    The GSI sink URL resolves from the same helper, so this is what keeps CS:GO's
    state posts pointed at the port uvicorn actually binds.
    """
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, app, **kwargs):
            captured["kwargs"] = kwargs

    class FakeServer:
        def __init__(self, config):
            self.should_exit = False

        def run(self):
            pass

    monkeypatch.setattr(run_server, "_install_windows_selector_loop", lambda: None)
    monkeypatch.setattr(run_server.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(run_server.uvicorn, "Server", FakeServer)
    monkeypatch.setattr("app.shutdown_state.register_server_shutdown", lambda _cb: None)
    monkeypatch.delenv("CSGO_INSIGHT_PORT", raising=False)

    run_server.main()

    assert captured["kwargs"]["port"] == DEFAULT_BACKEND_PORT
