// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ClientMsg } from "../../lib/ws-client";
import { initI18n } from "../../lib/i18nSetup";
import { useWS } from "../../stores/ws";
import { TierSwitcher } from "./TierSwitcher";

beforeAll(async () => {
  await initI18n("en");
});

class FakeClient {
  readonly sent: ClientMsg[] = [];

  send(message: ClientMsg) {
    this.sent.push(message);
  }
}

afterEach(cleanup);

it("shows the persisted tier and patches a new selection", () => {
  const client = new FakeClient();
  useWS.setState({
    client: client as never,
    config: { agent: { tier: "medium" } },
  });

  const { getByRole } = render(<TierSwitcher />);
  fireEvent.click(getByRole("button", { name: "Agent tier: Medium" }));
  fireEvent.click(getByRole("button", { name: /^Max\b/ }));

  expect(client.sent).toContainEqual({
    type: "settings.patch",
    patch: { "agent.tier": "max" },
  });
});

it("renders the Ultra row with a red warning description", () => {
  const client = new FakeClient();
  useWS.setState({
    client: client as never,
    config: { agent: { tier: "ultra" } },
  });

  render(<TierSwitcher />);
  fireEvent.click(screen.getByRole("button", { name: "Agent tier: Ultra" }));

  const description = screen.getByText(/May burn tokens and time/i);
  expect(description).toHaveClass("text-red-400");
  expect(description.textContent).toMatch(/^⚠/);
  expect(screen.getByText(/Adds planning, parallel tool use, and self-verification/i)).toBeInTheDocument();
});
