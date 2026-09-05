from __future__ import annotations

import json
from pathlib import Path

from app.csgo_demo_parser import DemoParser
from app.csgo_demo_parser.replay_binary import MAGIC, encode_replay_binary
from app.features.demo_analysis.clip_builder import (
    infer_regulation_maxrounds,
    is_mr12_regulation_decided_score,
    is_post_match_round,
)


def _write_dump(root: Path) -> Path:
    dump = root / "dump"
    dump.mkdir()
    (dump / "header.json").write_text(
        json.dumps({"map_name": "de_dust2", "tick_rate": 128.0, "tickrate": 128.0}),
        encoding="utf-8",
    )
    (dump / "players.json").write_text(
        json.dumps([{"name": "Alice", "steamid": "76561198000000001", "team_number": 2, "user_id": 2}]),
        encoding="utf-8",
    )
    events = [
        {
            "event_name": "player_death",
            "tick": 100,
            "user_name": "Bob",
            "user_steamid": "76561198000000002",
            "attacker_name": "Alice",
            "attacker_steamid": "76561198000000001",
            "weapon": "ak47",
            "headshot": 1,
        },
        {"event_name": "round_freeze_end", "tick": 64},
        {"event_name": "smokegrenade_detonate", "tick": 120, "x": 1.0, "y": 2.0, "z": 3.0},
    ]
    (dump / "events.jsonl").write_text(
        "\n".join(json.dumps(item) for item in events) + "\n",
        encoding="utf-8",
    )
    ticks = [
        {
            "tick": 100,
            "players": [
                {
                    "tick": 100,
                    "name": "Alice",
                    "steamid": "76561198000000001",
                    "team_num": 2,
                    "X": 10.0,
                    "Y": 20.0,
                    "Z": 0.0,
                    "yaw": 90.0,
                    "is_alive": True,
                    "health": 100,
                    "armor": 100,
                    "has_helmet": True,
                    "balance": 2700,
                    "current_equip_value": 5000,
                    "inventory": ["ak47"],
                    "active_weapon": "ak47",
                    "active_weapon_name": "ak47",
                    "has_defuser": False,
                    "has_c4": False,
                    "flash_duration": 0.0,
                }
            ],
        }
    ]
    (dump / "ticks.jsonl").write_text(
        "\n".join(json.dumps(item) for item in ticks) + "\n",
        encoding="utf-8",
    )
    return dump


def test_parser_from_dump_events(tmp_path: Path):
    parser = DemoParser.from_dump(_write_dump(tmp_path))
    header = parser.parse_header()
    assert header["map_name"] == "de_dust2"
    assert header["tick_rate"] == 128.0
    deaths = parser.parse_event("player_death")
    assert deaths["attacker_name"] == ["Alice"]
    assert deaths["weapon"] == ["ak47"]
    ticks = parser.parse_ticks(["name", "X"], ticks=[100])
    assert ticks["name"] == ["Alice"]
    assert ticks["X"] == [10.0]


def test_replay_binary_magic():
    frame = {
        "tick": [10, 10],
        "steamid": ["76561198000000001", "76561198000000002"],
        "name": ["A", "B"],
        "team_num": [2, 3],
        "is_alive": [True, True],
        "has_helmet": [False, True],
        "has_defuser": [False, False],
        "has_c4": [False, False],
        "health": [100, 80],
        "armor": [0, 100],
        "balance": [800, 800],
        "current_equip_value": [200, 200],
        "X": [1.0, 2.0],
        "Y": [3.0, 4.0],
        "Z": [0.0, 0.0],
        "yaw": [0.0, 90.0],
        "flash_duration": [0.0, 0.0],
        "inventory": ["[]", "[]"],
        "active_weapon": ["ak47", "m4a1"],
        "active_weapon_name": ["ak47", "m4a1"],
        "player_color": ["blue", "green"],
    }
    packet = encode_replay_binary(frame, [10], {"fps": 32, "frame_count": 1})
    assert packet.startswith(MAGIC)


def test_mr15_not_decided_at_13_11():
    assert is_mr12_regulation_decided_score(13, 11) is False
    assert is_mr12_regulation_decided_score(16, 14) is True
    assert is_mr12_regulation_decided_score(13, 11, maxrounds=12) is True
    assert infer_regulation_maxrounds(final_scoreline=(16, 12)) == 15
    assert is_post_match_round(
        20, 13, 11, completed_rounds=20, final_scoreline=None
    ) is False
    assert is_post_match_round(
        31, 16, 14, completed_rounds=30, final_scoreline=(16, 14)
    ) is True
