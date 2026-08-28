// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SubtitleOverlay } from "./SubtitleOverlay";
import { initI18n } from "../../lib/i18nSetup";
import i18n from "../../lib/i18nSetup";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(() => cleanup());

describe("SubtitleOverlay", () => {
  it("renders empty state label when no items", () => {
    render(<SubtitleOverlay items={[]} />);
    expect(screen.getByText(i18n.t("live.subtitles"))).toBeTruthy();
  });

  it("renders user and assistant lines", () => {
    render(
      <SubtitleOverlay
        items={[
          { id: "1", role: "user", text: "hello" },
          { id: "2", role: "assistant", text: "hi there" },
        ]}
      />
    );
    expect(screen.getByText("hello")).toBeTruthy();
    expect(screen.getByText("hi there")).toBeTruthy();
  });

  it("marks streaming lines", () => {
    render(
      <SubtitleOverlay
        items={[{ id: "3", role: "assistant", text: "thinking…", streaming: true }]}
      />
    );
    expect(screen.getByText("thinking…")).toBeTruthy();
  });
});
