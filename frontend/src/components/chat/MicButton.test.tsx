// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { useSpeechStore } from "../../stores/speech";
import { MicButton } from "./MicButton";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

it("is hidden without an active ASR provider", () => {
  useSpeechStore.setState({ isAsrConfigured: false });
  render(<MicButton onTranscript={() => {}} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("keeps a stable hook order when ASR becomes configured while mounted", () => {
  // A changing hook count throws React error #310 in a production build, which
  // blanks the whole app; the dev build only warns.
  const errors: string[] = [];
  const spy = vi.spyOn(console, "error").mockImplementation((...args) => {
    errors.push(String(args[0]));
  });
  useSpeechStore.setState({ isAsrConfigured: false });
  render(<MicButton onTranscript={() => {}} />);

  act(() => {
    useSpeechStore.setState({ isAsrConfigured: true });
  });
  spy.mockRestore();

  expect(screen.getByRole("button")).toBeInTheDocument();
  expect(errors.filter((message) => message.includes("order of Hooks"))).toEqual([]);
});

it("shows the click-to-toggle control when ASR is active", () => {
  useSpeechStore.setState({ isAsrConfigured: true });
  render(<MicButton onTranscript={() => {}} />);
  const button = screen.getByRole("button", { name: "Click to record" });
  expect(button).toBeInTheDocument();
  expect(button).toHaveAttribute("aria-pressed", "false");
});
