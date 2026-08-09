// SPDX-License-Identifier: MIT
import { beforeEach, expect, it } from "vitest";
import type { ServerMsg } from "../lib/ws-client";
import { useWorkspace } from "./workspace";

class Client {
  listener?: (message: ServerMsg) => void;
  on(listener: (message: ServerMsg) => void) { this.listener = listener; return () => {}; }
}

beforeEach(() => useWorkspace.setState({ workspaces: [], currentBinding: null, bindings: {}, defaultId: null, hardlineClasses: [], sensitiveClasses: [], customSensitive: [], auditEvents: [], escapeRequest: null }));

it("hydrates sandbox state from snapshot", () => {
  const client = new Client();
  useWorkspace.getState().init(client as never);
  client.listener?.({
    type: "snapshot", config: {},
    workspace: { current_binding: null, default_workspace_id: 1, all_workspaces: [{ id: 1, name: "Sandbox", root_path: "C:\\workspace", allowed_paths: ["**"], blocked_patterns: [], default_for_new: true, created_at: "", updated_at: "" }] },
    security: { hardline_disabled_classes: [], power_user_mode: false, hardline_classes: [] },
    sensitive: { classes: [], custom: ["*/.npmrc"] },
  });
  expect(useWorkspace.getState().workspaces[0].name).toBe("Sandbox");
  expect(useWorkspace.getState().customSensitive).toEqual(["*/.npmrc"]);
});

it("stores an escape request", () => {
  const client = new Client();
  useWorkspace.getState().init(client as never);
  client.listener?.({ type: "tool.sandbox.request_escape", request_id: "esc", tool: "edit", operation: "edit", target_path: "x", reason: "outside", risk_level: "CRITICAL", context: { workspace_id: 1, workspace_root: "root", matched_rule: "outside_workspace", is_sensitive: false }, options: ["deny"] });
  expect(useWorkspace.getState().escapeRequest?.request_id).toBe("esc");
});
