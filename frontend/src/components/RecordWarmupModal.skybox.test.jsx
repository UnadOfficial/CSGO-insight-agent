import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLocaleStore } from "../i18n/localeStore.js";
import RecordWarmupModal from "./RecordWarmupModal.jsx";

describe("RecordWarmupModal CS:GO options", () => {
  beforeEach(() => {
    useLocaleStore.getState().hydrate("zh");
  });

  it("does not render Source 2 visual override selectors", () => {
    render(<RecordWarmupModal open onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByRole("combobox", { name: "录制天空盒" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "录制地图材质" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "录制天气效果" })).toBeNull();
    expect(screen.getByText(/CS:GO 不支持 Source 2/)).toBeTruthy();
  });

  it("submits the optional HLAE switch without Source 2 fields", () => {
    const onConfirm = vi.fn();
    render(<RecordWarmupModal open onClose={vi.fn()} onConfirm={onConfirm} />);
    const hlae = screen.getByRole("checkbox", { name: /HLAE mirv_pov/ });
    expect(hlae.checked).toBe(false);
    fireEvent.click(hlae);
    fireEvent.click(screen.getByRole("button", { name: "开始录制" }));
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ hlae_mirv_pov: true }));
    const payload = onConfirm.mock.calls[0][0];
    expect(payload).not.toHaveProperty("recording_skybox");
    expect(payload).not.toHaveProperty("recording_map_material");
    expect(payload).not.toHaveProperty("recording_weather_effect");
  });
});
