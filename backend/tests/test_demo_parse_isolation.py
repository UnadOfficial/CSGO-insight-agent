import pytest

from app import demo_parse_isolation


def test_metadata_inspection_has_a_shorter_deadline(monkeypatch):
    monkeypatch.delenv("CS2_INSIGHT_DEMO_INSPECT_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CS2_INSIGHT_PARSE_WORKER_TIMEOUT_SEC", raising=False)

    assert demo_parse_isolation._timeout_seconds("inspect") == 30.0
    assert demo_parse_isolation._timeout_seconds("analyze_batch") == 240.0


def test_worker_deadlines_remain_developer_overridable(monkeypatch):
    monkeypatch.setenv("CS2_INSIGHT_DEMO_INSPECT_TIMEOUT_SEC", "18")
    monkeypatch.setenv("CS2_INSIGHT_PARSE_WORKER_TIMEOUT_SEC", "90")

    assert demo_parse_isolation._timeout_seconds("players") == 18.0
    assert demo_parse_isolation._timeout_seconds("analyze") == 90.0


def test_multi_player_worker_rejects_malformed_success(monkeypatch):
    monkeypatch.setattr(demo_parse_isolation, "run_parse_worker", lambda *_args, **_kwargs: [])

    with pytest.raises(demo_parse_isolation.IsolatedParseError):
        demo_parse_isolation.analyze_multi_isolated("match.dem", ["alpha"])


def test_multi_player_parse_rebuilds_replay_in_a_second_worker(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_run(action, **payload):
        calls.append((action, payload))
        if action == "analyze_batch":
            return {
                "__analysis_workspace__": {"rounds": [{"round_number": 1}]},
                "alpha": {"clips": []},
            }
        if action == "materialize_replay":
            return {"status": "materialized", "frames": 32}
        raise AssertionError(action)

    monkeypatch.setattr(demo_parse_isolation, "run_parse_worker", fake_run)

    result = demo_parse_isolation.analyze_multi_isolated("match.dem", ["alpha"])

    assert [action for action, _payload in calls] == ["analyze_batch", "materialize_replay"]
    assert calls[1][1]["dem_path"] == "match.dem"
    assert result["__analysis_workspace__"]["replay_cache"] == {
        "status": "materialized",
        "frames": 32,
    }
    assert result["alpha"] == {"clips": []}


def test_replay_materialize_is_skipped_when_analysis_consumed_the_budget(monkeypatch):
    calls: list[str] = []

    class Clock:
        t = 0.0

        def monotonic(self):
            return self.t

    clock = Clock()

    def fake_run(action, **_payload):
        calls.append(action)
        if action == "analyze_batch":
            clock.t = 230.0
            return {
                "__analysis_workspace__": {"rounds": [{"round_number": 1}]},
                "alpha": {"clips": []},
            }
        raise AssertionError(action)

    monkeypatch.setattr(demo_parse_isolation, "run_parse_worker", fake_run)
    monkeypatch.setattr(demo_parse_isolation.time, "monotonic", clock.monotonic)

    result = demo_parse_isolation.analyze_multi_isolated("match.dem", ["alpha"])

    assert calls == ["analyze_batch"]
    assert result["alpha"] == {"clips": []}
    assert result["__analysis_workspace__"]["replay_cache"]["status"] == "skipped"


def test_parse_worker_scratch_dir_follows_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CS2_INSIGHT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CSGO_INSIGHT_DATA_DIR", str(tmp_path))

    path = demo_parse_isolation._parse_worker_dir()

    assert path == tmp_path.resolve() / "tmp" / "parse-workers"
    assert path.is_dir()


def test_multi_player_parse_keeps_analysis_when_replay_worker_fails(monkeypatch):
    def fake_run(action, **payload):
        if action == "analyze_batch":
            return {
                "__analysis_workspace__": {"rounds": [{"round_number": 1}]},
                "alpha": {"clips": []},
            }
        raise demo_parse_isolation.IsolatedParseError("replay boom")

    monkeypatch.setattr(demo_parse_isolation, "run_parse_worker", fake_run)

    result = demo_parse_isolation.analyze_multi_isolated("match.dem", ["alpha"])

    assert result["alpha"] == {"clips": []}
    assert result["__analysis_workspace__"]["replay_cache"]["status"] == "error"
    assert "replay boom" in result["__analysis_workspace__"]["replay_cache"]["error"]
