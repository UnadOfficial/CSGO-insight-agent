import CommonParamsModal from "../components/CommonParamsModal";
import { useAppShell } from "../context/AppShellContext";

export default function RecordingParamsPage({ embedded = false, onRegisterSave, onSaveUiChange }) {
  const s = useAppShell();
  return (
    <CommonParamsModal
      variant={embedded ? "embedded" : "page"}
      open
      onClose={() => {}}
      configReady={s.savedRecordWarmupDefaults !== null}
      configRefreshKey={s.commonParamsRefreshKey}
      batchRecording={s.batchRecording}
      savedWarmupDefaults={s.savedRecordWarmupDefaults}
      onSaveAllCommonParams={s.saveAllCommonParams}
      hlaeMirvPovEnabled={s.hlaeMirvPovEnabled}
      csgoExtraLaunchArgs={s.csgoExtraLaunchArgs}
      recordInjectConsoleLines={s.recordInjectConsoleLines}
      obsTransitionEnabled={s.obsTransitionEnabled}
      obsTransitionName={s.obsTransitionName}
      obsTransitionDurationMs={s.obsTransitionDurationMs}
      onRegisterSave={onRegisterSave}
      onSaveUiChange={onSaveUiChange}
    />
  );
}
