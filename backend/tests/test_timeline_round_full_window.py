"""Full-round timeline windows: freeze start → death or round end.

Run:  python -m pytest backend/tests/test_timeline_round_full_window.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.recording.models import (  # noqa: E402
    DemoContext,
    RecordingOptions,
    RecordingRequestDTO,
    RequestType,
    RoundInfo,
    SourceRef,
    SourceType,
    TargetPlayer,
)
from app.recording.plan_builder import build_plan  # noqa: E402
from app.round_timeline import build_round_timeline  # noqa: E402
from app import native_table as pd  # noqa: E402


TICK_RATE = 64.0
PLAYER = TargetPlayer(name="TestPlayer", steamid64="76561198012345678")


def _request(round_info: RoundInfo) -> RecordingRequestDTO:
    return RecordingRequestDTO(
        request_id="timeline-round-window",
        request_type=RequestType.timeline_round,
        source_type=SourceType.round,
        demo=DemoContext(
            demo_path="/demo/test.dem",
            demo_filename="test.dem",
            map_name="de_dust2",
            tick_rate=TICK_RATE,
            first_tick=0,
            demo_end_tick=100_000,
            final_round=20,
            final_round_start_tick=90_000,
            final_round_end_tick=99_000,
        ),
        target_player=PLAYER,
        rounds=[round_info],
        options=RecordingOptions(),
        source_ref=SourceRef(),
    )


def _round(
    *,
    freeze_start_tick: int | None = 9_000,
    freeze_end_tick: int = 10_000,
    round_end_tick: int = 30_000,
    next_round_start_tick: int = 30_400,
    target_death_tick: int | None = None,
) -> RoundInfo:
    return RoundInfo(
        round=5,
        round_start_tick=freeze_start_tick if freeze_start_tick is not None else freeze_end_tick,
        round_end_tick=round_end_tick,
        freeze_start_tick=freeze_start_tick,
        freeze_end_tick=freeze_end_tick,
        next_round_start_tick=next_round_start_tick,
        target_death_tick=target_death_tick,
    )


def test_timeline_round_starts_at_freeze_start():
    plan = build_plan(_request(_round()))
    assert plan.segments[0].start_tick == 9_000


def test_timeline_round_without_freeze_start_keeps_preroll():
    plan = build_plan(_request(_round(freeze_start_tick=None)))
    assert plan.segments[0].start_tick == 10_000 - int(3.0 * TICK_RATE)


def test_alive_timeline_round_keeps_three_second_result_tail():
    plan = build_plan(_request(_round()))
    assert plan.segments[0].end_tick == 30_000 + int(3.0 * TICK_RATE)
    assert plan.segments[0].metadata["end_reason"] == "round_end_post"
    assert plan.segments[0].metadata["target_death_tick"] is None


def test_dead_timeline_round_stops_at_death_plus_post():
    plan = build_plan(_request(_round(target_death_tick=20_000)))
    assert plan.segments[0].end_tick == 20_000 + int(2.0 * TICK_RATE)
    assert plan.segments[0].metadata["end_reason"] == "target_death_post"
    assert plan.segments[0].end_tick < 30_000


def test_round_ending_death_keeps_death_post_tail():
    plan = build_plan(_request(_round(target_death_tick=30_000)))
    assert plan.segments[0].end_tick == 30_000 + int(2.0 * TICK_RATE)
    assert plan.segments[0].metadata["end_reason"] == "target_death_post"


def test_alive_timeline_round_tail_stops_before_next_round():
    plan = build_plan(_request(_round(next_round_start_tick=30_100)))
    assert plan.segments[0].end_tick == 30_100 - int(0.5 * TICK_RATE)
    assert plan.segments[0].metadata["end_reason"] == "round_end_clamped_to_next_round_start"


def test_round_timeline_emits_freeze_start_and_next_round_start():
    empty = pd.DataFrame()
    bundle = build_round_timeline(
        demo_path="x.dem",
        map_name="de_dust2",
        target_player="P",
        target_player_user_id=1,
        target_steam_id="1",
        target_team_num=2,
        round_target_team_map={1: 2, 2: 2},
        events=empty,
        round_freeze_end_ticks={1: 1000, 2: 5000},
        round_freeze_start_ticks={1: 100, 2: 4000},
        round_result_map={1: True},
        round_scores_by_round={1: {2: 0, 3: 0}, 2: {2: 1, 3: 0}},
        round_end_df=empty,
        round_end_tick_map={1: 3000, 2: 8000},
        clips=[],
        total_rounds=2,
        match_start_tick=0,
        tick_rate=64.0,
    )
    row = bundle["round_timeline"][0]
    assert row["freeze_start_tick"] == 100
    assert row["freeze_end_tick"] == 1000
    assert row["next_round_start_tick"] == 4000
    assert row["next_round_freeze_end_tick"] == 5000
    last = bundle["round_timeline"][1]
    assert last["next_round_start_tick"] is None


def test_round_timeline_assigns_kills_from_freeze_windows_without_event_counter():
    empty = pd.DataFrame()
    events = pd.DataFrame(
        [
            {
                "tick": 1500,
                "attacker_name": "P",
                "user_name": "enemy-one",
                "weapon": "ak47",
                "headshot": 0,
            },
            {
                "tick": 6000,
                "total_rounds_played": 0,
                "attacker_name": "P",
                "user_name": "enemy-two",
                "weapon": "ak47",
                "headshot": 0,
            },
        ]
    )
    bundle = build_round_timeline(
        demo_path="x.dem",
        map_name="de_dust2",
        target_player="P",
        target_player_user_id=1,
        target_steam_id="1",
        target_team_num=2,
        round_target_team_map={1: 2, 2: 2},
        events=events,
        round_freeze_end_ticks={1: 1000, 2: 5000},
        round_freeze_start_ticks={1: 100, 2: 4000},
        round_result_map={1: True, 2: True},
        round_scores_by_round={1: {2: 0, 3: 0}, 2: {2: 1, 3: 0}},
        round_end_df=empty,
        round_end_tick_map={1: 3000, 2: 8000},
        clips=[],
        total_rounds=2,
        match_start_tick=0,
        tick_rate=64.0,
    )
    round_one = bundle["round_timeline"][0]["events"]
    round_two = bundle["round_timeline"][1]["events"]
    assert [event["victim_name"] for event in round_one] == ["enemy-one"]
    assert [event["round"] for event in round_one] == [1]
    assert [event["victim_name"] for event in round_two] == ["enemy-two"]
    assert [event["round"] for event in round_two] == [2]
