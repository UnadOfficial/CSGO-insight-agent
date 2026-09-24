import { describe, expect, test } from "vitest";
import { RECORD_WARMUP_DEFAULT_OPTIONS } from "../components/RecordWarmupModal";
import { buildRecordingPresetFile, parseRecordingPresetFile } from "./recordingPresetJson";

const preset = {
  recording_global_pacing: { pre_first_sec: 2, default_victim_pov: true },
  default_record_warmup: { ...RECORD_WARMUP_DEFAULT_OPTIONS, aspect_ratio: "16:9", resolution_width: "1920", resolution_height: "1080" },
  csgo_extra_launch_args: "-fullscreen",
  record_inject_console_lines: "fps_max 0",
  obs_transition_enabled: true,
  obs_transition_name: "Fade",
  obs_transition_duration_ms: 200,
  hlae_mirv_pov_enabled: false,
};

describe("recording preset share JSON", () => {
  test("round trips a valid preset", () => {
    const file = buildRecordingPresetFile(preset, "2026-07-03T00:00:00.000Z");
    expect(parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).toEqual(preset);
  });

  test("rejects another file format", () => {
    expect(() => parseRecordingPresetFile({ format: "other", version: 1, preset }, RECORD_WARMUP_DEFAULT_OPTIONS)).toThrow();
  });

  test("rejects invalid values", () => {
    const file = buildRecordingPresetFile({ ...preset, recording_global_pacing: { pre_first_sec: -1 } });
    expect(() => parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).toThrow();
  });

  test("ignores retired OBS overlay fields in legacy presets", () => {
    const file = {
      ...buildRecordingPresetFile({
        ...preset,
        kb_overlay_enabled: true,
        kb_overlay_tick_offset: 12,
        kb_overlay_position: "weapon_right",
        kill_fx_enabled: true,
        kill_fx_tick_offset: -2,
      }),
      version: 4,
    };
    expect(parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS))
      .toEqual(preset);
  });

  test("drops legacy Source 2 skybox fields", () => {
    const file = buildRecordingPresetFile({ ...preset, recording_skybox: "cartoon3" });
    expect(parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).not.toHaveProperty("recording_skybox");
  });

  test("drops legacy Source 2 map material fields", () => {
    const file = buildRecordingPresetFile({ ...preset, recording_map_material: "waxed_reflection" });
    expect(parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).not.toHaveProperty("recording_map_material");
  });

  test("ignores unknown map material values from old clients", () => {
    const file = buildRecordingPresetFile({ ...preset, recording_map_material: "chrome" });
    expect(() => parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).not.toThrow();
  });

  test("ignores unknown skybox values from old clients", () => {
    const file = buildRecordingPresetFile({ ...preset, recording_skybox: "other" });
    expect(() => parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).not.toThrow();
  });

  test("does not preserve custom Source 2 skybox references", () => {
    const customId = "custom:0123456789abcdef0123456789abcdef";
    const file = buildRecordingPresetFile({ ...preset, recording_skybox: customId });
    expect(parseRecordingPresetFile(file, RECORD_WARMUP_DEFAULT_OPTIONS)).not.toHaveProperty("recording_skybox");
  });

  test("round trips the POV voice audience", () => {
    const next = {
      ...preset,
      default_record_warmup: {
        ...preset.default_record_warmup,
        pov_voice_mode: "all",
      },
    };
    expect(parseRecordingPresetFile(buildRecordingPresetFile(next), RECORD_WARMUP_DEFAULT_OPTIONS))
      .toEqual(next);
  });

  test("round trips the in-game input HUD recording defaults", () => {
    const next = {
      ...preset,
      default_record_warmup: {
        ...preset.default_record_warmup,
        input_hud_enabled: false,
        input_hud_display_mode: "active",
      },
    };
    expect(parseRecordingPresetFile(buildRecordingPresetFile(next), RECORD_WARMUP_DEFAULT_OPTIONS))
      .toEqual(preset);
  });

  test("rejects an unknown in-game input HUD display mode", () => {
    const next = {
      ...preset,
      default_record_warmup: {
        ...preset.default_record_warmup,
        input_hud_display_mode: "sometimes",
      },
    };
    expect(() => parseRecordingPresetFile(buildRecordingPresetFile(next), RECORD_WARMUP_DEFAULT_OPTIONS))
      .not.toThrow();
  });

  test("migrates the legacy disabled voice switch", () => {
    const { pov_voice_mode: _removed, ...legacyWarmup } = preset.default_record_warmup;
    const next = {
      ...preset,
      default_record_warmup: {
        ...legacyWarmup,
        pov_voice_disabled: true,
      },
    };
    expect(parseRecordingPresetFile(buildRecordingPresetFile(next), RECORD_WARMUP_DEFAULT_OPTIONS)
      .default_record_warmup.pov_voice_mode).toBe("team");
  });

  test("rejects an unknown POV voice audience", () => {
    const next = {
      ...preset,
      default_record_warmup: {
        ...preset.default_record_warmup,
        pov_voice_mode: "spectators",
      },
    };
    expect(() => parseRecordingPresetFile(buildRecordingPresetFile(next), RECORD_WARMUP_DEFAULT_OPTIONS))
      .toThrow();
  });

  test("normalizes legacy hidden-radar presets to the fixed visible radar", () => {
    const next = {
      ...preset,
      default_record_warmup: {
        ...preset.default_record_warmup,
        pov_radar_mode: -1,
      },
    };
    expect(parseRecordingPresetFile(buildRecordingPresetFile(next), RECORD_WARMUP_DEFAULT_OPTIONS)
      .default_record_warmup).not.toHaveProperty("pov_radar_mode");
  });
});
