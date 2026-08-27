// SPDX-License-Identifier: MIT
import { describe, expect, it, vi } from "vitest";
import { fetchModelList } from "./modelsApi";

describe("fetchModelList", () => {
  it("returns models array on success", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: async () => ({ models: ["a.vrm", "b.vrm"] }),
      } as Response)
    ));
    expect(await fetchModelList()).toEqual(["a.vrm", "b.vrm"]);
  });

  it("returns [] on network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("down"))));
    expect(await fetchModelList()).toEqual([]);
  });

  it("returns [] when response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({ ok: false } as Response)
    ));
    expect(await fetchModelList()).toEqual([]);
  });
});
