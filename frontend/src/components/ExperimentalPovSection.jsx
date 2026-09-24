import { useT } from "../i18n/useT.js";

/**
 * CS:GO advanced POV controls.
 *
 * Source 2 VPK/gameinfo, skybox, material and weather overrides are deliberately
 * not represented here.  HLAE mirv_pov is the only optional advanced POV path.
 * The legacy props are accepted but ignored so embedded callers can migrate
 * independently without ever serialising Source 2 options.
 */
export default function ExperimentalPovSection({
  visible = true,
  hlaeMirvPovEnabled = false,
  onHlaeMirvPovChange,
  checkboxDisabled = false,
  povVoiceMode,
  onPovVoiceModeChange,
  contentAfterVoice = null,
  omitEyebrow = false,
  omitDisclaimer = false,
  embedded = false,
  className,
}) {
  const t = useT();
  if (!visible) return null;
  const rootClass = className ?? "min-w-0";
  return (
    <div className={rootClass}>
      <section
        className={embedded ? "min-w-0" : "min-w-0 rounded-lg border border-amber-500/25 bg-cs2-amber-surface p-3"}
        data-testid="experimental-feature-card"
      >
        {!omitEyebrow ? (
          <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-cs2-amber-on-surface">
            {t("pov.eyebrowLabel")}
          </p>
        ) : null}
        <label className="flex cursor-pointer items-start gap-2 py-1">
          <input
            type="checkbox"
            disabled={checkboxDisabled || !onHlaeMirvPovChange}
            checked={!!hlaeMirvPovEnabled}
            onChange={(event) => onHlaeMirvPovChange?.(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-cs2-border accent-cs2-orange disabled:opacity-40"
          />
          <span className="min-w-0 text-[12px] leading-snug text-cs2-text-primary">
            <span className="font-semibold text-cs2-amber-on-surface/95">
              {t("pov.hlaeTitle")}
            </span>
            <span className="mt-1 block text-[11px] leading-relaxed text-cs2-text-muted">
              {t("pov.hlaeDescription")}
            </span>
          </span>
        </label>
        {!omitDisclaimer ? (
          <div className="mt-2 rounded border border-cs2-border bg-cs2-bg-card px-2.5 py-2 text-[11px] leading-relaxed text-cs2-text-muted">
            {t("pov.source2Unsupported")}
          </div>
        ) : null}
        {onPovVoiceModeChange ? (
          <label className="mt-4 block border-t border-amber-500/20 pt-4 text-[11px] text-cs2-text-secondary">
            <span className="mb-1 block font-semibold text-cs2-text-primary">{t("pov.voiceModeLabel")}</span>
            <select
              aria-label={t("pov.voiceModeLabel")}
              value={povVoiceMode || "team"}
              disabled={checkboxDisabled}
              onChange={(event) => onPovVoiceModeChange(event.target.value)}
              className="mt-1 w-full rounded border border-cs2-border bg-cs2-bg-input px-2 py-1.5 text-xs text-cs2-text-primary"
            >
              <option value="team">{t("pov.voiceMode.team")}</option>
              <option value="all">{t("pov.voiceMode.all")}</option>
              <option value="mute">{t("pov.voiceMode.mute")}</option>
            </select>
          </label>
        ) : null}
        {contentAfterVoice ? <div className="mt-4 border-t border-amber-500/20 pt-4">{contentAfterVoice}</div> : null}
      </section>
    </div>
  );
}
