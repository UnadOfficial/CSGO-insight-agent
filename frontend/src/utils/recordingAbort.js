export function isRecordingAbortResult(result) {
  if (!result || typeof result !== "object") return false;
  if (String(result.error || "").trim().toLowerCase() === "aborted") return true;
  return (Array.isArray(result.segment_results) ? result.segment_results : []).some(
    (segment) => String(segment?.error || "").trim().toLowerCase() === "aborted",
  );
}

export function recordingQueueWasAborted(results, abortRequested = false) {
  return Boolean(abortRequested) || (Array.isArray(results) && results.some(isRecordingAbortResult));
}

export function recordingAbortToastKind(configBackupStatus, results = []) {
  const recovery = (Array.isArray(results) ? results : [])
    .map((item) => item?.recovery)
    .find((value) => value && typeof value === "object");
  const state = String(recovery?.player_config_restore_state || "").toLowerCase();
  if (state === "restored") return "completed";
  if (state === "not_needed") return "not_needed";
  if (state === "failed") return "restore_pending";
  if (state === "unverified") return "unverified";
  if (configBackupStatus?.restore_required === true) return "restore_pending";
  if (configBackupStatus?.fetch_failed === true) return "unverified";
  return "completed";
}

export function isUnexpectedCsgoExitResult(result) {
  if (!result || typeof result !== "object") return false;
  if (result.error_code === "RECORDING_CSGO_EXITED") return true;
  return String(result.error || "").trim().toLowerCase() === "csgo_exited_unexpectedly";
}

export function recordingQueueHadUnexpectedCsgoExit(results) {
  return Array.isArray(results) && results.some(isUnexpectedCsgoExitResult);
}

export function unexpectedCsgoExitRecoveryMessageKey({
  configRecoveryNeeded = false,
} = {}) {
  if (configRecoveryNeeded) return "app.unexpectedCsgoExitConfigPending";
  return "app.unexpectedCsgoExitRecovered";
}
