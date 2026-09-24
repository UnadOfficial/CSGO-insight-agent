import { describe, expect, it } from "vitest";

import {
  isUnexpectedCsgoExitResult,
  isRecordingAbortResult,
  recordingAbortToastKind,
  recordingQueueHadUnexpectedCsgoExit,
  recordingQueueWasAborted,
  unexpectedCsgoExitRecoveryMessageKey,
} from "./recordingAbort";

describe("recording abort outcome", () => {
  it("recognizes request- and segment-level abort results", () => {
    expect(isRecordingAbortResult({ success: false, error: "aborted" })).toBe(true);
    expect(isRecordingAbortResult({
      success: false,
      segment_results: [{ status: "skipped", error: "aborted" }],
    })).toBe(true);
    expect(recordingQueueWasAborted([{ success: true }], true)).toBe(true);
    expect(recordingQueueWasAborted([{ success: false, error: "failed" }], false)).toBe(false);
  });

  it("keeps restore warnings distinct from a completed cleanup", () => {
    expect(recordingAbortToastKind({ restore_required: true })).toBe("restore_pending");
    expect(recordingAbortToastKind({ fetch_failed: true })).toBe("unverified");
    expect(recordingAbortToastKind({ restore_required: false })).toBe("completed");
    expect(recordingAbortToastKind(
      { restore_required: false },
      [{ recovery: { player_config_restore_state: "unverified" } }],
    )).toBe("unverified");
    expect(recordingAbortToastKind(
      { restore_required: false },
      [{ recovery: { player_config_restore_state: "not_needed" } }],
    )).toBe("not_needed");
  });

  it("recognizes a managed CS:GO process that exited outside Insight cleanup", () => {
    expect(isUnexpectedCsgoExitResult({ error_code: "RECORDING_CSGO_EXITED" })).toBe(true);
    expect(isUnexpectedCsgoExitResult({ error: "csgo_exited_unexpectedly" })).toBe(true);
    expect(recordingQueueHadUnexpectedCsgoExit([{ success: true }, {
      success: false,
      error_code: "RECORDING_CSGO_EXITED",
    }])).toBe(true);
    expect(recordingQueueHadUnexpectedCsgoExit([{ success: false, error: "failed" }])).toBe(false);
  });

  it("selects recovery copy for config and optional POV state", () => {
    expect(unexpectedCsgoExitRecoveryMessageKey()).toBe("app.unexpectedCsgoExitRecovered");
    expect(unexpectedCsgoExitRecoveryMessageKey({ configRecoveryNeeded: true })).toBe(
      "app.unexpectedCsgoExitConfigPending",
    );
  });
});
