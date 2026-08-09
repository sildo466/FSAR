// SPDX-License-Identifier: MIT
import { afterEach, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ClientMsg } from "../../lib/ws-client";
import { useSpeechStore } from "../../stores/speech";
import { useWS } from "../../stores/ws";
import { TtsAutoplayToggle } from "./TtsAutoplayToggle";

class Client { sent: ClientMsg[] = []; send(message: ClientMsg) { this.sent.push(message); } }
afterEach(cleanup);

it("is hidden without an active TTS provider", () => {
  useSpeechStore.setState({ isTtsConfigured: false });
  render(<TtsAutoplayToggle />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("patches autoplay on click", () => {
  const client = new Client();
  useWS.setState({ client: client as never });
  useSpeechStore.setState({ isTtsConfigured: true, autoplay: false });
  render(<TtsAutoplayToggle />);
  fireEvent.click(screen.getByRole("button"));
  expect(client.sent).toContainEqual({ type: "settings.patch", patch: { "tts.autoplay": true } });
});
