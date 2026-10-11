// SPDX-License-Identifier: MIT
// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { initI18n } from "../../lib/i18nSetup";
import { PermissionsTab } from "./PermissionsTab";

vi.mock("../../stores/ws", () => {
  const state = { send: vi.fn(), client: null, config: { security: {} } };
  const useWS = (selector: (s: typeof state) => unknown) => selector(state);
  useWS.getState = () => state;
  return { useWS };
});

beforeAll(async () => {
  await initI18n("en");
});

afterEach(() => {
  cleanup();
});

describe("PermissionsTab", () => {
  it("offers the room command classifier switch", () => {
    render(
      <MemoryRouter>
        <PermissionsTab />
      </MemoryRouter>,
    );
    expect(screen.getByText("Judge room commands")).toBeTruthy();
  });
});
