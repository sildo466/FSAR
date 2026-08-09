// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ClientMsg } from "../../lib/ws-client";
import { initI18n } from "../../lib/i18nSetup";
import { useWS } from "../../stores/ws";
import { ModelEffortSwitcher } from "./ModelEffortSwitcher";

beforeAll(async () => {
  await initI18n("en");
});

class FakeClient {
  readonly sent: ClientMsg[] = [];

  send(message: ClientMsg) {
    this.sent.push(message);
  }
}

describe("ModelEffortSwitcher", () => {
  let client: FakeClient;

  beforeEach(() => {
    client = new FakeClient();
    useWS.setState({
      client: client as never,
      config: { llm: { model_thinking_effort: "off" } },
    });
  });

  afterEach(cleanup);

  it("renders Off as the default label", () => {
    render(<ModelEffortSwitcher />);
    expect(screen.getByRole("button", { name: "Model thinking effort: Off" })).toBeInTheDocument();
  });

  it("opens the dropdown with all six levels and descriptions", () => {
    render(<ModelEffortSwitcher />);
    fireEvent.click(screen.getByRole("button", { name: "Model thinking effort: Off" }));

    for (const label of ["Off", "Low", "Medium", "High", "XHigh", "Max"]) {
      expect(screen.getByRole("button", { name: new RegExp(`^${label}\\b`) })).toBeInTheDocument();
    }
    expect(screen.getByText(/Uses light reasoning for quicker responses/i)).toBeInTheDocument();
    expect(screen.getByText(/Uses the maximum reasoning depth the model supports/i)).toBeInTheDocument();
  });

  it("sends settings.patch when a level is selected", () => {
    render(<ModelEffortSwitcher />);
    fireEvent.click(screen.getByRole("button", { name: "Model thinking effort: Off" }));
    fireEvent.click(screen.getByRole("button", { name: /^High\b/ }));

    expect(client.sent).toContainEqual({
      type: "settings.patch",
      patch: { "llm.model_thinking_effort": "high" },
    });
  });
});
