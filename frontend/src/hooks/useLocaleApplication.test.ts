// SPDX-License-Identifier: MIT
// @vitest-environment jsdom
import { describe, expect, it, vi, beforeAll } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useLocaleApplication } from "./useLocaleApplication";
import { useLocale } from "../stores/locale";
import { initI18n } from "../lib/i18nSetup";

let configStyle: Record<string, unknown> | undefined = { locale: "zh-Hans" };

vi.mock("../stores/ws", () => {
  const subscribe = vi.fn();
  return {
    useWS: Object.assign(
      (selector: (s: { config: Record<string, unknown> | null }) => unknown) =>
        selector({ config: configStyle ? { style: configStyle } : null }),
      {
        subscribe: (cb: (s: { config: Record<string, unknown> | null }) => void) =>
          subscribe.mockImplementation(cb),
      },
    ),
  };
});

beforeAll(async () => {
  await initI18n("en");
});

describe("useLocaleApplication", () => {
  it("hydrates locale from initial ws config", async () => {
    configStyle = { locale: "zh-Hans" };
    useLocale.setState({ locale: "en", pendingLocale: null });
    renderHook(() => useLocaleApplication());
    await waitFor(() => {
      expect(useLocale.getState().locale).toBe("zh-Hans");
    });
  });

  it("ignores missing locale in config", async () => {
    configStyle = undefined;
    useLocale.setState({ locale: "en", pendingLocale: null });
    renderHook(() => useLocaleApplication());
    await waitFor(() => {
      expect(useLocale.getState().locale).toBe("en");
    });
  });
});