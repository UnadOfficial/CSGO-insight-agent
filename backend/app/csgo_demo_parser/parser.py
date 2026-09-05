"""Load a CS:GO demo via the Go extractor dump, exposing a demoparser2-like API."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..csgo_demo_format import DemoFormatError, read_hl2demo_header, require_csgo_demo
from ..env_utils import get_data_dir
from .replay_binary import encode_replay_binary

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "csgo-extract-1"
_EXTRACTOR_NAMES = ("csgo-demo-extract.exe", "csgo-demo-extract")


def resolve_extractor_path() -> Path | None:
    configured = (
        os.environ.get("CSGO_INSIGHT_DEMO_EXTRACT")
        or os.environ.get("CS2_INSIGHT_DEMO_EXTRACT")
        or ""
    ).strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    repo_root = Path(__file__).resolve().parents[3]
    tools_dir = repo_root / "tools" / "csgo-demo-extract"
    candidates.extend(
        [
            tools_dir / name
            for name in _EXTRACTOR_NAMES
        ]
    )
    candidates.append(tools_dir / "csgo-demo-extract.exe")
    bundled = Path(sys.executable).resolve().parent.parent / "tools" / "csgo-demo-extract"
    candidates.extend(bundled / name for name in _EXTRACTOR_NAMES)
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return resolved
    which = shutil.which("csgo-demo-extract") or shutil.which("csgo-demo-extract.exe")
    return Path(which) if which else None


def extractor_version_output(path: Path | None = None) -> str | None:
    binary = path or resolve_extractor_path()
    if binary is None:
        return None
    try:
        completed = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    return text.splitlines()[0].strip() if text else None


class DemoParser:
    """demoparser2-compatible facade over a one-shot CS:GO extractor dump."""

    def __init__(self, path: str, *, dump_dir: str | Path | None = None):
        self.path = str(path)
        self.demo_path = self.path
        if dump_dir is not None:
            self._dump_dir = Path(dump_dir)
            self._ensure_dump_loaded()
            return
        require_csgo_demo(self.path)
        self._dump_dir = self._cache_dir_for(self.path)
        self._header: dict[str, Any] | None = None
        self._events: dict[str, list[dict[str, Any]]] | None = None
        self._ticks: dict[int, list[dict[str, Any]]] | None = None
        self._tick_order: list[int] | None = None
        self._players: list[dict[str, Any]] | None = None

    @classmethod
    def from_dump(cls, dump_dir: str | Path, demo_path: str = "synthetic.dem") -> "DemoParser":
        parser = object.__new__(cls)
        parser.path = demo_path
        parser.demo_path = demo_path
        parser._dump_dir = Path(dump_dir)
        parser._header = None
        parser._events = None
        parser._ticks = None
        parser._tick_order = None
        parser._players = None
        parser._ensure_dump_loaded()
        return parser

    def _cache_dir_for(self, demo_path: str) -> Path:
        stat = Path(demo_path).stat()
        key = f"{EXTRACTOR_VERSION}|{os.path.normcase(str(Path(demo_path).resolve()))}|{stat.st_size}|{stat.st_mtime_ns}"
        digest = hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()[:40]
        return get_data_dir() / "csgo-demo-extract" / digest

    def _dump_ready(self) -> bool:
        return (
            (self._dump_dir / "header.json").is_file()
            and (self._dump_dir / "events.jsonl").is_file()
            and (self._dump_dir / "ticks.jsonl").is_file()
        )

    def _ensure_extracted(self) -> None:
        if self._dump_ready():
            return
        binary = resolve_extractor_path()
        if binary is None:
            raise RuntimeError(
                "CS:GO demo extractor is not installed. Build tools/csgo-demo-extract "
                "(go build) or set CSGO_INSIGHT_DEMO_EXTRACT to the binary."
            )
        self._dump_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [str(binary), "--demo", self.path, "--out", str(self._dump_dir)],
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 or not self._dump_ready():
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"CS:GO demo extractor failed (exit {completed.returncode}): {detail or 'no dump written'}"
            )

    def _ensure_dump_loaded(self) -> None:
        if self._events is not None:
            return
        if not self._dump_ready():
            self._ensure_extracted()
        self._header = json.loads((self._dump_dir / "header.json").read_text(encoding="utf-8"))
        players_path = self._dump_dir / "players.json"
        self._players = json.loads(players_path.read_text(encoding="utf-8")) if players_path.is_file() else []
        events: dict[str, list[dict[str, Any]]] = {}
        with (self._dump_dir / "events.jsonl").open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                name = str(row.get("event_name") or "")
                events.setdefault(name, []).append(row)
        self._events = events
        ticks: dict[int, list[dict[str, Any]]] = {}
        order: list[int] = []
        with (self._dump_dir / "ticks.jsonl").open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                tick = int(payload.get("tick") or 0)
                players = payload.get("players") or []
                ticks[tick] = list(players) if isinstance(players, list) else []
                order.append(tick)
        self._ticks = ticks
        self._tick_order = order

    def parse_header(self) -> dict[str, Any]:
        try:
            self._ensure_dump_loaded()
            return dict(self._header or {})
        except Exception:
            return dict(read_hl2demo_header(self.path))

    def parse_player_info(self) -> dict[str, list[Any]]:
        self._ensure_dump_loaded()
        rows = list(self._players or [])
        return _records_to_columns(rows)

    def parse_event(self, event_name: str, **_kwargs: Any) -> dict[str, list[Any]]:
        self._ensure_dump_loaded()
        rows = list((self._events or {}).get(str(event_name), []))
        return _records_to_columns(rows)

    def parse_events(
        self,
        event_names: Sequence[str],
        player: Sequence[str] | None = None,
        other: Sequence[str] | None = None,
    ) -> list[tuple[str, dict[str, list[Any]]]]:
        del player, other
        return [(str(name), self.parse_event(str(name))) for name in event_names]

    def parse_ticks(
        self,
        wanted: Sequence[str],
        ticks: Sequence[int] | None = None,
        players: Sequence[Any] | None = None,
    ) -> dict[str, list[Any]]:
        del players
        self._ensure_dump_loaded()
        wanted_fields = [str(name) for name in wanted]
        if "tick" not in wanted_fields:
            wanted_fields = ["tick", *wanted_fields]
        selected = self._select_tick_rows(ticks)
        columns: dict[str, list[Any]] = {name: [] for name in wanted_fields}
        for row in selected:
            for name in wanted_fields:
                columns[name].append(row.get(name))
        return columns

    def _select_tick_rows(self, ticks: Sequence[int] | None) -> list[dict[str, Any]]:
        stored = self._ticks or {}
        order = self._tick_order or []
        if not ticks:
            rows: list[dict[str, Any]] = []
            for tick in order:
                rows.extend(stored.get(tick) or [])
            return rows
        out: list[dict[str, Any]] = []
        for raw in ticks:
            tick = int(raw)
            rows = stored.get(tick)
            if rows is None and order:
                nearest = min(order, key=lambda sample: abs(sample - tick))
                rows = stored.get(nearest) or []
                patched = []
                for row in rows:
                    copy = dict(row)
                    copy["tick"] = tick
                    patched.append(copy)
                rows = patched
            out.extend(rows or [])
        return out

    def parse_grenades(self, extra: Sequence[str] | None = None) -> dict[str, list[Any]]:
        del extra
        return _records_to_columns([])

    def parse_infernos(self, extra: Sequence[str] | None = None) -> dict[str, list[Any]]:
        del extra
        return _records_to_columns([])

    def parse_utility_effects(self, extra: Sequence[str] | None = None) -> dict[str, list[Any]]:
        del extra
        return _records_to_columns([])

    def write_replay_parquet(
        self,
        output_path: str,
        wanted_props: Sequence[str],
        ticks: Sequence[int],
        round_numbers: Sequence[int],
    ) -> dict[str, Any]:
        fields = list(dict.fromkeys(["tick", *wanted_props]))
        tick_rows = self.parse_ticks(fields, ticks=ticks)
        row_count = len(tick_rows.get("tick") or [])
        by_tick: dict[int, dict[str, list[Any]]] = {}
        for index in range(row_count):
            tick = int(tick_rows["tick"][index] or 0)
            bucket = by_tick.setdefault(tick, {name: [] for name in fields})
            for name in fields:
                bucket[name].append(tick_rows[name][index])

        groups: list[dict[str, Any]] = []
        unique_rounds = list(dict.fromkeys(int(value) for value in round_numbers))
        round_of_tick: dict[int, int] = {}
        for tick, round_number in zip(ticks, round_numbers):
            round_of_tick[int(tick)] = int(round_number)

        for round_index, round_number in enumerate(unique_rounds):
            columns = {name: [] for name in fields}
            rows = 0
            for tick in ticks:
                if round_of_tick.get(int(tick)) != round_number:
                    continue
                bucket = by_tick.get(int(tick))
                if not bucket:
                    continue
                count = len(bucket["tick"])
                rows += count
                for name in fields:
                    columns[name].extend(bucket[name])
            groups.append(
                {
                    "round_number": int(round_number),
                    "row_group": round_index,
                    "rows": rows,
                    "columns": columns,
                }
            )

        payload = {
            "magic": "CSGO-RPL-JSON-1",
            "version": EXTRACTOR_VERSION,
            "row_groups": groups,
        }
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".partial")
        with gzip.open(tmp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp, destination)
        return {
            "row_groups": [
                {
                    "round_number": group["round_number"],
                    "row_group": group["row_group"],
                    "rows": group["rows"],
                }
                for group in groups
            ]
        }

    @staticmethod
    def read_replay_parquet_round(path: str, row_group: int) -> dict[str, list[Any]]:
        payload = _load_replay_store(path)
        groups = payload.get("row_groups") or []
        if row_group < 0 or row_group >= len(groups):
            return {}
        columns = groups[row_group].get("columns") or {}
        return {str(name): list(values) for name, values in columns.items()}

    @staticmethod
    def read_replay_parquet_round_binary(
        path: str,
        row_group: int,
        sample_ticks: Sequence[int],
        metadata_json: str,
    ) -> bytes:
        frame = DemoParser.read_replay_parquet_round(path, row_group)
        metadata = json.loads(metadata_json) if metadata_json else {}
        return encode_replay_binary(frame, sample_ticks, metadata)

    @staticmethod
    def decode_smoke_voxel_journal(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


def _load_replay_store(path: str) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {}
    return payload


def _records_to_columns(rows: Iterable[dict[str, Any]]) -> dict[str, list[Any]]:
    materialised = [dict(row) for row in rows]
    if not materialised:
        return {}
    names: list[str] = []
    seen: set[str] = set()
    for row in materialised:
        for key in row:
            name = str(key)
            if name not in seen:
                seen.add(name)
                names.append(name)
    return {name: [row.get(name) for row in materialised] for name in names}


