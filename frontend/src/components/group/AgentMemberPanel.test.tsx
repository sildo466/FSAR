// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { AgentMemberPanel } from "./AgentMemberPanel";
import { useGroup } from "../../stores/group";
import type { AgentMemberSummary, RoomSummary } from "../../lib/ws-client";

beforeAll(async () => {
  await initI18n("en");
});

beforeEach(() => {
  useGroup.setState({ agentMembers: {} });
});

afterEach(cleanup);

function room(agentMembers: AgentMemberSummary[]): RoomSummary {
  return {
    id: 1,
    name: "Room",
    description: "",
    scenario_prompt: "",
    session_id: "s1",
    user_card_id: null,
    pinned: false,
    max_rounds: 0,
    created_at: "",
    updated_at: "",
    members: [7],
    agent_mode: true,
    lan_enabled: false,
    agent_members: agentMembers,
  };
}

const active = { ref: "claude-laptop", display_name: "Claude", state: "active" };

it("lists an agent member with its state", () => {
  render(<AgentMemberPanel room={room([active])} onClose={() => {}} />);
  expect(screen.getByTestId("agent-member-claude-laptop")).toHaveTextContent(
    "Claude"
  );
  expect(screen.getByTestId("agent-member-claude-laptop")).toHaveTextContent(
    "claude-laptop"
  );
});

it("asks to mute an active member", () => {
  const mute = vi.fn();
  useGroup.setState({ muteAgentMember: mute });
  render(<AgentMemberPanel room={room([active])} onClose={() => {}} />);
  fireEvent.click(screen.getByTestId("mute-claude-laptop"));
  expect(mute).toHaveBeenCalledWith(1, "claude-laptop", true);
});

it("asks to unmute a muted member", () => {
  const mute = vi.fn();
  useGroup.setState({ muteAgentMember: mute });
  render(
    <AgentMemberPanel
      room={room([{ ...active, state: "muted" }])}
      onClose={() => {}}
    />
  );
  fireEvent.click(screen.getByTestId("mute-claude-laptop"));
  expect(mute).toHaveBeenCalledWith(1, "claude-laptop", false);
});

it("asks to kick a member", () => {
  const kick = vi.fn();
  useGroup.setState({ removeAgentMember: kick });
  render(<AgentMemberPanel room={room([active])} onClose={() => {}} />);
  fireEvent.click(screen.getByTestId("kick-claude-laptop"));
  expect(kick).toHaveBeenCalledWith(1, "claude-laptop");
});

it("issues a token for a member", () => {
  const issue = vi.fn();
  useGroup.setState({ issueMemberToken: issue });
  render(<AgentMemberPanel room={room([active])} onClose={() => {}} />);
  fireEvent.click(screen.getByTestId("issue-token-claude-laptop"));
  expect(issue).toHaveBeenCalledWith(1, "claude-laptop");
});

it("lists token metadata and asks to revoke one", () => {
  const revoke = vi.fn();
  useGroup.setState({
    revokeMemberToken: revoke,
    agentMembers: {
      1: [
        {
          ...active,
          tokens: [
            {
              id: 4,
              label: "laptop",
              created_at: "t",
              last_used_at: null,
              revoked_at: null,
            },
            {
              id: 5,
              label: "old",
              created_at: "t",
              last_used_at: null,
              revoked_at: "t2",
            },
          ],
        },
      ],
    },
  });
  render(<AgentMemberPanel room={room([active])} onClose={() => {}} />);
  expect(screen.getByTestId("agent-token-4")).toHaveTextContent("#4");
  fireEvent.click(screen.getByTestId("revoke-token-4"));
  expect(revoke).toHaveBeenCalledWith(1, "claude-laptop", 4);
  // An already revoked token offers no second revoke.
  expect(screen.queryByTestId("revoke-token-5")).toBeNull();
});

it("adds a member from the form", () => {
  const add = vi.fn();
  useGroup.setState({ addAgentMember: add });
  render(<AgentMemberPanel room={room([])} onClose={() => {}} />);
  fireEvent.change(screen.getByTestId("agent-ref-input"), {
    target: { value: "codex" },
  });
  fireEvent.change(screen.getByTestId("agent-display-name-input"), {
    target: { value: "Codex" },
  });
  fireEvent.click(screen.getByTestId("add-agent-submit"));
  expect(add).toHaveBeenCalledWith(1, "codex", "Codex");
});

it("falls back to the ref when no display name is given", () => {
  const add = vi.fn();
  useGroup.setState({ addAgentMember: add });
  render(<AgentMemberPanel room={room([])} onClose={() => {}} />);
  fireEvent.change(screen.getByTestId("agent-ref-input"), {
    target: { value: "codex" },
  });
  fireEvent.click(screen.getByTestId("add-agent-submit"));
  expect(add).toHaveBeenCalledWith(1, "codex", "codex");
});

it("stops every chain on demand", () => {
  const stop = vi.fn();
  useGroup.setState({ stopAllChains: stop });
  render(<AgentMemberPanel room={room([active])} onClose={() => {}} />);
  fireEvent.click(screen.getByTestId("stop-all-chains"));
  expect(stop).toHaveBeenCalled();
});

it("says so when there are no agent members yet", () => {
  render(<AgentMemberPanel room={room([])} onClose={() => {}} />);
  expect(screen.getByTestId("agent-members-empty")).toBeInTheDocument();
});
