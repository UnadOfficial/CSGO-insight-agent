"""Direct Source 1 / CS:GO demo playback."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .csgo_config_backup import (
    is_csgo_running,
    restore_user_config_snapshot,
    snapshot_user_configs,
    write_persistent_backup_from_snap,
)
from .csgo_demo_format import require_csgo_demo
from .player_aliases import create_player_alias_copy

logger = logging.getLogger(__name__)

_DEMO_PLAYBACK_FORCED_ARGS = ("+cl_demo_predict", "0")


class DemoPlaybackBusyError(RuntimeError):
    """A playback launch is already active or still being cleaned up."""


class DemoPlaybackCSGORunningError(RuntimeError):
    """CS:GO is already running and must be closed before managed playback."""


@dataclass(frozen=True)
class DemoPlaybackOptions:
    """Native CS:GO playback controls."""

    player_aliases: dict[str, str] = field(default_factory=dict)


@dataclass
class DemoPlaybackSession:
    session_id: str
    process: Any
    copied_demo: Path
    copied_cfg: Optional[Path]
    player_config_snapshot: dict[Path, Optional[bytes]]
    started_at_monotonic: float


class DemoPlaybackService:
    """Own one direct-playback CS:GO session and restore player configs on exit."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: Optional[DemoPlaybackSession] = None
        self._session_reports: dict[str, dict[str, Any]] = {}

    def _set_session_report(self, session_id: str, **updates: Any) -> None:
        with self._lock:
            current = dict(self._session_reports.get(session_id) or {"session_id": session_id})
            current.update(updates)
            self._session_reports[session_id] = current
            while len(self._session_reports) > 20:
                self._session_reports.pop(next(iter(self._session_reports)), None)

    def session_status(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            report = self._session_reports.get(str(session_id))
            active = self._active
        if report is None:
            return {"found": False, "session_id": str(session_id)}
        result = dict(report)
        result["found"] = True
        result["csgo_running"] = bool(is_csgo_running())
        result["playback_active"] = active is not None and active.session_id == str(session_id)
        return result

    def preflight(self, config_like: Any) -> dict[str, Any]:
        csgo_path = str(getattr(config_like, "csgo_path", "") or "").strip()
        csgo_path_valid = bool(
            csgo_path
            and Path(csgo_path).is_file()
            and Path(csgo_path).name.lower() == "csgo.exe"
        )
        with self._lock:
            active = self._active is not None
        running = bool(is_csgo_running())
        return {
            "ok": csgo_path_valid and not active and not running,
            "csgo_path_configured": csgo_path_valid,
            "csgo_running": running,
            "playback_active": active,
            "warnings": [],
        }

    @staticmethod
    def _resolve_game_paths(csgo_path: str) -> tuple[Path, Path]:
        csgo_bin = Path(csgo_path)
        if not csgo_path or not csgo_bin.is_file() or csgo_bin.name.lower() != "csgo.exe":
            raise FileNotFoundError("CS:GO path is not configured or csgo.exe does not exist")
        game_root = csgo_bin.parent
        csgo_dir = game_root / "csgo"
        if not csgo_dir.is_dir():
            raise FileNotFoundError("Unable to find the CS:GO game/csgo directory")
        return game_root, csgo_dir

    @staticmethod
    def _cleanup_artifacts(session: DemoPlaybackSession) -> None:
        for label, path in (("preview cfg", session.copied_cfg), ("preview demo", session.copied_demo)):
            if path and path.is_file():
                try:
                    path.unlink()
                except OSError as exc:
                    logger.warning("Could not remove direct playback %s %s: %s", label, path, exc)

    @staticmethod
    def _start_player_config_protection(csgo_path: str) -> dict[Path, Optional[bytes]]:
        snapshot = snapshot_user_configs(csgo_path)
        if snapshot and write_persistent_backup_from_snap(snapshot) is None:
            raise RuntimeError("Unable to create the player config backup; playback was not started.")
        return snapshot

    @staticmethod
    def _restore_player_configs(snapshot: dict[Path, Optional[bytes]]) -> dict[str, Any]:
        if not snapshot:
            return {
                "ok": True,
                "verified": True,
                "checked": 0,
                "restored": 0,
                "failed": [],
                "source": "none",
                "state": "not_needed",
            }
        result = restore_user_config_snapshot(snapshot)
        return {**result, "state": "restored" if result.get("verified") else "restore_failed"}

    def _monitor_session(self, session: DemoPlaybackSession) -> None:
        try:
            try:
                session.process.wait()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not wait for direct playback CS:GO process: %s", exc)
            runtime = time.monotonic() - session.started_at_monotonic
            if runtime < 3.0 and not is_csgo_running():
                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline and not is_csgo_running():
                    time.sleep(0.5)
            while is_csgo_running():
                time.sleep(1.0)
            player_restore = self._restore_player_configs(session.player_config_snapshot)
            self._set_session_report(
                session.session_id,
                state="completed" if player_restore.get("verified") else "restore_failed",
                restore=None,
                player_config_restore=player_restore,
            )
        finally:
            self._cleanup_artifacts(session)
            with self._lock:
                if self._active is session:
                    self._active = None
            logger.info("Direct CS:GO playback session %s cleaned up", session.session_id)

    def launch(
        self,
        dem_path: Path,
        config_like: Any,
        options: Optional[DemoPlaybackOptions] = None,
    ) -> dict[str, Any]:
        options = options or DemoPlaybackOptions()
        dem_path = Path(dem_path)

        with self._lock:
            if self._active is not None:
                raise DemoPlaybackBusyError("A direct playback session is already active")
            if is_csgo_running():
                raise DemoPlaybackCSGORunningError("CS:GO is already running")
            if not dem_path.is_file():
                raise FileNotFoundError(f"Demo file not found: {dem_path}")
            require_csgo_demo(dem_path)

            csgo_path = str(getattr(config_like, "csgo_path", "") or "").strip()
            game_root, csgo_dir = self._resolve_game_paths(csgo_path)
            csgo_bin = Path(csgo_path)
            session_id = uuid.uuid4().hex
            copied_demo = csgo_dir / f"_insight_preview_{session_id}.dem"
            copied_cfg: Optional[Path] = None
            player_config_snapshot: dict[Path, Optional[bytes]] = {}
            session: Optional[DemoPlaybackSession] = None
            try:
                player_config_snapshot = self._start_player_config_protection(csgo_path)
                if options.player_aliases:
                    create_player_alias_copy(dem_path, copied_demo, options.player_aliases)
                else:
                    copied_demo.parent.mkdir(parents=True, exist_ok=True)
                    copied_demo.write_bytes(dem_path.read_bytes())
                # Keep direct playback on the same Source 1 cfg path as the
                # recorder.  The cfg is intentionally private and removed by
                # the monitor after csgo.exe exits.
                cfg_dir = csgo_dir / "cfg"
                cfg_dir.mkdir(parents=True, exist_ok=True)
                copied_cfg = cfg_dir / f"_insight_preview_{session_id}.cfg"
                copied_cfg.write_text(
                    f'playdemo "{copied_demo.name}"\n',
                    encoding="ascii",
                )
                if is_csgo_running():
                    raise DemoPlaybackCSGORunningError("CS:GO started during playback preparation")

                argv = [
                    str(csgo_bin),
                    "-steam",
                    "-insecure",
                    "-novid",
                    "-console",
                    *_DEMO_PLAYBACK_FORCED_ARGS,
                    "+exec",
                    copied_cfg.stem,
                ]
                child_env = os.environ.copy()
                child_env["SteamAppId"] = "730"
                child_env["SteamGameId"] = "730"
                creationflags = 0
                if sys.platform == "win32":
                    creationflags = (
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        | getattr(subprocess, "DETACHED_PROCESS", 0)
                    )
                logger.info("Launch CS:GO direct playback: cwd=%s cmd=%s", game_root, " ".join(argv))
                process = subprocess.Popen(
                    argv,
                    cwd=str(game_root),
                    env=child_env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=creationflags,
                )
                session = DemoPlaybackSession(
                    session_id=session_id,
                    process=process,
                    copied_demo=copied_demo,
                    copied_cfg=copied_cfg,
                    player_config_snapshot=player_config_snapshot,
                    started_at_monotonic=time.monotonic(),
                )
                self._active = session
                self._set_session_report(
                    session_id,
                    state="running",
                    restore=None,
                    player_config_restore=None,
                )
                threading.Thread(
                    target=self._monitor_session,
                    args=(session,),
                    name=f"demo-playback-{session_id[:8]}",
                    daemon=True,
                ).start()
                return {"ok": True, "session_id": session_id}
            except Exception:
                if session is not None:
                    if self._active is session:
                        self._active = None
                    self._session_reports.pop(session_id, None)
                    try:
                        session.process.terminate()
                        session.process.wait(timeout=10)
                    except Exception as stop_exc:  # noqa: BLE001
                        logger.error("Could not stop CS:GO after playback launch failure: %s", stop_exc)
                if player_config_snapshot:
                    self._restore_player_configs(player_config_snapshot)
                placeholder = session or DemoPlaybackSession(
                    session_id=session_id,
                    process=None,
                    copied_demo=copied_demo,
                    copied_cfg=copied_cfg,
                    player_config_snapshot=player_config_snapshot,
                    started_at_monotonic=time.monotonic(),
                )
                self._cleanup_artifacts(placeholder)
                raise


demo_playback_service = DemoPlaybackService()
