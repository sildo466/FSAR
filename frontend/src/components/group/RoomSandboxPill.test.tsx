// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { initI18n } from "../../lib/i18nSetup";
import type { WorkspaceInfo } from "../../lib/ws-client";
import { useWS } from "../../stores/ws";
import { useWorkspace } from "../../stores/workspace";
import { isRestrictedSandbox, RoomSandboxPill } from "./RoomSandboxPill";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

function workspace(id: number, name: string, root: string): WorkspaceInfo {
  return {
    id, name, root_path: root, allowed_paths: ["**"], blocked_patterns: [],
    default_for_new: false, created_at: "", updated_at: "",
  };
}

const DRIVE = workspace(30, "computer", "C:\\");
const HOME = workspace(31, "home", "C:\\Users\\TANG");
const SANDBOX = workspace(1, "Sandbox", "C:\\Users\\TANG\\FSAR-workspace");
const PROJECT = workspace(2, "proj", "D:\\work\\proj");

describe("isRestrictedSandbox", () => {
  it("rejects a whole drive and the home directory, keeps anything narrower", () => {
    expect(isRestrictedSandbox(DRIVE)).toBe(false);
    expect(isRestrictedSandbox(HOME)).toBe(false);
    expect(isRestrictedSandbox(SANDBOX)).toBe(true);
    expect(isRestrictedSandbox(PROJECT)).toBe(true);
    expect(isRestrictedSandbox(workspace(3, "posix-home", "/home/me"))).toBe(false);
    expect(isRestrictedSandbox(workspace(4, "posix-home-slash", "/home/me/"))).toBe(false);
    expect(isRestrictedSandbox(workspace(5, "mac", "/Users/me"))).toBe(false);
    expect(isRestrictedSandbox(workspace(6, "posix-proj", "/home/me/work"))).toBe(true);
  });
});

describe("RoomSandboxPill", () => {
  const send = vi.fn();

  beforeEach(() => {
    send.mockClear();
    useWS.setState({ send });
    useWorkspace.setState({ workspaces: [DRIVE, HOME, SANDBOX, PROJECT] });
  });

  it("names the room's sandbox and never offers a whole drive", () => {
    render(<RoomSandboxPill roomId={7} sandboxWorkspaceId={SANDBOX.id} />);

    expect(screen.getByTestId("room-sandbox-pill")).toHaveTextContent("Sandbox");
    expect(screen.queryByText("computer")).toBeNull();

    fireEvent.click(screen.getByTestId("room-sandbox-pill"));
    expect(screen.getByText("proj")).toBeDefined();
    expect(screen.queryByText("computer")).toBeNull();
    expect(screen.queryByText("home")).toBeNull();
  });

  it("moves the sandbox through group.update", () => {
    render(<RoomSandboxPill roomId={7} sandboxWorkspaceId={SANDBOX.id} />);
    fireEvent.click(screen.getByTestId("room-sandbox-pill"));
    fireEvent.click(screen.getByTestId(`room-sandbox-option-${PROJECT.id}`));

    expect(send).toHaveBeenCalledWith({
      type: "group.update",
      room_id: 7,
      sandbox_workspace_id: PROJECT.id,
    });
  });

  it("shows a dash rather than guessing when the room has no sandbox yet", () => {
    render(<RoomSandboxPill roomId={7} sandboxWorkspaceId={null} />);
    expect(screen.getByTestId("room-sandbox-pill")).toHaveTextContent("—");
  });
});
