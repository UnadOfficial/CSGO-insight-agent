import { useCallback, useEffect, useRef, useState } from "react";
import {
  hasInvalidPlayerAliases,
  PLAYER_ALIAS_ENTRY_VISIBLE,
  playerAliasMaps,
} from "../utils/playerAliases.js";

import DemoPlayOptionsModal from "../components/DemoPlayOptionsModal.jsx";
import DemoPlaybackRestoreModal from "../components/DemoPlaybackRestoreModal.jsx";
import { useT } from "../i18n/useT.js";
import { getDemoPlaybackPreflight, getDemoPlaybackStatus, playDemoErrorLabel, playDemoInCsgo } from "../utils/playDemoInCsgo.js";
import { parseApiDetail } from "../utils/apiErrorMessages.js";
import { usePlayDemoToast } from "./usePlayDemoToast.jsx";

function blockedReasonFromPreflight(data) {
  if (!data?.csgo_path_configured) return "path";
  if (data?.csgo_running) return "running";
  if (data?.playback_active) return "busy";
  return "";
}

function blockedReasonFromError(error) {
  const { code } = parseApiDetail(error?.response?.data?.detail);
  if (code === "DEMO_PLAYBACK_CSGO_RUNNING") return "running";
  if (code === "DEMO_PLAYBACK_BUSY") return "busy";
  if (code === "DEMO_PLAYBACK_CSGO_PATH_MISSING") return "path";
  return "";
}

export function useDemoPlaybackDialog() {
  const t = useT();
  const { showPlayToast, PlayDemoToast } = usePlayDemoToast();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [checking, setChecking] = useState(false);
  const [blockedReason, setBlockedReason] = useState("");
  const [launchingMode, setLaunchingMode] = useState("");
  const [error, setError] = useState("");
  const [aliasEditor, setAliasEditor] = useState({ enabled: false, drafts: {} });
  const [aliasesReady, setAliasesReady] = useState(false);
  const [restoreMonitor, setRestoreMonitor] = useState(null);
  const [restorePollError, setRestorePollError] = useState("");

  useEffect(() => {
    const sessionId = restoreMonitor?.sessionId;
    if (!sessionId) return undefined;
    let stopped = false;
    let timer = null;
    const poll = async () => {
      try {
        const data = await getDemoPlaybackStatus(sessionId);
        if (!data?.found) throw new Error(t("playDemo.restoreSessionMissing"));
        if (stopped) return;
        setRestorePollError("");
        setRestoreMonitor((current) => (
          current?.sessionId === sessionId ? { ...current, status: data } : current
        ));
        if (!["completed", "restore_failed"].includes(String(data.state || ""))) {
          timer = setTimeout(poll, 1000);
        }
      } catch (statusError) {
        if (stopped) return;
        setRestorePollError(playDemoErrorLabel(statusError, t));
        timer = setTimeout(poll, 2000);
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timer != null) clearTimeout(timer);
    };
  }, [restoreMonitor?.sessionId, t]);

  const runPreflight = useCallback(async () => {
    setChecking(true);
    setBlockedReason("");
    setError("");
    try {
      const data = await getDemoPlaybackPreflight();
      setBlockedReason(blockedReasonFromPreflight(data));
    } catch (preflightError) {
      // The launch endpoint remains authoritative; keep the choices available if preflight itself fails.
      setError(playDemoErrorLabel(preflightError, t));
    } finally {
      setChecking(false);
    }
  }, [t]);

  const requestPlayDemo = useCallback(async ({ id = null, path = null, label = "Demo" } = {}) => {
    setTarget({ id, path, label });
    setOpen(true);
    setLaunchingMode("");
    setAliasEditor({ enabled: false, drafts: {} });
    setAliasesReady(false);
    await runPreflight();
  }, [runPreflight]);

  const close = useCallback(() => {
    if (launchingMode) return;
    setOpen(false);
    setTarget(null);
    setBlockedReason("");
    setError("");
  }, [launchingMode]);

  const launch = useCallback(async () => {
    if (!target || launchingMode) return;
    if (PLAYER_ALIAS_ENTRY_VISIBLE
        && aliasEditor.enabled
        && (!aliasesReady || hasInvalidPlayerAliases(aliasEditor))) {
      setError(t("playerAliases.invalid"));
      return;
    }
    setLaunchingMode("native");
    setError("");
    try {
      const launchResult = await playDemoInCsgo({
        id: target.id,
        path: target.path,
        playerAliases: PLAYER_ALIAS_ENTRY_VISIBLE ? playerAliasMaps(aliasEditor).playback : {},
      });
      setOpen(false);
      setTarget(null);
      setBlockedReason("");
      if (launchResult?.session_id) {
        setRestorePollError("");
        setRestoreMonitor({
          sessionId: String(launchResult.session_id),
          status: {
            found: true,
            session_id: String(launchResult.session_id),
            state: "running",
            hlae_mirv_pov: false,
            restore: null,
          },
        });
      }
      showPlayToast(true, target.label || "Demo");
    } catch (launchError) {
      const nextBlockedReason = blockedReasonFromError(launchError);
      if (nextBlockedReason) {
        setBlockedReason(nextBlockedReason);
      } else {
        setError(playDemoErrorLabel(launchError, t));
      }
    } finally {
      setLaunchingMode("");
    }
  }, [aliasEditor, aliasesReady, launchingMode, showPlayToast, t, target]);

  const retryRestoreStatus = useCallback(async () => {
    const sessionId = restoreMonitor?.sessionId;
    if (!sessionId) return;
    try {
      const data = await getDemoPlaybackStatus(sessionId);
      if (!data?.found) throw new Error(t("playDemo.restoreSessionMissing"));
      setRestorePollError("");
      setRestoreMonitor((current) => (
        current?.sessionId === sessionId ? { ...current, status: data } : current
      ));
    } catch (statusError) {
      setRestorePollError(playDemoErrorLabel(statusError, t));
    }
  }, [restoreMonitor?.sessionId, t]);

  // Keep the component type stable while alias drafts change so focus and IME
  // composition are not lost on each keystroke.
  const uiRef = useRef(null);
  uiRef.current = (
    <>
      <DemoPlayOptionsModal
        open={open}
        demoLabel={target?.label}
        checking={checking}
        blockedReason={blockedReason}
        error={error}
        launchingMode={launchingMode}
        aliasDemos={target ? [{ key: "playback", id: target.id, path: target.path, label: target.label }] : []}
        aliasEditor={aliasEditor}
        aliasesReady={aliasesReady}
        onAliasEditorChange={setAliasEditor}
        onAliasesReadyChange={setAliasesReady}
        onClose={close}
        onRetry={runPreflight}
        onPlayAdvanced={() => void launch()}
      />
      <PlayDemoToast />
      <DemoPlaybackRestoreModal
        open={Boolean(restoreMonitor)}
        status={restoreMonitor?.status}
        pollError={restorePollError}
        onRetry={() => void retryRestoreStatus()}
        onClose={() => {
          setRestoreMonitor(null);
          setRestorePollError("");
        }}
      />
    </>
  );
  const DemoPlaybackUi = useCallback(() => uiRef.current, []);

  return { requestPlayDemo, DemoPlaybackUi };
}
