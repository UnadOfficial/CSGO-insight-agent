import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLocaleStore } from "../i18n/localeStore.js";
import DemoPlaybackRestoreModal from "./DemoPlaybackRestoreModal.jsx";

describe("DemoPlaybackRestoreModal", () => {
  beforeEach(() => useLocaleStore.getState().hydrate("zh"));

  it("confirms player settings restoration", () => {
    const onClose = vi.fn();
    render(<DemoPlaybackRestoreModal open status={{ state: "completed", player_config_restore: { verified: true } }} onClose={onClose} />);
    expect(screen.getByText("玩家设置已恢复")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("reports a failed player settings restoration", () => {
    render(<DemoPlaybackRestoreModal open status={{ state: "restore_failed", player_config_restore: { verified: false } }} onClose={vi.fn()} onRetry={vi.fn()} />);
    expect(screen.getByText("玩家设置未能确认恢复")).toBeTruthy();
    expect(screen.getByText(/配置恢复失败/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新核验" })).toBeTruthy();
  });

  it("waits for CS:GO to exit before reporting final status", () => {
    render(<DemoPlaybackRestoreModal open status={{ state: "running" }} onClose={vi.fn()} />);
    expect(screen.getByText(/等待 CS:GO 完全退出/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "关闭" })).toBeNull();
  });
});
