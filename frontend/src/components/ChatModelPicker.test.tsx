// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ClientMsg } from "../lib/ws-client";
import { initI18n } from "../lib/i18nSetup";
import { useWS } from "../stores/ws";

vi.mock("../clients/chatClient", () => ({
  chatClient: {
    snapshot: vi.fn(async () => ({
      chat_models: [
        { kind: "model", provider: "openai", model: "gpt-4o", label: "GPT-4o", est_calls: 1 },
        { kind: "integration", id: 7, label: "Deep Team", est_calls: 4 },
      ],
      selected_chat_model: { kind: "model", provider: "anthropic", model: "claude" },
    })),
  },
}));

vi.mock("../clients/integrationClient", () => ({
  integrationClient: {
    list: vi.fn(async () => [
      { id: 7, name: "Deep Team", description: "", main_model_id: 0, rounds: 2, max_depth: 2, max_subs_picked: 2, subs: [], est_calls: 4 },
    ]),
  },
}));

import { ChatModelPicker } from "./ChatModelPicker";
import { chatClient } from "../clients/chatClient";

class FakeClient {
  readonly sent: ClientMsg[] = [];

  send(message: ClientMsg) {
    this.sent.push(message);
  }
}

describe("ChatModelPicker", () => {
  let client: FakeClient;

  beforeAll(async () => {
    await initI18n("en");
  });

  beforeEach(() => {
    vi.mocked(chatClient.snapshot).mockImplementation(async () => ({
      chat_models: [
        { kind: "model", provider: "openai", model: "gpt-4o", label: "GPT-4o", est_calls: 1 },
        { kind: "integration", id: 7, label: "Deep Team", est_calls: 4 },
      ],
      selected_chat_model: { kind: "model", provider: "anthropic", model: "claude" },
    }));
    client = new FakeClient();
    useWS.setState({
      client: client as never,
      config: {
        llm: {
          active: "anthropic",
          providers: [
            { id: "anthropic", model: "claude", label: "Claude" },
            { id: "openai", model: "gpt-4o", label: "GPT-4o" },
          ],
        },
        chat: {},
      },
    });
  });

  afterEach(cleanup);

  it("sends settings.patch and llm.set_active when picking a single model", async () => {
    render(<ChatModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Chat model/i }));
    fireEvent.click(await screen.findByRole("button", { name: /GPT-4o/ }));

    expect(client.sent).toContainEqual({
      type: "settings.patch",
      patch: { "chat.default_model": { kind: "model", provider: "openai", model: "gpt-4o" } },
    });
    expect(client.sent).toContainEqual({ type: "llm.set_active", provider_id: "openai" });
  });

  it("sends only settings.patch when picking an integration", async () => {
    render(<ChatModelPicker />);
    fireEvent.click(screen.getByRole("button", { name: /Chat model/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Deep Team/ }));

    expect(client.sent).toContainEqual({
      type: "settings.patch",
      patch: { "chat.default_model": { kind: "integration", id: 7 } },
    });
    expect(client.sent.some((message) => message.type === "llm.set_active")).toBe(false);
  });

  it("shows a loading placeholder instead of a wrong single model while integrations load", () => {
    vi.mocked(chatClient.snapshot).mockReturnValue(new Promise(() => undefined));
    useWS.setState({
      config: {
        llm: {
          active: "anthropic",
          providers: [{ id: "anthropic", model: "claude", label: "Claude" }],
        },
        chat: { default_model: { kind: "integration", id: 7 } },
      },
    });

    render(<ChatModelPicker />);
    const trigger = screen.getByRole("button", { name: /Chat model/i });
    expect(trigger).toHaveTextContent("Loading…");
    expect(trigger).not.toHaveTextContent("Claude");
  });
});
