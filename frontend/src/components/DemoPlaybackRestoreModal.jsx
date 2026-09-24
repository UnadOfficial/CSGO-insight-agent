import { AlertTriangle, CheckCircle2, FileCheck2, Loader2, RefreshCw } from "lucide-react";
import { useT } from "../i18n/useT.js";
import Modal from "./ui/Modal.jsx";

export default function DemoPlaybackRestoreModal({ open, status, pollError = "", onClose, onRetry }) {
  const t = useT();
  const state = String(status?.state || "running");
  const final = state === "completed" || state === "restore_failed";
  const playerRestore = status?.player_config_restore;
  const verified = Boolean(final && playerRestore?.verified !== false);
  const failed = final && !verified;
  const canClose = final || Boolean(pollError);
  return (
    <Modal
      open={open}
      onClose={() => { if (canClose) onClose?.(); }}
      title={t("playDemo.restoreTitle")}
      subtitle={t("playDemo.restoreSubtitle")}
      icon={verified ? <FileCheck2 className="h-4 w-4 text-emerald-400" /> : failed ? <AlertTriangle className="h-4 w-4 text-rose-400" /> : <Loader2 className="h-4 w-4 animate-spin text-cs2-accent" />}
      maxWidth="max-w-lg"
      maxHeight="max-h-[82vh]"
      className="!h-auto"
      contentClassName="overflow-y-auto"
      zIndex={155}
    >
      <div className="space-y-3 px-5 py-4" data-testid="demo-playback-restore-content">
        {!final ? (
          <div className="flex items-start gap-3 rounded-lg border border-cs2-border bg-cs2-bg-input/35 px-3.5 py-2.5">
            <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-cs2-accent" />
            <div>
              <p className="text-sm font-bold text-cs2-text-primary">{t("playDemo.restoreWaiting")}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-cs2-text-muted">{t("playDemo.restoreDoNotAssume")}</p>
            </div>
          </div>
        ) : (
          <div className={`rounded-lg border px-3 py-2.5 ${verified ? "border-emerald-500/35 bg-emerald-500/10" : "border-rose-500/35 bg-cs2-rose-surface"}`}>
            <p className={`text-sm font-bold ${verified ? "text-emerald-400" : "text-cs2-rose-on-surface"}`}>
              {verified ? t("playDemo.restoreVerifiedTitle") : t("playDemo.restoreFailedTitle")}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-cs2-text-muted">
              {verified ? t("playDemo.playerConfigRestored") : t("playDemo.playerConfigNotRestored")}
            </p>
          </div>
        )}
        {pollError ? <div className="rounded-lg border border-amber-500/35 bg-cs2-amber-surface px-3 py-2.5 text-[11px] text-cs2-amber-on-surface">{t("playDemo.restoreStatusUnavailable")}: {pollError}</div> : null}
        <div className="flex justify-end gap-2">
          {(failed || pollError) ? <button type="button" onClick={onRetry} className="flex items-center gap-1.5 rounded-lg border border-cs2-border px-3 py-2 text-xs font-semibold"><RefreshCw className="h-3.5 w-3.5" />{t("playDemo.restoreRecheck")}</button> : null}
          {canClose ? <button type="button" onClick={onClose} className="rounded-lg bg-cs2-accent px-3 py-2 text-xs font-bold text-cs2-text-on-accent">{t("common.close")}</button> : null}
        </div>
      </div>
    </Modal>
  );
}
