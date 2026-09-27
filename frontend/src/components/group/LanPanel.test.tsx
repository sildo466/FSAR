// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { LanPanel } from "./LanPanel";
import { useGroup } from "../../stores/group";
import type { AuthAuditEvent, LanStatus } from "../../lib/ws-client";

beforeAll(async () => {
  await initI18n("en");
});

beforeEach(() => {
  useGroup.setState({ lan: { status: null, blocklist: [], audit: [] } });
});

afterEach(cleanup);

const LISTENING: LanStatus = {
  enabled: true,
  listening: true,
  host: "0.0.0.0",
  port: 8766,
  fingerprint: "AB:CD",
  lan_rooms: 1,
  error: "",
  addresses: ["https://192.168.1.20:8766"],
  agent_md_hint: 'curl -k -H "Authorization: Bearer $FSAR_ROOM_TOKEN" ...',
};

function seed(
  status: Partial<LanStatus> = {},
  blocklist: { ip: string; reason: string; created_at: string }[] = [],
  audit: AuthAuditEvent[] = [],
  { withStatus = true } = {}
) {
  useGroup.setState({
    lan: {
      status: withStatus ? { ...LISTENING, ...status } : null,
      blocklist,
      audit,
    },
  });
}

function denial(overrides: Partial<AuthAuditEvent>): AuthAuditEvent {
  return {
    seq: 1, created_at: "t", action: "lan_auth", result: "deny",
    reason: "ip_mismatch", room_id: 1, member_ref: "claude-laptop",
    token_id: 12, source_ip: "10.0.0.9", detail: "",
    ...overrides,
  };
}

it("shows whether the listener is up", () => {
  seed();
  render(<LanPanel onClose={() => {}} />);
  expect(screen.getByTestId("lan-status")).toHaveTextContent(/listening/i);
});

it("says so when the setting is off", () => {
  seed({ enabled: false, listening: false, addresses: [] });
  render(<LanPanel onClose={() => {}} />);
  expect(screen.getByTestId("lan-status")).toHaveTextContent(/closed/i);
});

it("shows the setting, not the socket, and says why it is not running", () => {
  // The state that looked like "the switch does nothing": the setting is on,
  // the listener could not start.
  seed({
    enabled: true,
    listening: false,
    addresses: [],
    error: "cannot listen on 0.0.0.0:8766",
  });
  render(<LanPanel onClose={() => {}} />);
  const toggle = screen.getByTestId("lan-master-switch") as HTMLInputElement;
  expect(toggle.checked).toBe(true);
  expect(screen.getByTestId("lan-status")).toHaveTextContent(/not running/i);
  expect(screen.getByTestId("lan-error")).toHaveTextContent("0.0.0.0:8766");
});

it("leaves the switch unticked when the setting is off", () => {
  seed({ enabled: false, listening: false, addresses: [] });
  render(<LanPanel onClose={() => {}} />);
  const toggle = screen.getByTestId("lan-master-switch") as HTMLInputElement;
  expect(toggle.checked).toBe(false);
});

it("lists the addresses to hand over and the fingerprint", () => {
  seed();
  render(<LanPanel onClose={() => {}} />);
  expect(screen.getByTestId("lan-url-0")).toHaveTextContent(
    "https://192.168.1.20:8766"
  );
  expect(screen.getByTestId("lan-fingerprint")).toHaveTextContent("AB:CD");
});

it("offers the handoff line as read-only text", () => {
  seed();
  render(<LanPanel onClose={() => {}} />);
  const handoff = screen.getByTestId("lan-handoff") as HTMLInputElement;
  expect(handoff.value).toContain("$FSAR_ROOM_TOKEN");
  expect(handoff.readOnly).toBe(true);
});

it("surfaces a listener error instead of hiding it", () => {
  seed({ enabled: true, listening: false, error: "OSError: address in use" });
  render(<LanPanel onClose={() => {}} />);
  expect(screen.getByTestId("lan-error")).toHaveTextContent("address in use");
});

it("blocks an address from the form", () => {
  seed();
  const block = vi.fn();
  useGroup.setState({ blockIp: block });
  render(<LanPanel onClose={() => {}} />);
  fireEvent.change(screen.getByTestId("block-ip-input"), {
    target: { value: "10.0.0.9" },
  });
  fireEvent.click(screen.getByTestId("block-ip-submit"));
  expect(block).toHaveBeenCalledWith("10.0.0.9", "");
});

it("does not block a blank address", () => {
  seed();
  const block = vi.fn();
  useGroup.setState({ blockIp: block });
  render(<LanPanel onClose={() => {}} />);
  fireEvent.change(screen.getByTestId("block-ip-input"), {
    target: { value: "   " },
  });
  fireEvent.click(screen.getByTestId("block-ip-submit"));
  expect(block).not.toHaveBeenCalled();
});

it("lists blocked addresses and unblocks them", () => {
  seed({}, [
    { ip: "10.0.0.9", reason: "noise", created_at: "2026-09-27T10:00:00" },
  ]);
  const unblock = vi.fn();
  useGroup.setState({ unblockIp: unblock });
  render(<LanPanel onClose={() => {}} />);
  expect(screen.getByTestId("blocked-ip-10.0.0.9")).toHaveTextContent("10.0.0.9");
  fireEvent.click(screen.getByTestId("unblock-10.0.0.9"));
  expect(unblock).toHaveBeenCalledWith("10.0.0.9");
});

it("offers a rebind only for address-mismatch rows", () => {
  seed({}, [], [
    denial({ seq: 7 }),
    denial({ seq: 6, reason: "token_unknown", token_id: null, member_ref: null }),
  ]);
  const rebind = vi.fn();
  useGroup.setState({ rebindIp: rebind });
  render(<LanPanel onClose={() => {}} />);
  fireEvent.click(screen.getByTestId("rebind-7"));
  expect(rebind).toHaveBeenCalledWith(12, "10.0.0.9");
  expect(screen.queryByTestId("rebind-6")).toBeNull();
});

it("asks for status, blocklist and audit on mount", () => {
  const refreshStatus = vi.fn();
  const refreshBlocklist = vi.fn();
  const refreshAudit = vi.fn();
  useGroup.setState({
    refreshLanStatus: refreshStatus,
    refreshLanBlocklist: refreshBlocklist,
    refreshAuthAudit: refreshAudit,
  });
  seed();
  render(<LanPanel onClose={() => {}} />);
  expect(refreshStatus).toHaveBeenCalled();
  expect(refreshBlocklist).toHaveBeenCalled();
  expect(refreshAudit).toHaveBeenCalledWith(50);
});

it("saves the master switch and then re-reads the status", () => {
  const send = vi.fn();
  const refreshStatus = vi.fn();
  useGroup.setState({ send, refreshLanStatus: refreshStatus });
  seed({ enabled: false, listening: false });
  render(<LanPanel onClose={() => {}} />);
  fireEvent.click(screen.getByTestId("lan-master-switch"));
  expect(send).toHaveBeenCalledWith({
    type: "settings.patch",
    patch: { "lan.enabled": true },
  });
  // Without this the switch would look stuck until the next mount.
  expect(refreshStatus).toHaveBeenCalled();
});

it("renders nothing about addresses while the status is unknown", () => {
  seed({}, [], [], { withStatus: false });
  render(<LanPanel onClose={() => {}} />);
  expect(screen.queryByTestId("lan-url-0")).toBeNull();
  expect(screen.queryByTestId("lan-handoff")).toBeNull();
});
