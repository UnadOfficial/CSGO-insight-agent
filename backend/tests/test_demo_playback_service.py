"""CS:GO-only direct demo playback service.

The old suite exercised the retired Source 2 POV pipeline (VPK install,
gameinfo.gi patching, skybox/material/weather overrides).  CS:GO playback is
deliberately much smaller: copy the demo into ``csgo/``, write a private
``+exec`` cfg, launch ``csgo.exe``, then restore player configs and delete the
temporary files once the game exits.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import demo_playback_service as playback
from app.csgo_demo_format import DemoFormatError


class _FakeProcess:
    def __init__(self):
        self.waited = 0
        self.terminated = 0

    def wait(self, timeout=None):
        self.waited += 1
        return 0

    def terminate(self):
        self.terminated += 1

    def kill(self):
        pass


class _DeferredThread:
    """Keep playback monitoring deterministic: never run the thread inline."""

    def __init__(self, *, target, args, **_kwargs):
        self.target = target
        self.args = args

    def start(self):
        return None


def _hl2demo_bytes(payload: bytes = b"") -> bytes:
    return b"HL2DEMO" + payload


def _paths(tmp_path: Path):
    game_root = tmp_path / "Counter-Strike Global Offensive"
    csgo_exe = game_root / "csgo.exe"
    csgo_exe.parent.mkdir(parents=True)
    csgo_exe.write_bytes(b"exe")
    (game_root / "csgo").mkdir()
    demo = tmp_path / "match.dem"
    demo.write_bytes(_hl2demo_bytes(b"demo"))
    return SimpleNamespace(csgo_path=str(csgo_exe)), demo, game_root


@pytest.fixture(autouse=True)
def _playback_fakes(monkeypatch):
    monkeypatch.setattr(playback, "is_csgo_running", lambda: False)
    monkeypatch.setattr(playback, "snapshot_user_configs", lambda _csgo_path: {})
    monkeypatch.setattr(playback, "write_persistent_backup_from_snap", lambda _snap: Path("backup.json"))
    monkeypatch.setattr(playback.threading, "Thread", _DeferredThread)


def test_preflight_requires_a_csgo_executable(tmp_path: Path):
    service = playback.DemoPlaybackService()
    missing = service.preflight(SimpleNamespace(csgo_path=""))

    assert missing["ok"] is False
    assert missing["csgo_path_configured"] is False
    assert missing["csgo_running"] is False
    assert missing["playback_active"] is False

    cfg, _demo, _root = _paths(tmp_path)
    ready = service.preflight(cfg)
    assert ready["ok"] is True
    assert ready["csgo_path_configured"] is True


def test_preflight_rejects_a_non_csgo_executable(tmp_path: Path):
    impostor = tmp_path / "cs2.exe"
    impostor.write_bytes(b"exe")
    result = playback.DemoPlaybackService().preflight(SimpleNamespace(csgo_path=str(impostor)))
    assert result["ok"] is False
    assert result["csgo_path_configured"] is False


def test_preflight_reports_a_running_game(monkeypatch, tmp_path: Path):
    cfg, _demo, _root = _paths(tmp_path)
    monkeypatch.setattr(playback, "is_csgo_running", lambda: True)
    result = playback.DemoPlaybackService().preflight(cfg)
    assert result["ok"] is False
    assert result["csgo_running"] is True


def test_launch_is_blocked_when_csgo_is_already_running(monkeypatch, tmp_path: Path):
    cfg, demo, _game_root = _paths(tmp_path)
    monkeypatch.setattr(playback, "is_csgo_running", lambda: True)
    monkeypatch.setattr(playback.subprocess, "Popen", pytest.fail)

    with pytest.raises(playback.DemoPlaybackCSGORunningError):
        playback.DemoPlaybackService().launch(demo, cfg)


def test_launch_rejects_a_source2_demo(monkeypatch, tmp_path: Path):
    cfg, demo, _game_root = _paths(tmp_path)
    demo.write_bytes(b"PBDEMS2" + b"\x00" * 32)
    monkeypatch.setattr(playback.subprocess, "Popen", pytest.fail)

    with pytest.raises(DemoFormatError):
        playback.DemoPlaybackService().launch(demo, cfg)


def test_launch_requires_a_real_csgo_executable(tmp_path: Path):
    demo = tmp_path / "match.dem"
    demo.write_bytes(_hl2demo_bytes(b"demo"))

    with pytest.raises(FileNotFoundError):
        playback.DemoPlaybackService().launch(demo, SimpleNamespace(csgo_path=""))


def test_normal_playback_uses_unique_demo_and_cleans_it(monkeypatch, tmp_path: Path):
    cfg, demo, game_root = _paths(tmp_path)
    calls = []
    process = _FakeProcess()

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    monkeypatch.setattr(playback.subprocess, "Popen", fake_popen)
    service = playback.DemoPlaybackService()
    result = service.launch(demo, cfg)

    session = service._active
    assert result["ok"] is True and result["session_id"]
    assert session is not None and session.copied_demo.is_file()
    # The disposable copy lives inside the CS:GO tree, never beside the source.
    assert session.copied_demo.parent == game_root / "csgo"
    assert demo.read_bytes() == _hl2demo_bytes(b"demo")

    argv, kwargs = calls[0]
    assert argv[0] == str(game_root / "csgo.exe")
    assert kwargs["cwd"] == str(game_root)
    assert kwargs["env"]["SteamAppId"] == "730"
    assert kwargs["env"]["SteamGameId"] == "730"
    # Source 1 contract: native playdemo via +exec, no Source 2 launcher flags.
    assert "+playdemo" not in argv
    assert argv[-2:] == ["+exec", session.copied_cfg.stem]
    assert session.copied_cfg.read_text(encoding="ascii") == f'playdemo "{session.copied_demo.name}"\n'
    assert session.copied_cfg.parent == game_root / "csgo" / "cfg"

    session.started_at_monotonic = time.monotonic() - 4
    service._monitor_session(session)
    assert process.waited == 1
    assert not session.copied_demo.exists()
    assert not session.copied_cfg.exists()
    assert service._active is None
    assert service.session_status(result["session_id"])["state"] == "completed"


def test_alias_copy_is_used_for_playback_then_removed(monkeypatch, tmp_path: Path):
    cfg, demo, _game_root = _paths(tmp_path)
    process = _FakeProcess()
    monkeypatch.setattr(playback.subprocess, "Popen", lambda *_args, **_kwargs: process)

    def copy(source, output, aliases):
        assert source == demo and aliases == {"76561199032006224": "京介"}
        output.write_bytes(_hl2demo_bytes(b"aliased"))
        return output

    monkeypatch.setattr(playback, "create_player_alias_copy", copy)
    service = playback.DemoPlaybackService()
    service.launch(
        demo,
        cfg,
        playback.DemoPlaybackOptions(player_aliases={"76561199032006224": "京介"}),
    )

    session = service._active
    assert session is not None
    assert session.copied_demo.read_bytes() == _hl2demo_bytes(b"aliased")
    assert demo.read_bytes() == _hl2demo_bytes(b"demo")
    session.started_at_monotonic = time.monotonic() - 4
    service._monitor_session(session)
    assert not session.copied_demo.exists()


def test_launch_is_busy_while_a_session_is_active(monkeypatch, tmp_path: Path):
    cfg, demo, _game_root = _paths(tmp_path)
    monkeypatch.setattr(playback.subprocess, "Popen", lambda *_args, **_kwargs: _FakeProcess())
    service = playback.DemoPlaybackService()
    service.launch(demo, cfg)

    with pytest.raises(playback.DemoPlaybackBusyError):
        service.launch(demo, cfg)


def test_player_configs_are_snapshotted_and_restored(monkeypatch, tmp_path: Path):
    cfg, demo, _game_root = _paths(tmp_path)
    sentinel = {tmp_path / "config.cfg": b"bind w +forward"}
    restore_calls = []
    monkeypatch.setattr(playback, "snapshot_user_configs", lambda _path: sentinel)
    monkeypatch.setattr(playback.subprocess, "Popen", lambda *_args, **_kwargs: _FakeProcess())

    def restore(snapshot):
        restore_calls.append(snapshot)
        return {"ok": True, "verified": True, "checked": 1, "restored": 1, "failed": []}

    monkeypatch.setattr(playback, "restore_user_config_snapshot", restore)
    service = playback.DemoPlaybackService()
    result = service.launch(demo, cfg)

    session = service._active
    assert session is not None
    session.started_at_monotonic = time.monotonic() - 4
    service._monitor_session(session)

    assert restore_calls == [sentinel]
    status = service.session_status(result["session_id"])
    assert status["player_config_restore"]["verified"] is True
    assert status["state"] == "completed"


def test_backup_failure_blocks_launch_and_leaves_no_artifacts(monkeypatch, tmp_path: Path):
    cfg, demo, game_root = _paths(tmp_path)
    monkeypatch.setattr(playback, "snapshot_user_configs", lambda _path: {tmp_path / "config.cfg": b"x"})
    monkeypatch.setattr(playback, "write_persistent_backup_from_snap", lambda _snap: None)
    monkeypatch.setattr(playback.subprocess, "Popen", pytest.fail)

    with pytest.raises(RuntimeError):
        playback.DemoPlaybackService().launch(demo, cfg)

    assert list((game_root / "csgo").glob("_insight_preview_*")) == []


def test_launch_failure_rolls_back_files_and_player_configs(monkeypatch, tmp_path: Path):
    cfg, demo, game_root = _paths(tmp_path)
    restored = []
    monkeypatch.setattr(playback, "snapshot_user_configs", lambda _path: {tmp_path / "config.cfg": b"x"})
    monkeypatch.setattr(
        playback,
        "restore_user_config_snapshot",
        lambda snapshot: restored.append(snapshot) or {"ok": True, "verified": True},
    )

    def boom(*_args, **_kwargs):
        raise OSError("csgo.exe refused to start")

    monkeypatch.setattr(playback.subprocess, "Popen", boom)

    with pytest.raises(OSError):
        playback.DemoPlaybackService().launch(demo, cfg)

    assert restored, "player configs must be restored after a failed launch"
    assert list((game_root / "csgo").glob("_insight_preview_*")) == []
    assert list((game_root / "csgo" / "cfg").glob("_insight_preview_*")) == []


def test_monitor_waits_for_a_short_lived_launcher(monkeypatch, tmp_path: Path):
    """Steam/launcher handoff: the process may exit before csgo.exe appears.

    ``_monitor_session`` grants a bounded grace window when the launch handle
    dies almost immediately.  A fake clock keeps the assertion deterministic
    instead of burning the real 12-second window.
    """
    cfg, demo, _game_root = _paths(tmp_path)
    clock = {"now": 1000.0}
    running = {"value": False}
    sleeps = {"count": 0}

    def sleep(seconds):
        clock["now"] += seconds
        sleeps["count"] += 1
        if sleeps["count"] == 1:
            # csgo.exe shows up shortly after the launcher process exits.
            running["value"] = True
        else:
            # ... and eventually the player closes the game.
            running["value"] = False

    monkeypatch.setattr(playback, "is_csgo_running", lambda: running["value"])
    monkeypatch.setattr(playback.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(playback.time, "sleep", sleep)
    monkeypatch.setattr(playback.subprocess, "Popen", lambda *_args, **_kwargs: _FakeProcess())

    service = playback.DemoPlaybackService()
    service.launch(demo, cfg)
    session = service._active
    assert session is not None

    service._monitor_session(session)

    assert service._active is None
    assert not session.copied_demo.exists()
