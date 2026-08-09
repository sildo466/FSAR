// SPDX-License-Identifier: MIT
import { afterEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { useSocialStore } from "../../../stores/social";
import { WeChatPanel } from "./WeChatPanel";

vi.mock("../../../clients/socialClient", () => ({
  beginWechatQr: vi.fn(async () => ({ qrcode: "q", scan_data: "s" })),
  resetWechatQr: vi.fn(async () => ({ qrcode: "q2", scan_data: "s2" })),
  checkWechatQr: vi.fn(async () => ({ status: "wait" })),
  patchSocial: vi.fn(async () => {}),
}));

vi.mock("../../../stores/cards", () => ({
  useCardsStore: (selector: (state: unknown) => unknown) =>
    selector({ characters: [], userCards: [], refresh: () => {} }),
}));

const config = { enabled: true, character_card_id: null, user_card_id: null };

afterEach(cleanup);

function setState(state: string) {
  useSocialStore.setState({
    statuses: {
      telegram: { platform: "telegram", state: "unknown" },
      feishu: { platform: "feishu", state: "unknown" },
      wechat: { platform: "wechat", state },
    },
  } as never);
}

it("hides the rescan control while no session is running", () => {
  setState("paused");
  render(<WeChatPanel config={config} />);
  expect(screen.queryByText("channels.wechat.rescan")).not.toBeInTheDocument();
});

it("offers rescan once a session is running", () => {
  setState("running");
  render(<WeChatPanel config={config} />);
  expect(screen.getByText("channels.wechat.rescan")).toBeInTheDocument();
});

it("requests a replacement QR rather than a fresh login on rescan", async () => {
  const { resetWechatQr, beginWechatQr } = await import("../../../clients/socialClient");
  setState("running");
  render(<WeChatPanel config={config} />);

  screen.getByText("channels.wechat.rescan").click();

  await waitFor(() => expect(resetWechatQr).toHaveBeenCalled());
  expect(beginWechatQr).not.toHaveBeenCalled();
});
