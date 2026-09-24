import { describe, expect, it } from "vitest";

import { splitRecordWarmupConfirmPayload, warmupUiOptsToPersisted } from "./warmupDefaults.js";

describe("CS:GO recording warmup payload", () => {
  it("drops retired Source 2 fields from the API warmup and session", () => {
    const result = splitRecordWarmupConfirmPayload({
      recording_skybox: "cartoon3",
      recording_map_material: "waxed_reflection",
      tv_nochat: true,
    });

    expect(result.warmupForApi).toEqual({ tv_nochat: true });
    expect(result.session).not.toHaveProperty("recording_skybox");
    expect(result.session).not.toHaveProperty("recording_map_material");
  });

  it("keeps only CS:GO warmup values in the API payload", () => {
    const result = splitRecordWarmupConfirmPayload({
      input_hud_enabled: false,
      input_hud_display_mode: "active",
      input_audio_enabled: false,
      combat_stats_hud_enabled: false,
      tv_nochat: true,
    });

    expect(result.warmupForApi).toEqual({ tv_nochat: true });
    expect(result.session).toEqual({
      player_aliases_by_demo: {},
      csgo_extra_launch_args: undefined,
      record_inject_console_lines: undefined,
      obs_transition_enabled: undefined,
      obs_transition_name: undefined,
      obs_transition_duration_ms: undefined,
    });
  });

  it("does not add defaults for retired visual overrides", () => {
    expect(splitRecordWarmupConfirmPayload({
      recording_skybox: "unknown",
      recording_map_material: "unknown",
    }).session).not.toHaveProperty("recording_skybox");
  });

  it("persists CS:GO warmup defaults for the recording preset", () => {
    expect(warmupUiOptsToPersisted({
      input_hud_enabled: false,
      input_hud_display_mode: "hybrid",
    })).toMatchObject({
      pov_voice_mode: "team",
      aspect_ratio: "",
    });
  });
});
