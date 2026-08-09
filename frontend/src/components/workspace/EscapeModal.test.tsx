// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { EscapeModal } from "./EscapeModal";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

const request = {
  request_id: "esc-1",
  tool: "file_ops",
  operation: "read",
  target_path: "C:\\Users\\me\\secret.txt",
  reason: "path is outside the active workspace",
  risk_level: "CRITICAL" as const,
  context: { workspace_id: 1, workspace_root: "C:\\workspace", matched_rule: "outside_workspace", is_sensitive: false },
  options: ["deny", "allow_once", "allow_session", "allow_always"] as const,
};

it("shows the boundary context and submits allow once", () => {
  const decide = vi.fn();
  const screen = render(<EscapeModal request={{ ...request, options: [...request.options] }} onDecision={decide} />);
  expect(screen.getByText("Leave this workspace?")).toBeTruthy();
  expect(screen.getByText("C:\\Users\\me\\secret.txt")).toBeTruthy();
  fireEvent.click(screen.getByText("Allow once"));
  expect(decide).toHaveBeenCalledWith("allow_once");
});
