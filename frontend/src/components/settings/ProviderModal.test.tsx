// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import type { ClientMsg, ServerMsg } from "../../lib/ws-client";
import { useWS } from "../../stores/ws";
import { ProviderModal } from "./ProviderModal";

class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listeners = new Set<(message: ServerMsg) => void>();

  on(listener: (message: ServerMsg) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: ClientMsg) {
    this.sent.push(message);
  }
}

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

it("tests and fetches models through the backend websocket", async () => {
  const client = new FakeClient();
  const browserFetch = vi.spyOn(globalThis, "fetch");
  useWS.setState({
    client: client as never,
    config: { llm: { providers: [] } },
  });
  const { findByText, findByRole } = render(
    <ProviderModal
      open
      initial={{
        id: "test",
        preset_id: "openai",
        label: "Test",
        family: "openai_compat",
        base_url: "https://api.example.com/v1",
        api_key: "secret",
        model: "model-a",
      }}
      existingIds={["test"]}
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );

  const testButton = await findByRole("button", { name: "Test" });
  fireEvent.click(testButton);
  const fetchButton = await findByText("Fetch models");
  fireEvent.click(fetchButton);

  expect(browserFetch).not.toHaveBeenCalled();
  expect(client.sent).toContainEqual({
    type: "provider.test_connection",
    preset_id: "openai",
    base_url: "https://api.example.com/v1",
    api_key: "secret",
    model: "model-a",
  });
  expect(client.sent).toContainEqual({
    type: "provider.fetch_models",
    preset_id: "openai",
    base_url: "https://api.example.com/v1",
    api_key: "secret",
  });
  browserFetch.mockRestore();
});

it("preserves legacy provider family values when editing", async () => {
  const client = new FakeClient();
  useWS.setState({ client: client as never, config: { llm: { providers: [] } } });
  const { findByDisplayValue } = render(
    <ProviderModal
      open
      initial={{ id: "legacy", label: "Legacy", provider_family: "openai", model: "model-a" }}
      existingIds={["legacy"]}
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );

  await waitFor(async () => {
    expect(await findByDisplayValue("openai compatible")).toBeTruthy();
  });
});
