import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { useLocaleStore } from "../../i18n/localeStore.js";
import QueueWorkspaceRow from "./QueueWorkspaceRow.jsx";

function renderRow() {
  return render(
    <QueueWorkspaceRow
      item={{
        demoFilename: "match.dem",
        demoPath: "C:/demos/match.dem",
        targetPlayer: "alpha",
        clipData: {
          category: "highlight",
          clip_id: "clip-1",
          map_name: "de_mirage",
          round: 12,
        },
      }}
      priorityIndex={1}
      selected={false}
      onSelect={() => {}}
      onRemove={() => {}}
      globalPacing={{}}
    />,
  );
}

describe("QueueWorkspaceRow", () => {
  beforeEach(() => {
    useLocaleStore.setState({
      locale: "zh",
      effectiveLocale: "zh",
      hydrated: true,
      persistenceError: null,
    });
  });

  test("does not render retired Source 2 input HUD warnings", () => {
    renderRow();
    expect(screen.queryByTestId("queue-input-hud-warning")).toBeNull();
  });
});
