// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ClientMsg } from "../../lib/ws-client";
import { initI18n } from "../../lib/i18nSetup";
import { useWS } from "../../stores/ws";
import { StepAsr } from "./StepAsr";

class Client { sent: ClientMsg[] = []; send(message: ClientMsg) { this.sent.push(message); } }

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

it("renders all three ASR presets", () => {
  useWS.setState({ config: { asr: { active: "", providers: [] } } });
  render(<StepAsr onNext={() => {}} onSkip={() => {}} />);
  expect(screen.getByRole("button", { name: /faster-whisper/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /OpenAI Whisper/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Volcengine ASR/ })).toBeDisabled();
});

it("skips without writing providers", () => {
  const client = new Client();
  useWS.setState({ client: client as never, config: { asr: { active: "", providers: [] } } });
  render(<StepAsr onNext={() => {}} onSkip={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Skip setup" }));
  expect(client.sent).toEqual([{ type: "onboarding.skip_step", step: "asr" }]);
});
