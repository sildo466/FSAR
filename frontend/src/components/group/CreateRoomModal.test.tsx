// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { CreateRoomModal } from "./CreateRoomModal";
import { useCardsStore, type CardSummary } from "../../stores/cards";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

function card(id: number, name: string): CardSummary {
  return { id, name, description: "", personality: "", is_default: 0 };
}

function seedCards() {
  useCardsStore.setState({
    characters: [card(7, "Mira"), card(8, "Kai")],
    userCards: [],
  });
}

it("blocks submit without a name", () => {
  seedCards();
  const onSubmit = vi.fn();
  render(<CreateRoomModal open onClose={() => {}} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByTestId("create-room-submit"));
  expect(onSubmit).not.toHaveBeenCalled();
});

it("blocks submit without any character", () => {
  seedCards();
  const onSubmit = vi.fn();
  render(<CreateRoomModal open onClose={() => {}} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByTestId("create-room-name"), {
    target: { value: "Island" },
  });
  fireEvent.click(screen.getByTestId("create-room-submit"));
  expect(onSubmit).not.toHaveBeenCalled();
});

it("submits name and selected characters", () => {
  seedCards();
  const onSubmit = vi.fn();
  render(<CreateRoomModal open onClose={() => {}} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByTestId("create-room-name"), {
    target: { value: "Island" },
  });
  fireEvent.click(screen.getByLabelText("Mira"));
  fireEvent.click(screen.getByTestId("create-room-submit"));
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({ name: "Island", character_ids: [7] })
  );
});

it("toggles a character off when clicked twice", () => {
  seedCards();
  const onSubmit = vi.fn();
  render(<CreateRoomModal open onClose={() => {}} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByTestId("create-room-name"), {
    target: { value: "Island" },
  });
  fireEvent.click(screen.getByLabelText("Mira"));
  fireEvent.click(screen.getByLabelText("Mira"));
  fireEvent.click(screen.getByTestId("create-room-submit"));
  expect(onSubmit).not.toHaveBeenCalled();
});

it("carries description and scenario through", () => {
  seedCards();
  const onSubmit = vi.fn();
  render(<CreateRoomModal open onClose={() => {}} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByTestId("create-room-name"), {
    target: { value: "Island" },
  });
  fireEvent.change(screen.getByTestId("create-room-description"), {
    target: { value: "stranded" },
  });
  fireEvent.change(screen.getByTestId("create-room-scenario"), {
    target: { value: "We must survive." },
  });
  fireEvent.click(screen.getByLabelText("Kai"));
  fireEvent.click(screen.getByTestId("create-room-submit"));
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({
      description: "stranded",
      scenario_prompt: "We must survive.",
      character_ids: [8],
    })
  );
});

it("renders nothing when closed", () => {
  seedCards();
  const { container } = render(
    <CreateRoomModal open={false} onClose={() => {}} onSubmit={vi.fn()} />
  );
  expect(container).toBeEmptyDOMElement();
});
