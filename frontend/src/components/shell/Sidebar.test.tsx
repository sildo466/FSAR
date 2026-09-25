// SPDX-License-Identifier: MIT
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { initI18n } from "../../lib/i18nSetup";
import { useWS } from "../../stores/ws";
import { Sidebar } from "./Sidebar";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(() => {
  cleanup();
  useWS.setState({ version: null });
});

it("renders the base tag from the snapshot", () => {
  useWS.setState({
    version: {
      tag: "v0.6.0-beta1-31-gad68159",
      base: "v0.6.0-beta1",
      channel: "beta",
      exact: false,
      source: "git",
    },
  });
  const screen = render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
  expect(screen.getByTestId("app-version").textContent).toBe("0.6.0-beta1");
  expect(screen.getByTestId("app-version").getAttribute("title")).toBe(
    "v0.6.0-beta1-31-gad68159",
  );
});

it("renders nothing when the snapshot has no version", () => {
  useWS.setState({ version: null });
  const screen = render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
  expect(screen.getByTestId("app-version").textContent).toBe("");
});
