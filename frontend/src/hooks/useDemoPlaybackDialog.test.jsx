import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/api.js", () => ({ default: { post: vi.fn() } }));
vi.mock("../utils/playDemoInCsgo.js", () => ({
  getDemoPlaybackPreflight: vi.fn(),
  getDemoPlaybackStatus: vi.fn(),
  playDemoErrorLabel: vi.fn((error) => error?.message || "error"),
  playDemoInCsgo: vi.fn(),
}));
vi.mock("./usePlayDemoToast.jsx", () => ({
  usePlayDemoToast: () => ({ showPlayToast: vi.fn(), PlayDemoToast: () => null }),
}));

import { useLocaleStore } from "../i18n/localeStore.js";
import { getDemoPlaybackPreflight, getDemoPlaybackStatus, playDemoInCsgo } from "../utils/playDemoInCsgo.js";
import { useDemoPlaybackDialog } from "./useDemoPlaybackDialog.jsx";

function Harness() {
  const { requestPlayDemo, DemoPlaybackUi } = useDemoPlaybackDialog();
  return <><button type="button" onClick={() => void requestPlayDemo({ id: 7, label: "match.dem" })}>open</button><DemoPlaybackUi /></>;
}

describe("useDemoPlaybackDialog", () => {
  beforeEach(() => {
    useLocaleStore.getState().hydrate("zh");
    getDemoPlaybackPreflight.mockReset();
    getDemoPlaybackStatus.mockReset();
    playDemoInCsgo.mockReset();
  });

  it("launches CS:GO playback without Source 2 options or aliases", async () => {
    getDemoPlaybackPreflight.mockResolvedValue({ csgo_path_configured: true, csgo_running: false });
    playDemoInCsgo.mockResolvedValue({ ok: true });
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    fireEvent.click(await screen.findByRole("button", { name: "在 CS:GO 中播放" }));
    await waitFor(() => expect(playDemoInCsgo).toHaveBeenCalledWith({ id: 7, path: null, playerAliases: {} }));
  });

  it("opens factual restoration monitoring for a playback session", async () => {
    getDemoPlaybackPreflight.mockResolvedValue({ csgo_path_configured: true, csgo_running: false });
    playDemoInCsgo.mockResolvedValue({ session_id: "session-7" });
    getDemoPlaybackStatus.mockResolvedValue({ found: true, state: "completed", player_config_restore: { verified: true } });
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    fireEvent.click(await screen.findByRole("button", { name: "在 CS:GO 中播放" }));
    await screen.findByText("玩家设置已恢复");
    expect(getDemoPlaybackStatus).toHaveBeenCalledWith("session-7");
  });

  it("shows a CS:GO running preflight block", async () => {
    getDemoPlaybackPreflight.mockResolvedValue({ csgo_path_configured: true, csgo_running: true });
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    expect(await screen.findByText(/CS:GO 正在运行/)).toBeTruthy();
  });
});
