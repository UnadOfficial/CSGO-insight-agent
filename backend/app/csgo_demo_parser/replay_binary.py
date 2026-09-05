"""Encode 2D replay frames into the CS2RPL01 packet the frontend already decodes."""

from __future__ import annotations

import json
import math
import struct
from typing import Any, Mapping, Sequence

MAGIC = b"CS2RPL01"
VERSION = 1


def _align(value: int, boundary: int) -> int:
    return math.ceil(value / boundary) * boundary


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _f(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return default if not math.isfinite(parsed) else parsed


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none", "null", "undefined"} else text


def _string_id(table: dict[str, int], value: Any) -> int:
    text = _text(value)
    existing = table.get(text)
    if existing is not None:
        return existing
    index = len(table)
    table[text] = index
    return index


def _column_values(frame: Mapping[str, Sequence[Any]], name: str, count: int) -> list[Any]:
    values = frame.get(name)
    if values is None:
        return [None] * count
    out = list(values)
    if len(out) < count:
        out.extend([None] * (count - len(out)))
    return out[:count]


def encode_replay_binary(
    frame: Mapping[str, Sequence[Any]],
    sample_ticks: Sequence[int],
    metadata: dict[str, Any],
) -> bytes:
    ticks = [int(tick) for tick in sample_ticks]
    frame_count = len(ticks)
    row_tick = _column_values(frame, "tick", len(next(iter(frame.values()), [])))
    row_count = len(row_tick)
    groups: dict[int, list[int]] = {}
    for index, tick in enumerate(row_tick):
        groups.setdefault(_i(tick), []).append(index)

    offsets = [0]
    selected_rows: list[int] = []
    for tick in ticks:
        rows = groups.get(tick) or []
        selected_rows.extend(rows)
        offsets.append(len(selected_rows))
    packed_rows = len(selected_rows)

    strings: dict[str, int] = {"": 0}

    def take(name: str) -> list[Any]:
        values = _column_values(frame, name, row_count)
        return [values[index] for index in selected_rows]

    steamid = take("steamid")
    names = take("name")
    team_num = take("team_num")
    is_alive = take("is_alive")
    has_helmet = take("has_helmet")
    has_defuser = take("has_defuser")
    has_c4 = take("has_c4")
    health = take("health")
    armor = take("armor")
    balance = take("balance")
    equip = take("current_equip_value")
    xs = take("X")
    ys = take("Y")
    zs = take("Z")
    yaws = take("yaw")
    flash = take("flash_duration")
    inventory = take("inventory")
    active = take("active_weapon")
    active_name = take("active_weapon_name")
    color = take("player_color")

    name_ids = [_string_id(strings, value) for value in names]
    inv_ids: list[int] = []
    for item in inventory:
        if isinstance(item, (list, tuple)):
            encoded = json.dumps([_text(part) for part in item], ensure_ascii=False)
        elif isinstance(item, str) and item.startswith("["):
            encoded = item
        elif item in (None, ""):
            encoded = "[]"
        else:
            encoded = json.dumps([_text(item)], ensure_ascii=False)
        inv_ids.append(_string_id(strings, encoded))
    active_ids = [_string_id(strings, value) for value in active]
    active_name_ids = [_string_id(strings, value) for value in active_name]
    color_ids = [_string_id(strings, value) for value in color]

    ordered_strings = [""] * len(strings)
    for text, index in strings.items():
        ordered_strings[index] = text

    header = dict(metadata)
    header["protocol"] = "CS2RPL01"
    header["frame_count"] = frame_count
    header["row_count"] = packed_rows
    header["strings"] = ordered_strings
    header_json = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    parts: list[bytes] = [MAGIC, struct.pack("<HI", VERSION, len(header_json)), header_json]
    cursor = 16 + len(header_json)

    def pad(boundary: int) -> None:
        nonlocal cursor
        needed = _align(cursor, boundary) - cursor
        if needed:
            parts.append(b"\x00" * needed)
            cursor += needed

    def add(fmt: str, values: Sequence[Any], boundary: int) -> None:
        nonlocal cursor
        pad(boundary)
        packed = struct.pack("<" + (fmt * len(values)), *values) if values else b""
        parts.append(packed)
        cursor += len(packed)

    add("i", ticks, 4)
    add("I", offsets, 4)
    pad(8)
    steam_vals: list[int] = []
    for value in steamid:
        text = _text(value)
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
        try:
            steam_vals.append(int(text) if text else 0)
        except ValueError:
            steam_vals.append(0)
    add("Q", steam_vals, 8)
    add("I", name_ids, 4)
    add("b", [_i(value, 0) for value in team_num], 1)
    flags: list[int] = []
    for alive, helmet, defuser, c4 in zip(is_alive, has_helmet, has_defuser, has_c4):
        bit = 0
        if alive in (True, 1, "1", "true", "True"):
            bit |= 1
        if helmet in (True, 1, "1", "true", "True"):
            bit |= 2
        if defuser in (True, 1, "1", "true", "True"):
            bit |= 4
        if c4 in (True, 1, "1", "true", "True"):
            bit |= 8
        flags.append(bit)
    add("B", flags, 1)
    add("H", [max(0, min(65535, _i(value))) for value in health], 2)
    add("H", [max(0, min(65535, _i(value))) for value in armor], 2)
    add("i", [_i(value) for value in balance], 4)
    add("i", [_i(value) for value in equip], 4)
    add("f", [_f(value) for value in xs], 4)
    add("f", [_f(value) for value in ys], 4)
    add("f", [_f(value) for value in zs], 4)
    add("f", [_f(value) for value in yaws], 4)
    add("f", [_f(value) for value in flash], 4)
    add("I", inv_ids, 4)
    add("I", active_ids, 4)
    add("I", active_name_ids, 4)
    add("I", color_ids, 4)
    return b"".join(parts)
