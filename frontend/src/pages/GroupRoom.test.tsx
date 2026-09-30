// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { useGroup } from "../stores/group";
import { useWS } from "../stores/ws";
import { initI18n } from "../lib/i18nSetup";
import { GroupRoom } from "./GroupRoom";

beforeAll(async () => {
  await initI18n("en");
});

class FakeClient {
  readonly sent: ClientMsg[] = [];
  private listeners = new Set<(message: ServerMsg) => void>();

  on(listener: (message: ServerMsg) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: ClientMsg) {
    this.sent.push(message);
  }

  emit(message: ServerMsg) {
    this.listeners.forEach((listener) => listener(message));
  }
}

afterEach(cleanup);

const ROOM = {
  id: 4, session_id: "s4", name: "Work", agent_mode: true, lan_enabled: false,
} as never;

function twoSteps() {
  return [
    { callId: "c1", tool: "read_file", argsPreview: "a", result: "ok", latencyMs: 1 },
    { callId: "c2", tool: "run_command", argsPreview: "ls" },
  ];
}

function setup(overrides: Record<string, unknown> = {}) {
  const client = new FakeClient();
  useWS.setState({ client: client as never, init: () => {} });
  useGroup.setState({
    rooms: [ROOM],
    currentRoomId: 4,
    messages: {},
    pendingRisks: {},
    elections: {},
    chainRunning: {},
    loadingHistory: {},
    context: {},
    agentMembers: {},
    lan: { status: null, blocklist: [], audit: [] },
    ...overrides,
  });
  useGroup.getState().init(client as never);
  return client;
}

function renderRoom() {
  return render(
    <MemoryRouter initialEntries={["/group/4"]}>
      <Routes>
        <Route path="/group/:roomId" element={<GroupRoom />} />
      </Routes>
    </MemoryRouter>
  );
}

function messageWithSteps() {
  return [{
    id: "m1",
    role: "assistant" as const,
    content: "done",
    character_id: 7,
    character_name: "Mira",
    tools: twoSteps(),
  }];
}

it("folds a character's tool steps in the room", () => {
  setup({ messages: { 4: messageWithSteps() } });
  renderRoom();

  // The room folds them: several characters can be mid-loop at once.
  expect(screen.getByTestId("folded-tool-steps").getAttribute("open")).toBeNull();
  expect(screen.getByText("run_command")).toBeTruthy();
});

it("asks the owner before a call the engine flagged", () => {
  const client = setup({
    messages: { 4: messageWithSteps() },
    pendingRisks: {
      4: [{ callId: "c2", tool: "run_command", argsPreview: "ls", risk: "HIGH" }],
    },
  });
  renderRoom();

  fireEvent.click(screen.getByText("Send anyway"));

  expect(client.sent).toContainEqual({
    type: "risk.respond", call_id: "c2", response: "y",
  });
});

it("opens the room to the network from inside the room", () => {
  const client = setup();
  renderRoom();

  fireEvent.click(screen.getByTestId("room-lan-toggle"));

  expect(client.sent).toContainEqual({
    type: "group.update", room_id: 4, lan_enabled: true,
  });
});
