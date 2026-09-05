"""Validate the CS:GO demo extractor required by analysis and 2D replay."""

from __future__ import annotations

import json
from typing import Any

from .csgo_demo_parser.parser import (
    EXTRACTOR_VERSION,
    DemoParser,
    extractor_version_output,
    resolve_extractor_path,
)

REQUIRED_DEMOPARSER_VERSION = EXTRACTOR_VERSION
REQUIRED_DEMOPARSER_METHODS = (
    "parse_header",
    "parse_event",
    "parse_events",
    "parse_ticks",
    "write_replay_parquet",
    "read_replay_parquet_round",
    "read_replay_parquet_round_binary",
)


def inspect_demoparser_runtime() -> dict[str, Any]:
    """Return a stable capability report without raising import errors."""
    extractor = resolve_extractor_path()
    installed_version = extractor_version_output(extractor)
    missing_methods = [
        method
        for method in REQUIRED_DEMOPARSER_METHODS
        if not callable(getattr(DemoParser, method, None))
    ]
    ready = (
        extractor is not None
        and installed_version == REQUIRED_DEMOPARSER_VERSION
        and not missing_methods
    )
    return {
        "ready": ready,
        "installed_version": installed_version,
        "required_version": REQUIRED_DEMOPARSER_VERSION,
        "missing_methods": missing_methods,
        "import_error": None if extractor is not None else "csgo-demo-extract not found",
        "extractor_path": str(extractor) if extractor is not None else None,
    }


def require_demoparser_runtime() -> dict[str, Any]:
    """Fail startup instead of silently degrading the replay pipeline."""
    report = inspect_demoparser_runtime()
    if report["ready"]:
        return report
    installed = report["installed_version"] or "not installed"
    missing = ", ".join(report["missing_methods"]) or "none"
    detail = f"; import error: {report['import_error']}" if report["import_error"] else ""
    raise RuntimeError(
        "CS:GO demo extractor is not ready. "
        f"Required {REQUIRED_DEMOPARSER_VERSION}, installed {installed}; "
        f"missing methods: {missing}{detail}. "
        "Build tools/csgo-demo-extract with Go, or set CSGO_INSIGHT_DEMO_EXTRACT."
    )


def main() -> int:
    report = require_demoparser_runtime()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
