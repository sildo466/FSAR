// SPDX-License-Identifier: Apache-2.0
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";
import { useCardsStore } from "../stores/cards";
import { useWS } from "../stores/ws";
import { Cards } from "./Cards";

vi.mock("../components/ui/AvatarCropDialog", () => ({
  AvatarCropDialog: ({
    open,
    onConfirm,
  }: {
    open: boolean;
    onConfirm: (blob: Blob) => void;
  }) => open ? (
    <button data-testid="avatar-crop-confirm" onClick={() => onConfirm(new Blob(["avatar"], { type: "image/jpeg" }))}>
      Use avatar
    </button>
  ) : null,
}));

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

let detachCards = () => {};

beforeEach(() => {
  useCardsStore.setState({
    characters: [],
    userCards: [],
    defaultUserCard: null,
    sessionCharacters: {},
    draftCharacterId: null,
  });
});

afterEach(() => {
  detachCards();
  detachCards = () => {};
  vi.unstubAllGlobals();
  cleanup();
});

function setup() {
  const client = new FakeClient();
  useWS.setState({ client: client as never });
  detachCards = useCardsStore.getState().init(client as never);
  return client;
}

describe("Cards", () => {
  it("creates a user card through the active WebSocket client", async () => {
    const client = setup();
    const screen = render(<Cards />);

    fireEvent.click(screen.getByRole("button", { name: /^User / }));
    fireEvent.click(screen.getByRole("button", { name: "+ New User" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Test User" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Saved over WS" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const request = client.sent.find(
      (message): message is Extract<ClientMsg, { type: "card.upsert" }> => message.type === "card.upsert",
    );
    expect(request?.kind).toBe("user");
    expect(request?.card).toMatchObject({ name: "Test User", description: "Saved over WS" });

    await act(async () => {
      client.emit({ type: "card.upserted", kind: "user", id: 42 });
    });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Cards" })).toBeTruthy());
  });

  it("creates a character with editable initial emotion values and formulas", async () => {
    const client = setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ avatar_path: "avatars/43.jpg" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const screen = render(<Cards />);

    fireEvent.click(screen.getByRole("button", { name: "+ New Character" }));
    expect((screen.getByTestId("emotion-initial-affection") as HTMLInputElement).value).toBe("50");
    expect((screen.getByTestId("emotion-formula-energy") as HTMLInputElement).value).toBe("energy - 0.5");

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Dynamic Character" } });
    fireEvent.change(screen.getByTestId("emotion-initial-affection"), { target: { value: "72" } });
    fireEvent.change(screen.getByTestId("emotion-formula-energy"), { target: { value: "energy - 0.25" } });
    fireEvent.change(screen.getByTestId("avatar-upload-input"), {
      target: { files: [new File(["image"], "avatar.jpg", { type: "image/jpeg" })] },
    });
    fireEvent.click(await screen.findByTestId("avatar-crop-confirm"));
    await screen.findByText("Avatar ready — click Save to apply it.");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const request = client.sent.find(
      (message): message is Extract<ClientMsg, { type: "card.upsert" }> => message.type === "card.upsert",
    );
    const card = request?.card as Record<string, unknown> | undefined;
    const schema = card?.emotion_schema as Array<Record<string, unknown>> | undefined;
    expect(request?.kind).toBe("character");
    expect(card?.emotion_state).toMatchObject({ affection: 72 });
    expect(schema?.find((metric) => metric.key === "affection")?.initial).toBe(72);
    expect(card?.emotion_formulas).toMatchObject({ energy: "energy - 0.25" });

    await act(async () => {
      client.emit({ type: "card.upserted", kind: "character", id: 43 });
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/card/43/avatar",
      expect.objectContaining({ method: "POST", body: expect.any(Blob) }),
    ));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Cards" })).toBeTruthy());
  });

  it("preserves an existing avatar path when saving card fields", async () => {
    const client = setup();
    useCardsStore.setState({
      characters: [{
        id: 7,
        name: "Avatar Character",
        description: "",
        personality: "calm",
        is_default: 0,
        avatar_path: "avatars/7.jpg",
      }],
    });
    const screen = render(<Cards />);

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Updated" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const request = client.sent.find(
      (message): message is Extract<ClientMsg, { type: "card.upsert" }> => message.type === "card.upsert",
    );
    expect(request?.card).toMatchObject({
      id: 7,
      description: "Updated",
      avatar_path: "avatars/7.jpg",
    });

    await act(async () => {
      client.emit({ type: "card.upserted", kind: "character", id: 7 });
    });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Cards" })).toBeTruthy());
  });
});
