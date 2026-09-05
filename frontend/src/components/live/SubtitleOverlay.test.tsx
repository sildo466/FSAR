// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { SubtitleOverlay } from "./SubtitleOverlay";
import { initI18n } from "../../lib/i18nSetup";
import i18n from "../../lib/i18nSetup";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(() => cleanup());

const baseProps = { visible: true, onToggle: vi.fn() };

describe("SubtitleOverlay", () => {
  it("renders empty state label when no items", () => {
    render(<SubtitleOverlay items={[]} {...baseProps} />);
    expect(screen.getByText(i18n.t("live.subtitles"))).toBeTruthy();
  });

  it("renders user and assistant lines", () => {
    render(
      <SubtitleOverlay
        items={[
          { id: "1", role: "user", text: "hello" },
          { id: "2", role: "assistant", text: "hi there" },
        ]}
        {...baseProps}
      />
    );
    expect(screen.getByText("hello")).toBeTruthy();
    expect(screen.getByText("hi there")).toBeTruthy();
  });

  it("marks streaming lines", () => {
    render(
      <SubtitleOverlay
        items={[{ id: "3", role: "assistant", text: "thinking…", streaming: true }]}
        {...baseProps}
      />
    );
    expect(screen.getByText("thinking…")).toBeTruthy();
  });

  it("calls onToggle when the hide button is clicked", () => {
    render(<SubtitleOverlay items={[]} {...baseProps} />);
    const hideButtons = screen.getAllByRole("button", {
      name: i18n.t("live.subtitles.hide"),
    });
    fireEvent.click(hideButtons[0]);
    expect(baseProps.onToggle).toHaveBeenCalledTimes(1);
  });

  it("does not render the panel when hidden", () => {
    render(<SubtitleOverlay items={[{ id: "1", role: "user", text: "hidden" }]} visible={false} onToggle={vi.fn()} />);
    expect(screen.queryByText("hidden")).toBeNull();
  });
});
