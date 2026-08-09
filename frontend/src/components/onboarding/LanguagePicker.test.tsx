// SPDX-License-Identifier: MIT
// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { LanguagePicker } from "./LanguagePicker";

const state = { locale: "en" };
const setLocale = vi.fn();

vi.mock("../../stores/locale", () => ({
  useLocale: (selector: (s: { locale: string; setLocale: (l: string) => Promise<void> }) => unknown) =>
    selector({ locale: state.locale, setLocale }),
}));

describe("LanguagePicker", () => {
  beforeEach(() => {
    setLocale.mockReset();
    state.locale = "en";
  });

  afterEach(() => {
    cleanup();
  });

  it("renders all 6 locales with native names", () => {
    render(<LanguagePicker />);
    for (const label of ["English", "简体中文", "繁體中文", "日本語", "Deutsch", "Français"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("clicking a locale calls setLocale", async () => {
    render(<LanguagePicker />);
    const btn = screen.getAllByText("日本語")[0].closest("button")!;
    fireEvent.click(btn);
    await waitFor(() => expect(setLocale).toHaveBeenCalledWith("ja"));
  });
});