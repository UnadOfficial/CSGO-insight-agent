import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from ...win_cs2_console import inject_console_sequence
except ImportError:
    def inject_console_sequence(lines): pass

async def spec_player(player_name: str, mode: int = 5) -> None:
    """
    Send spec_mode + spec_player commands to CS2.
    mode: 5 = first-person (POV), 4 = chase/third-person, 1 = free
    """
    # Nicknames are display data, never console commands. Numeric-slot selection
    # remains the normal route (and works for every legal nickname). If an old
    # request has no slot, fail closed for names the console cannot quote safely.
    if not player_name.strip() or any(char in player_name for char in '\x00\r\n;"\\'):
        raise ValueError("此昵称不能用于控制台名称回退；请重新解析 Demo，使用玩家槽位录制。")
    cmds = [f"spec_mode {int(mode)}", f'spec_player "{player_name}"']
    try:
        await asyncio.to_thread(inject_console_sequence, cmds)
    except Exception as e:
        logger.warning("spec_player %s failed: %s", player_name, e)
    # Wait for spec switch to settle
    await asyncio.sleep(0.8)

STEAM_ID64_BASE = 76561197960265728


def steamid64_to_account_id(steamid64: str | int | None) -> int | None:
    raw = str(steamid64 or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw.isdigit():
        return None
    value = int(raw)
    if value > STEAM_ID64_BASE:
        value -= STEAM_ID64_BASE
    if value <= 0:
        return None
    return value


async def spec_by_accountid(steamid64: str, mode: int = 5, settle: float = 0.8) -> bool:
    """Prefer CS:GO spec_player_by_accountid when a SteamID64 is known."""
    account_id = steamid64_to_account_id(steamid64)
    if account_id is None:
        return False
    cmds = [f"spec_mode {int(mode)}", f"spec_player_by_accountid {account_id}"]
    try:
        await asyncio.to_thread(inject_console_sequence, cmds)
    except Exception as e:
        logger.warning("spec_player_by_accountid %s failed: %s", account_id, e)
        return False
    if settle > 0:
        await asyncio.sleep(settle)
    return True


async def spec_by_slot(slot: int, mode: int = 5, settle: float = 0.8) -> None:
    """Send spec_mode + spec_player by numeric slot."""
    cmds = [f"spec_mode {mode}", f"spec_player {int(slot)}"]
    try:
        await asyncio.to_thread(inject_console_sequence, cmds)
    except Exception as e:
        logger.warning("spec_player slot %s failed: %s", slot, e)
    if settle > 0:
        await asyncio.sleep(settle)
