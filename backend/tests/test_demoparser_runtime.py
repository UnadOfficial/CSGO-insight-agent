from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app import demoparser_runtime
from app.csgo_demo_parser.parser import DemoParser

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_parser_class_exposes_required_methods():
    for method in demoparser_runtime.REQUIRED_DEMOPARSER_METHODS:
        assert callable(getattr(DemoParser, method, None)), method


def test_runtime_cli_imports_with_backend_on_sys_path():
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from app.demoparser_runtime import REQUIRED_DEMOPARSER_VERSION; print(REQUIRED_DEMOPARSER_VERSION)",
            str(_BACKEND_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "csgo-extract-1"


def test_runtime_report_without_extractor(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(demoparser_runtime, "resolve_extractor_path", lambda: None)
    monkeypatch.setattr(demoparser_runtime, "extractor_version_output", lambda _path=None: None)
    report = demoparser_runtime.inspect_demoparser_runtime()
    assert report["ready"] is False
    assert report["required_version"] == "csgo-extract-1"


def test_runtime_ready_when_extractor_matches(monkeypatch, tmp_path: Path):
    fake = tmp_path / "csgo-demo-extract.exe"
    fake.write_bytes(b"stub")
    monkeypatch.setattr(demoparser_runtime, "resolve_extractor_path", lambda: fake)
    monkeypatch.setattr(
        demoparser_runtime,
        "extractor_version_output",
        lambda _path=None: demoparser_runtime.REQUIRED_DEMOPARSER_VERSION,
    )
    report = demoparser_runtime.require_demoparser_runtime()
    assert report["ready"] is True


def test_runtime_missing_extractor_raises(monkeypatch):
    monkeypatch.setattr(demoparser_runtime, "resolve_extractor_path", lambda: None)
    monkeypatch.setattr(demoparser_runtime, "extractor_version_output", lambda _path=None: None)
    with pytest.raises(RuntimeError) as error:
        demoparser_runtime.require_demoparser_runtime()
    assert "CSGO_INSIGHT_DEMO_EXTRACT" in str(error.value)
