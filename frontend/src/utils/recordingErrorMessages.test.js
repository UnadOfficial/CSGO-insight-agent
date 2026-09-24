import { describe, expect, it } from "vitest";
import { recordingErrorMessage } from "./recordingErrorMessages";

const messages = {
  "queue.errorCsgoExited": "CSGO_EXITED",
  "queue.errorVoiceFilter": "VOICE_FILTER",
  "queue.errorObsConnection": "OBS_CONNECTION",
  "queue.errorObsControl": "OBS_CONTROL",
  "queue.errorPerspective": "PERSPECTIVE",
  "queue.errorDemoSeek": "DEMO_SEEK",
  "queue.errorDemoControl": "DEMO_CONTROL",
  "queue.errorUnknown": "UNKNOWN",
};
const t = (key) => messages[key] || key;

describe("recordingErrorMessage", () => {
  it("localizes the voice isolation failure shown after CS:GO exits", () => {
    expect(recordingErrorMessage({
      error: "voice isolation failed before recording: voice mask injection returned false",
    }, t)).toBe("VOICE_FILTER");
  });

  it("uses the structured CS:GO exit code when available", () => {
    expect(recordingErrorMessage({
      error: "cs2_exited_unexpectedly",
      error_code: "RECORDING_CSGO_EXITED",
    }, t)).toBe("CSGO_EXITED");
  });

  it("uses segment status when the request-level error is empty", () => {
    expect(recordingErrorMessage({
      error: null,
      segment_results: [{ status: "seek_failed", error: "internal detail" }],
    }, t)).toBe("DEMO_SEEK");
  });

  it("does not expose an unknown raw backend error", () => {
    expect(recordingErrorMessage({ error: "some internal english failure" }, t)).toBe("UNKNOWN");
  });
});
