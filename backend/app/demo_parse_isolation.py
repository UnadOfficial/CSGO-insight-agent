"""Run demoparser work in a child process so native crashes do not kill FastAPI."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)
_REPLAY_ATTACH_MARGIN_SECS = 5.0
_REPLAY_ATTACH_MIN_SECS = 20.0


class IsolatedParseError(RuntimeError):
    pass


def _timeout_seconds(action: str) -> float:
    if action in {"players", "summary", "inspect"}:
        env_name = "CS2_INSIGHT_DEMO_INSPECT_TIMEOUT_SEC"
        default = "30"
    else:
        env_name = "CS2_INSIGHT_PARSE_WORKER_TIMEOUT_SEC"
        default = "240"
    raw = (os.environ.get(env_name) or default).strip()
    try:
        return max(10.0, float(raw))
    except ValueError:
        return float(default)


def _parse_worker_dir() -> Path:
    """Keep worker scratch files on the app data volume, not %TEMP% on C:."""
    try:
        from .env_utils import get_data_dir

        tmp_dir = get_data_dir() / "tmp" / "parse-workers"
    except Exception:
        tmp_dir = Path(tempfile.gettempdir()) / "cs2_insight_parse_workers"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def run_parse_worker(action: str, *, timeout: float | None = None, **payload: Any) -> Any:
    req = {"action": action, **payload}
    worker_timeout = _timeout_seconds(action) if timeout is None else max(10.0, float(timeout))
    tmp_dir = _parse_worker_dir()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=tmp_dir, delete=False) as rf:
        json.dump(req, rf, ensure_ascii=False)
        req_path = Path(rf.name)
    out_path = tmp_dir / f"{req_path.stem}.out.json"
    err_path = tmp_dir / f"{req_path.stem}.err.txt"
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    worker_path = Path(__file__).with_name("parse_worker.py")
    cmd = [sys.executable, str(worker_path), str(req_path), str(out_path)]
    started = time.monotonic()
    logger.info("Parse worker starting action=%s timeout=%.0fs", action, worker_timeout)
    try:
        with err_path.open("w", encoding="utf-8", errors="replace") as err_file:
            cp = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=err_file,
                text=False,
                timeout=worker_timeout,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        logger.info(
            "Parse worker finished action=%s elapsed=%.1fs returncode=%s",
            action,
            time.monotonic() - started,
            cp.returncode,
        )
    except subprocess.TimeoutExpired as e:
        logger.warning("Parse worker timed out action=%s after %.0fs", action, worker_timeout)
        for stale_path in (err_path, out_path):
            try:
                stale_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise IsolatedParseError(f"解析超时（>{worker_timeout:.0f}s），worker 已被终止") from e
    finally:
        try:
            req_path.unlink()
        except OSError:
            pass

    stderr_tail = ""
    try:
        stderr_tail = err_path.read_text(encoding="utf-8", errors="replace")[-2000:].strip()
    except OSError:
        pass
    finally:
        try:
            err_path.unlink()
        except OSError:
            pass

    if cp.returncode != 0:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        detail = f"解析 worker 退出码 {cp.returncode}"
        if stderr_tail:
            detail += f": {stderr_tail}"
        raise IsolatedParseError(detail)
    if not out_path.is_file():
        raise IsolatedParseError("解析 worker 未返回结果")
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    finally:
        try:
            out_path.unlink()
        except OSError:
            pass
    if not data.get("ok"):
        raise IsolatedParseError(str(data.get("error") or "解析失败"))
    return data.get("result")


def analyze_demo_isolated(
    dem_path: str,
    target_player: str,
    freeze_to_death_rounds: Optional[list[int]] = None,
) -> dict:
    result = run_parse_worker(
        "analyze",
        dem_path=dem_path,
        target_player=target_player,
        freeze_to_death_rounds=freeze_to_death_rounds,
    )
    if not isinstance(result, dict):
        raise IsolatedParseError("解析 worker 返回了无效结果")
    return result


def get_player_list_isolated(dem_path: str) -> list[dict]:
    result = run_parse_worker("players", dem_path=dem_path)
    if not isinstance(result, list):
        raise IsolatedParseError("玩家列表 worker 返回了无效结果")
    return result


def get_demo_match_summary_isolated(dem_path: str) -> dict:
    result = run_parse_worker("summary", dem_path=dem_path)
    if not isinstance(result, dict):
        raise IsolatedParseError("Demo 摘要 worker 返回了无效结果")
    return result


def inspect_demo_isolated(dem_path: str) -> dict:
    result = run_parse_worker("inspect", dem_path=dem_path)
    if not isinstance(result, dict):
        raise IsolatedParseError("Demo 检查 worker 返回了无效结果")
    players = result.get("players")
    match_meta = result.get("match_meta")
    if not isinstance(players, list) or not isinstance(match_meta, dict):
        raise IsolatedParseError("Demo 检查 worker 缺少玩家名单或比赛摘要")
    return result


def extract_radar_timeline_isolated(**kwargs: Any) -> Any:
    """parse_ticks 雷达时间线（子进程隔离，避免 demoparser 原生崩溃拖垮服务）。"""
    return run_parse_worker("radar_timeline", **kwargs)


def extract_replay_effects_isolated(**kwargs: Any) -> Any:
    """烟雾/燃烧效果轨（子进程隔离）。"""
    return run_parse_worker("replay_effects", **kwargs)


def materialize_match_replay_parquet_isolated(
    demo_path: str,
    workspace: dict[str, Any],
    *,
    fps: float = 32.0,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Build the whole-match Rust Parquet cache without risking the API process."""
    result = run_parse_worker(
        "materialize_replay",
        timeout=timeout,
        dem_path=demo_path,
        workspace=workspace,
        fps=float(fps),
    )
    if not isinstance(result, dict):
        raise IsolatedParseError("回放 Parquet worker 返回了无效结果")
    return result


def _attach_replay_cache(
    dem_path: str,
    result: dict[str, Any],
    *,
    started_at: float | None = None,
) -> dict[str, Any]:
    """Rebuild replay Parquet in a fresh worker after analysis RSS is gone.

    Windows does not reliably return a 4–6GB working set after ``gc.collect()``.
    The analysis ``python.exe`` must exit first, then this second process maps
    the demo again for 32 Hz replay + utility effects.
    """
    workspace = result.get("__analysis_workspace__")
    if not isinstance(workspace, dict) or not workspace.get("rounds"):
        return result
    workspace = dict(workspace)
    budget = _timeout_seconds("analyze_batch")
    elapsed = (time.monotonic() - started_at) if started_at is not None else 0.0
    remaining = budget - elapsed - _REPLAY_ATTACH_MARGIN_SECS
    if remaining < _REPLAY_ATTACH_MIN_SECS:
        logger.info(
            "Skipping replay materialize after analysis elapsed=%.1fs remaining=%.1fs",
            elapsed,
            remaining,
        )
        workspace["replay_cache"] = {
            "status": "skipped",
            "error": "analysis used the worker budget; replay cache will build on demand",
        }
        result = dict(result)
        result["__analysis_workspace__"] = workspace
        return result
    try:
        workspace["replay_cache"] = materialize_match_replay_parquet_isolated(
            dem_path,
            workspace,
            timeout=remaining,
        )
    except IsolatedParseError as exc:
        workspace["replay_cache"] = {
            "status": "error",
            "error": str(exc),
        }
    result = dict(result)
    result["__analysis_workspace__"] = workspace
    return result


def analyze_multi_isolated(
    dem_path: str,
    target_players: list[str],
    freeze_to_death_rounds: Optional[list[int]] = None,
) -> dict:
    """
    Run multi-player shared parsing in an isolated subprocess.
    Returns {player_name: ParseResult.to_dict()} for all players.
    ~10x fewer demo file scans vs calling analyze_demo_isolated per player.
    """
    started_at = time.monotonic()
    result = run_parse_worker(
        "analyze_batch",
        dem_path=dem_path,
        target_players=target_players,
        freeze_to_death_rounds=freeze_to_death_rounds,
    )
    if not isinstance(result, dict):
        raise IsolatedParseError("多玩家解析 worker 返回了无效结果")
    return _attach_replay_cache(dem_path, result, started_at=started_at)
