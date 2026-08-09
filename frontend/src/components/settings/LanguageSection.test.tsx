// SPDX-License-Identifier: MIT
// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { LanguageSection } from "./LanguageSection";

const state = { locale: "en" };
const setLocale = vi.fn();

vi.mock("../../stores/locale", () => ({
  useLocale: (selector: (s: { locale: string; setLocale: (l: string) => Promise<void> }) => unknown) =>
    selector({ locale: state.locale, setLocale }),
}));

describe("LanguageSection", () => {
  beforeEach(() => {
    setLocale.mockReset();
    state.locale = "en";
  });

  afterEach(() => {
    cleanup();
  });

  it("renders all 6 locales", () => {
    render(<LanguageSection />);
    expect(screen.getByText("English")).toBeTruthy();
    expect(screen.getByText("简体中文")).toBeTruthy();
    expect(screen.getByText("繁體中文")).toBeTruthy();
    expect(screen.getByText("日本語")).toBeTruthy();
    expect(screen.getByText("Deutsch")).toBeTruthy();
    expect(screen.getByText("Français")).toBeTruthy();
  });

  it("clicking a locale calls setLocale", async () => {
    render(<LanguageSection />);
    const btn = screen.getAllByText("Deutsch")[0].closest("button")!;
    fireEvent.click(btn);
    await waitFor(() => expect(setLocale).toHaveBeenCalledWith("de"));
  });

  it("highlights the current locale", async () => {
    state.locale = "ja";
    render(<LanguageSection />);
    const btn = screen.getAllByText("日本語")[0].closest("button");
    expect(btn?.getAttribute("data-active")).toBe("true");
  });
});