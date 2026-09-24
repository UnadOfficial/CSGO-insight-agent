import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLocaleStore } from "../i18n/localeStore.js";
import ExperimentalPovSection from "./ExperimentalPovSection.jsx";

describe("ExperimentalPovSection", () => {
  beforeEach(() => {
    useLocaleStore.getState().hydrate("zh");
  });

  it("renders the optional HLAE POV control and Source 2 limitation card", () => {
    const onChange = vi.fn();
    render(<ExperimentalPovSection visible hlaeMirvPovEnabled={false} onHlaeMirvPovChange={onChange} />);
    const checkbox = screen.getByRole("checkbox", { name: /HLAE mirv_pov/ });
    expect(checkbox.checked).toBe(false);
    expect(screen.getByText(/CS:GO 不支持 Source 2/)).toBeTruthy();
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("supports CS:GO voice selection and embedded content", () => {
    const onVoice = vi.fn();
    render(
      <ExperimentalPovSection
        visible
        povVoiceMode="team"
        onPovVoiceModeChange={onVoice}
        contentAfterVoice={<div data-testid="after">content</div>}
      />,
    );
    const select = screen.getByRole("combobox", { name: "语音控制" });
    expect(Array.from(select.options).map(({ value }) => value)).toEqual(["team", "all", "mute"]);
    fireEvent.change(select, { target: { value: "mute" } });
    expect(onVoice).toHaveBeenCalledWith("mute");
    expect(screen.getByTestId("after")).toBeTruthy();
  });

  it("honors visibility and disabled state", () => {
    const { rerender } = render(
      <ExperimentalPovSection visible checkboxDisabled onHlaeMirvPovChange={vi.fn()} />,
    );
    expect(screen.getByRole("checkbox").disabled).toBe(true);
    rerender(<ExperimentalPovSection visible={false} onHlaeMirvPovChange={vi.fn()} />);
    expect(screen.queryByTestId("experimental-feature-card")).toBeNull();
  });
});
