// SPDX-License-Identifier: MIT
import { afterEach, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { useSpeechStore } from "../../stores/speech";
import { MessageReplayButton } from "./MessageReplayButton";

afterEach(cleanup);

it("is hidden when TTS is inactive and no regenerate handler", () => {
  useSpeechStore.setState({ isTtsConfigured: false });
  render(<MessageReplayButton messageId="m1" text="Hello" />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("shows play and regenerate actions", () => {
  useSpeechStore.setState({ isTtsConfigured: true, playingMessageId: null });
  render(<MessageReplayButton messageId="m1" text="Hello" onRegenerate={() => {}} />);
  expect(screen.getByRole("button", { name: "Play message" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Regenerate response" })).toBeInTheDocument();
});

it("shows regenerate even when TTS is inactive", () => {
  useSpeechStore.setState({ isTtsConfigured: false });
  render(<MessageReplayButton messageId="m1" text="Hello" onRegenerate={() => {}} />);
  expect(screen.queryByRole("button", { name: "Play message" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Regenerate response" })).toBeInTheDocument();
});
