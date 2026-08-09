// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { useSpeechStore } from "../../stores/speech";
import { FasterWhisperModelPicker } from "./FasterWhisperModelPicker";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

const CATALOG = {
  downloaded: [],
  available: Object.keys({ tiny: 1, base: 1, small: 1, medium: 1, "large-v3": 1 }),
  sizes: { tiny: 75_000_000, base: 150_000_000, small: 500_000_000, medium: 1_500_000_000, "large-v3": 3_000_000_000 },
};

beforeEach(() => {
  useSpeechStore.setState({
    listDownloadedModels: vi.fn().mockResolvedValue(CATALOG),
    lastDownloadEndpoint: null,
  });
});

it("shows five explicit model sizes", async () => {
  render(<FasterWhisperModelPicker selected="" onSelect={() => {}} />);
  expect(await screen.findByText("large-v3")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /Download/ })).toHaveLength(5);
});

it("does not show the mirror hint when lastDownloadEndpoint is null", () => {
  render(<FasterWhisperModelPicker selected="" onSelect={() => {}} />);
  expect(screen.queryByText(/Using mirror:/)).not.toBeInTheDocument();
});

it("does not show the mirror hint when the source is official", () => {
  useSpeechStore.setState({
    lastDownloadEndpoint: { url: "https://huggingface.co", source: "official" },
  });
  render(<FasterWhisperModelPicker selected="" onSelect={() => {}} />);
  expect(screen.queryByText(/Using mirror:/)).not.toBeInTheDocument();
});

it("does not show the mirror hint when the source is override", () => {
  useSpeechStore.setState({
    lastDownloadEndpoint: { url: "https://my-mirror.example.com", source: "override" },
  });
  render(<FasterWhisperModelPicker selected="" onSelect={() => {}} />);
  expect(screen.queryByText(/Using mirror:/)).not.toBeInTheDocument();
});

it("shows the mirror hint when the source is mirror", () => {
  useSpeechStore.setState({
    lastDownloadEndpoint: { url: "https://hf-mirror.com", source: "mirror" },
  });
  render(<FasterWhisperModelPicker selected="" onSelect={() => {}} />);
  expect(screen.getByText("Using mirror: https://hf-mirror.com")).toBeInTheDocument();
});
