import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.csgo_demo_parser import DemoParser
from app.mirv_pov import (
    HLAE_MISSING_MSG,
    MirvPovError,
    build_hlae_launch_argv,
    is_hlae_exe,
    is_valid_entity_index,
    lock_plan_to_mirv_pov_player,
    majority_target_steamid,
    mirv_pov_cfg_lines,
    resolve_mirv_pov_entity_index,
)
from app.recording.models import (
    Perspective,
    RecordingPlan,
    RecordingSegment,
    RequestType,
    SourceType,
)


def _write_dump(root: Path) -> Path:
    dump = root / "dump"
    dump.mkdir()
    (dump / "header.json").write_text("{}", encoding="utf-8")
    (dump / "players.json").write_text(
        '[{"name":"Alice","steamid":"76561198000000001","user_id":3,"entity_id":8,"team_num":2}]',
        encoding="utf-8",
    )
    (dump / "events.jsonl").write_text("", encoding="utf-8")
    (dump / "ticks.jsonl").write_text(
        '{"tick":100,"players":[{"tick":100,"name":"Alice","steamid":"76561198000000001","entity_id":8}]}\n',
        encoding="utf-8",
    )
    return dump


def _segment(**kwargs) -> RecordingSegment:
    values = {
        "segment_index": 0,
        "source_type": SourceType.kill,
        "start_tick": 10,
        "end_tick": 20,
        "target_player_name": "Alice",
        "target_steamid64": "76561198000000001",
        "perspective": Perspective.killer,
        "safe_seek_tick": 5,
    }
    values.update(kwargs)
    return RecordingSegment(**values)


def test_resolve_entity_index_from_players_json(tmp_path: Path):
    parser = DemoParser.from_dump(_write_dump(tmp_path), demo_path="alice.dem")
    assert resolve_mirv_pov_entity_index("alice.dem", "76561198000000001", parser=parser) == 8
    assert resolve_mirv_pov_entity_index("alice.dem", "76561198000000099", parser=parser) is None


def test_resolve_entity_index_prefers_tick_snapshot(tmp_path: Path):
    parser = DemoParser.from_dump(_write_dump(tmp_path), demo_path="alice.dem")
    assert resolve_mirv_pov_entity_index(
        "alice.dem",
        "76561198000000001",
        tick=100,
        parser=parser,
    ) == 8


def test_mirv_pov_cfg_lines_precede_playdemo_contract():
    lines = mirv_pov_cfg_lines(8)
    assert lines[0] == "mirv_pov 8"
    assert "cl_show_observer_crosshair 2" in lines


def test_hlae_launch_argv_puts_mirv_pov_before_exec(tmp_path: Path):
    hlae = tmp_path / "HLAE.exe"
    csgo = tmp_path / "csgo.exe"
    hlae.write_bytes(b"mz")
    csgo.write_bytes(b"mz")
    argv = build_hlae_launch_argv(
        hlae,
        csgo,
        ["-steam", "-console", "+mirv_pov", "8", "+exec", "_insight_abc"],
    )
    assert argv[0] == str(hlae)
    assert argv[1:4] == ["-csgoLauncher", "-noGui", "-autoStart"]
    custom = argv[argv.index("-customLaunchOptions") + 1]
    assert custom.index("+mirv_pov 8") < custom.index("+exec _insight_abc")
    assert is_hlae_exe(hlae) is True
    assert is_hlae_exe(csgo) is False


def test_build_hlae_argv_rejects_missing_binary(tmp_path: Path):
    try:
        build_hlae_launch_argv(tmp_path / "missing.exe", tmp_path / "csgo.exe", [])
    except MirvPovError as exc:
        assert str(exc) == HLAE_MISSING_MSG
    else:
        raise AssertionError("expected MirvPovError")


def test_majority_target_and_lock_plan():
    class Target:
        def __init__(self, steamid64, name=""):
            self.steamid64 = steamid64
            self.name = name

    class Dto:
        def __init__(self, steamid64, name=""):
            self.target_player = Target(steamid64, name)

    assert majority_target_steamid([
        Dto("76561198000000001", "Alice"),
        Dto("76561198000000001", "Alice"),
        Dto("76561198000000002", "Bob"),
    ]) == "76561198000000001"

    plan = RecordingPlan(
        request_id="r1",
        request_type=RequestType.highlight,
        demo_path="x.dem",
        tick_rate=64.0,
        segments=[
            _segment(segment_index=0),
            _segment(
                segment_index=1,
                target_player_name="Bob",
                target_steamid64="76561198000000002",
                perspective=Perspective.victim,
            ),
        ],
    )
    skipped = lock_plan_to_mirv_pov_player(plan, "76561198000000001", "Alice")
    assert skipped == 1
    assert plan.segments[0].disabled is False
    assert plan.segments[1].disabled is True
    assert "Alice" in plan.warnings[0]


def test_invalid_entity_index():
    assert is_valid_entity_index(0) is False
    assert is_valid_entity_index(8) is True
    assert is_valid_entity_index(99) is False
