import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/api.js", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import API from "../api/api.js";
import { getDemoPlaybackPreflight, getDemoPlaybackStatus, playDemoErrorLabel, playDemoInCsgo } from "./playDemoInCsgo.js";

describe("playDemoInCsgo", () => {
  beforeEach(() => {
    API.get.mockReset();
    API.post.mockReset();
  });

  it("prefers library id over path", async () => {
    API.post.mockResolvedValue({ data: { ok: true } });
    await playDemoInCsgo({ id: 42, path: "C:/tmp/a.dem" });
    expect(API.post).toHaveBeenCalledWith("/demos/42/play", {});
  });

  it("posts path when id is missing", async () => {
    API.post.mockResolvedValue({ data: { ok: true } });
    await playDemoInCsgo({ path: "C:/tmp/a.dem" });
    expect(API.post).toHaveBeenCalledWith("/demo/play", { path: "C:/tmp/a.dem" });
  });

  it("does not serialize removed Source 2 playback options", async () => {
    API.post.mockResolvedValue({ data: { ok: true } });
    await playDemoInCsgo({
      id: 7,
      advancedPlayback: {
        enabled: true,
        radar_mode: -1,
        teamcounter_numeric: true,
        skybox_id: "cartoon3",
        map_material_id: "waxed_reflection",
        input_hud_enabled: true,
        input_hud_display_mode: "active",
        // Legacy callers may still send these, but the current product preset
        // fixes both values at 100.
        input_hud_scale_percent: 115,
        input_audio_enabled: true,
        input_audio_volume_percent: 50,
        weather_effect_id: "default",
      },
    });
    expect(API.post).toHaveBeenCalledWith("/demos/7/play", {});
  });

  it("does not serialize removed weather and input HUD options", async () => {
    API.post.mockResolvedValue({ data: { ok: true } });
    await playDemoInCsgo({
      id: 8,
      advancedPlayback: {
        enabled: true,
        map_material_id: "rain_puddles",
      },
    });
    expect(API.post).toHaveBeenCalledWith("/demos/8/play", {});
  });

  it("loads playback preflight", async () => {
    API.get.mockResolvedValue({ data: { csgo_running: true } });
    await expect(getDemoPlaybackPreflight()).resolves.toEqual({ csgo_running: true });
    expect(API.get).toHaveBeenCalledWith("/demo/playback/preflight");
  });

  it("loads the factual restoration status for one playback session", async () => {
    API.get.mockResolvedValue({ data: { found: true, state: "completed", restore: { verified: true } } });
    await expect(getDemoPlaybackStatus("session-123")).resolves.toEqual({
      found: true,
      state: "completed",
      restore: { verified: true },
    });
    expect(API.get).toHaveBeenCalledWith("/demo/playback/status", {
      params: { session_id: "session-123" },
    });
  });

  it("rejects when neither id nor path", async () => {
    await expect(playDemoInCsgo({})).rejects.toThrow(/缺少可播放/);
  });
});

describe("playDemoErrorLabel", () => {
  it("reads string detail", () => {
    expect(playDemoErrorLabel({ response: { data: { detail: "no cs2" } } })).toBe("no cs2");
  });
});
