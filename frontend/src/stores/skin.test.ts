// SPDX-License-Identifier: MIT
import { beforeEach, expect, it } from "vitest";
import { useSkinStore, type Skin } from "./skin";

const warm: Skin = { id: "warm", name: "暖阳", base: "light", palette: { bg: "#faf8f5", accent: "#d4a04a" } };
let sent: Array<Record<string, unknown>> = [];
const send = (m: Record<string, unknown>) => { sent.push(m); };

beforeEach(() => {
  sent = [];
  useSkinStore.setState({ skins: [], status: "idle", activeId: "default" });
});

it("setActive applies optimistically and sends skin.set_active", () => {
  useSkinStore.getState().setActive(send, "warm");
  expect(useSkinStore.getState().activeId).toBe("warm");
  expect(sent).toEqual([{ type: "skin.set_active", skin_id: "warm" }]);
  useSkinStore.getState().setActive(send, "default");
  expect(sent).toEqual([
    { type: "skin.set_active", skin_id: "warm" },
    { type: "skin.set_active", skin_id: "default" },
  ]);
});

it("hydrate accepts string ids and ignores non-strings", () => {
  useSkinStore.getState().hydrate("night");
  expect(useSkinStore.getState().activeId).toBe("night");
  useSkinStore.getState().hydrate(undefined);
  expect(useSkinStore.getState().activeId).toBe("night");
});

it("receiveList stores skins and marks ready", () => {
  useSkinStore.getState().receiveList([warm]);
  expect(useSkinStore.getState().skins).toEqual([warm]);
  expect(useSkinStore.getState().status).toBe("ready");
});
