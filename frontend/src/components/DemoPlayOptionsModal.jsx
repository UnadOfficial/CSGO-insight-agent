import { Eye, Loader2, Play } from "lucide-react";
import { useT } from "../i18n/useT.js";
import Modal from "./ui/Modal.jsx";
import PlayerAliasesSection from "./PlayerAliasesSection.jsx";
import { hasInvalidPlayerAliases, PLAYER_ALIAS_ENTRY_VISIBLE } from "../utils/playerAliases.js";

export default function DemoPlayOptionsModal({
  open,
  demoLabel,
  checking = false,
  blockedReason = "",
  error = "",
  launchingMode = "",
  onClose,
  onRetry,
  onPlayAdvanced,
  aliasDemos = [],
  aliasEditor,
  onAliasEditorChange,
  aliasesReady = false,
  onAliasesReadyChange,
}) {
  const t = useT();
  const launching = Boolean(launchingMode);
  const aliasesBlocked = PLAYER_ALIAS_ENTRY_VISIBLE
    && aliasEditor?.enabled
    && (!aliasesReady || hasInvalidPlayerAliases(aliasEditor));
  const blockedMessage = blockedReason === "path"
    ? t("playDemo.csgoPathMissing")
    : blockedReason === "busy"
      ? t("playDemo.busyMessage")
      : t("playDemo.csgoRunningMessage");

  return (
    <Modal
      open={open}
      onClose={() => { if (!launching) onClose?.(); }}
      closable={!launching}
      title={t("playDemo.title")}
      subtitle={demoLabel || t("playDemo.demoFallback")}
      icon={<Eye className="h-4 w-4 text-cs2-accent" />}
      maxWidth="max-w-lg"
      maxHeight="max-h-[90vh]"
      className="!h-auto"
      contentClassName="overflow-y-auto"
      zIndex={150}
    >
      <div className="space-y-3 px-5 py-4">
        {checking ? (
          <div className="flex min-h-36 flex-col items-center justify-center gap-3 text-cs2-text-muted">
            <Loader2 className="h-6 w-6 animate-spin text-cs2-accent" />
            <p className="text-sm">{t("playDemo.checking")}</p>
          </div>
        ) : launching ? (
          <div className="flex min-h-28 flex-col items-center justify-center gap-3 rounded-lg border border-cs2-border bg-cs2-bg-input/35 px-4 py-5 text-center">
            <Loader2 className="h-6 w-6 animate-spin text-cs2-accent" />
            <p className="text-sm font-semibold text-cs2-text-primary">{t("playDemo.launching")}</p>
            <p className="text-xs text-cs2-text-muted">{t("playDemo.nativePlaybackNote")}</p>
          </div>
        ) : blockedReason ? (
          <div className="rounded-lg border border-amber-500/35 bg-cs2-amber-surface px-3 py-3 text-sm text-cs2-amber-on-surface">
            <p>{blockedMessage}</p>
            <button type="button" onClick={() => void onRetry?.()} className="mt-2 rounded border border-amber-400/40 px-2 py-1 text-xs font-semibold">
              {t("playDemo.retry")}
            </button>
          </div>
        ) : (
          <>
            {error ? <p className="rounded border border-rose-500/35 bg-cs2-rose-surface px-3 py-2 text-xs text-rose-100">{error}</p> : null}
            <div className="rounded-lg border border-cs2-border bg-cs2-bg-input/35 px-3 py-3 text-xs leading-relaxed text-cs2-text-secondary">
              {t("playDemo.nativePlaybackNote")}
            </div>
            {PLAYER_ALIAS_ENTRY_VISIBLE ? (
              <PlayerAliasesSection
                demos={aliasDemos}
                value={aliasEditor}
                onChange={onAliasEditorChange}
                onReadyChange={onAliasesReadyChange}
              />
            ) : null}
            <button
              type="button"
              disabled={aliasesBlocked}
              onClick={() => void onPlayAdvanced?.()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-cs2-accent px-4 py-2.5 text-sm font-bold text-cs2-text-on-accent disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Play className="h-4 w-4" />
              {t("playDemo.playNative")}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}
