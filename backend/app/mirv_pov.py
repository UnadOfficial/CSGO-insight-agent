"""HLAE mirv_pov helpers for CS:GO GOTV recording.

mirv_pov must be set before the demo loads. It uses the engine entity index,
not spec_player slot or server user id.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .csgo_demo_parser import DemoParser

HLAE_MISSING_MSG = (
    "未找到 HLAE.exe。请先安装 HLAE（https://github.com/advancedfx/advancedfx），"
    "并在设置中填写 HLAE.exe 完整路径。"
)
HLAE_ENTITY_MISSING_MSG = (
    "无法从 Demo 解析目标玩家的实体编号（entity index）。"
    "请重新解析 Demo 后再开启 mirv_pov 录制。"
)
HLAE_TARGET_MISSING_MSG = "无法确定 mirv_pov 目标玩家（缺少 SteamID）。"


class MirvPovError(RuntimeError):
    """Raised when HLAE mirv_pov cannot be prepared for a recording session."""


def _steamid_key(value: object) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    return raw


def is_valid_entity_index(value: object) -> bool:
    try:
        index = int(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return 1 <= index <= 64


def is_hlae_exe(path: str | Path | None) -> bool:
    if not path:
        return False
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved.is_file() and resolved.name.lower() == "hlae.exe"


def detect_hlae_path() -> Optional[str]:
    """Return a usable HLAE.exe path, or None."""
    env = (os.environ.get("CSGO_INSIGHT_HLAE") or os.environ.get("HLAE_PATH") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    local_app = os.environ.get("LOCALAPPDATA") or ""
    user_profile = os.environ.get("USERPROFILE") or ""
    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    program_files_x86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    for raw in (
        Path(program_files) / "HLAE" / "HLAE.exe",
        Path(program_files_x86) / "HLAE" / "HLAE.exe",
        Path(r"C:\HLAE\HLAE.exe"),
        Path(r"D:\HLAE\HLAE.exe"),
        Path(r"E:\HLAE\HLAE.exe"),
        Path(local_app) / "HLAE" / "HLAE.exe" if local_app else None,
        Path(user_profile) / "HLAE" / "HLAE.exe" if user_profile else None,
        Path(user_profile) / "Downloads" / "HLAE" / "HLAE.exe" if user_profile else None,
    ):
        if raw is not None:
            candidates.append(raw)
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if is_hlae_exe(resolved):
            return str(resolved)
    return None


def majority_target_steamid(requests: Iterable[Any]) -> Optional[str]:
    """Pick the SteamID that owns the most recording requests in one demo group."""
    counts: Counter[str] = Counter()
    for dto in requests:
        target = getattr(dto, "target_player", None)
        steamid = _steamid_key(getattr(target, "steamid64", "") if target is not None else "")
        if steamid:
            counts[steamid] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _entity_from_columns(columns: dict[str, list[Any]], steamid64: str) -> Optional[int]:
    wanted = _steamid_key(steamid64)
    if not wanted:
        return None
    steamids = columns.get("steamid") or []
    entities = columns.get("entity_id") or []
    for steam, entity in zip(steamids, entities):
        if _steamid_key(steam) != wanted:
            continue
        if is_valid_entity_index(entity):
            return int(entity)
    return None


def resolve_mirv_pov_entity_index(
    demo_path: str | Path,
    steamid64: str,
    *,
    tick: int | None = None,
    parser: DemoParser | None = None,
) -> Optional[int]:
    """Return the HLAE mirv_pov entity index for a SteamID64."""
    wanted = _steamid_key(steamid64)
    if not wanted:
        return None
    demo_parser = parser or DemoParser(str(demo_path))
    if tick is not None:
        try:
            from_ticks = _entity_from_columns(
                demo_parser.parse_ticks(["steamid", "entity_id"], ticks=[int(tick)]),
                wanted,
            )
        except Exception:
            from_ticks = None
        if from_ticks is not None:
            return from_ticks
    try:
        return _entity_from_columns(demo_parser.parse_player_info(), wanted)
    except Exception:
        return None


def mirv_pov_cfg_lines(entity_index: int) -> list[str]:
    """Console lines that must run before playdemo."""
    if not is_valid_entity_index(entity_index):
        raise MirvPovError(HLAE_ENTITY_MISSING_MSG)
    return [
        f"mirv_pov {int(entity_index)}",
        "cl_show_observer_crosshair 2",
    ]


def build_hlae_launch_argv(
    hlae_exe: str | Path,
    csgo_exe: str | Path,
    custom_launch_options: Sequence[str],
) -> list[str]:
    """HLAE -csgoLauncher argv. custom_launch_options become one -customLaunchOptions string."""
    if not is_hlae_exe(hlae_exe):
        raise MirvPovError(HLAE_MISSING_MSG)
    custom = " ".join(str(part).strip() for part in custom_launch_options if str(part).strip())
    return [
        str(Path(hlae_exe)),
        "-csgoLauncher",
        "-noGui",
        "-autoStart",
        "-avoidVac",
        "true",
        "-csgoExe",
        str(Path(csgo_exe)),
        "-customLaunchOptions",
        custom,
    ]


def lock_plan_to_mirv_pov_player(plan: Any, steamid64: str, player_name: str = "") -> int:
    """Disable segments that are not the locked mirv_pov player. Returns skipped count."""
    wanted = _steamid_key(steamid64)
    skipped = 0
    label = (player_name or wanted or "target").strip()
    for segment in getattr(plan, "segments", []) or []:
        if getattr(segment, "disabled", False):
            continue
        if _steamid_key(getattr(segment, "target_steamid64", "")) == wanted:
            continue
        segment.disabled = True
        segment.disabled_reason = f"mirv_pov locked to {label}"
        skipped += 1
    if skipped:
        warnings = getattr(plan, "warnings", None)
        if isinstance(warnings, list):
            warnings.append(
                f"mirv_pov 已锁定 {label}，已跳过 {skipped} 个其他玩家视角片段"
            )
    return skipped
