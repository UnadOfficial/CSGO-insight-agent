import { describe, expect, test } from "vitest";

import {
  DEFAULT_RECORDING_OPTIONS,
  buildHighlightRecordingRequest,
  buildRoundCompilationRecordingRequest,
  buildTimelineRoundRecordingRequest,
} from "./recordingRequestFactory";


const queueItem = {
  id: "queue-1",
  demoPath: "C:/demo/source.dem",
  demoFilename: "source.dem",
  targetPlayer: "Player",
  targetSteamId: "1",
};

const matchMeta = {
  map_name: "de_nuke",
  total_rounds: 24,
  demo_end_tick: 177_914,
};


describe("recording demo EOF metadata", () => {
  test("uses the real MatchMeta EOF and removes legacy panel options", () => {
    const request = buildHighlightRecordingRequest(
      {
        round: 24,
        tick_rate: 64,
        clip_max_tick: 175_000,
        kill_ticks: [174_000],
      },
      queueItem,
      matchMeta,
    );

    expect(request.demo.demo_end_tick).toBe(177_914);
    expect(request.demo).not.toHaveProperty("win_panel_match_tick");
    expect(DEFAULT_RECORDING_OPTIONS.demo_end_guard_sec).toBe(1.5);
    expect(DEFAULT_RECORDING_OPTIONS).not.toHaveProperty("final_round_guard_sec");
    expect(DEFAULT_RECORDING_OPTIONS).not.toHaveProperty("final_round_win_panel_guard_sec");
  });

  test("does not let a derived round window enlarge the real EOF", () => {
    const request = buildRoundCompilationRecordingRequest(
      {
        round: 24,
        tick_rate: 64,
        clip_max_tick: 175_000,
        freeze_to_death_round_windows: [{
          round: 24,
          round_start_tick: 170_000,
          freeze_end_tick: 170_500,
          round_end_tick: 180_000,
          end_tick: 181_000,
        }],
      },
      queueItem,
      matchMeta,
    );

    expect(request.demo.demo_end_tick).toBe(177_914);
  });
});

describe("buildTimelineRoundRecordingRequest", () => {
  test("sends freeze start, real round end, death tick, and next-round bound", () => {
    const request = buildTimelineRoundRecordingRequest(
      {
        round: 5,
        start_tick: 9_000,
        end_tick: 20_128,
        clip_min_tick: 10_000,
        freeze_start_tick: 9_000,
        freeze_end_tick: 10_000,
        round_end_tick: 30_000,
        next_round_start_tick: 30_400,
        next_round_freeze_end_tick: 31_000,
        death_tick: 20_000,
        target_spec_slot: 3,
      },
      queueItem,
      matchMeta,
    );

    expect(request.request_type).toBe("timeline_round");
    expect(request.rounds).toHaveLength(1);
    expect(request.rounds[0]).toMatchObject({
      round: 5,
      round_start_tick: 9_000,
      round_end_tick: 30_000,
      freeze_start_tick: 9_000,
      freeze_end_tick: 10_000,
      next_round_start_tick: 30_400,
      next_round_freeze_end_tick: 31_000,
      target_death_tick: 20_000,
    });
  });

  test("does not treat the death-capped end_tick as round_end", () => {
    const request = buildTimelineRoundRecordingRequest(
      {
        round: 5,
        start_tick: 9_000,
        end_tick: 20_128,
        round_end_tick: 30_000,
        freeze_start_tick: 9_000,
        freeze_end_tick: 10_000,
      },
      queueItem,
      matchMeta,
    );
    expect(request.rounds[0].round_end_tick).toBe(30_000);
    expect(request.rounds[0].target_death_tick).toBeNull();
  });
});
