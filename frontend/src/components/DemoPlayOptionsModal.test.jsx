import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLocaleStore } from "../i18n/localeStore.js";
import DemoPlayOptionsModal from "./DemoPlayOptionsModal.jsx";

describe("DemoPlayOptionsModal", () => {
  beforeEach(() => {
    useLocaleStore.getState().hydrate("zh");
  });

  it("offers native CS:GO playback and no Source 2 controls", () => {
    const onPlay = vi.fn();
    render(<DemoPlayOptionsModal open demoLabel="match.dem" onPlayAdvanced={onPlay} onClose={vi.fn()} />);
    expect(screen.getByText("CS:GO Demo 播放")).toBeTruthy();
    expect(screen.getByText(/仅使用 Source 1 原生播放/)).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "在 CS:GO 中播放" }));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it("blocks playback while CS:GO is running and allows a recheck", () => {
    const onRetry = vi.fn();
    render(<DemoPlayOptionsModal open demoLabel="match.dem" blockedReason="running" onRetry={onRetry} onClose={vi.fn()} />);
    expect(screen.getByText(/csgo\.exe 正在运行|CS:GO 正在运行/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "在 CS:GO 中播放" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重新检测" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the CS:GO preparation state while launching", () => {
    render(<DemoPlayOptionsModal open demoLabel="match.dem" launchingMode="native" onClose={vi.fn()} />);
    expect(screen.getByText(/正在启动原生 CS:GO Demo 播放/)).toBeTruthy();
  });

  it("shows a configured-path error with a retry action", () => {
    const onRetry = vi.fn();
    render(<DemoPlayOptionsModal open blockedReason="path" onRetry={onRetry} onClose={vi.fn()} />);
    expect(screen.getByText(/有效的 csgo\.exe/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新检测" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
