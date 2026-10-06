// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { PlanBoard } from "./PlanBoard";
import type { PlanItem } from "../../stores/group";

const items: PlanItem[] = [
  { item_key: "a", text: "parse the config", status: "done",
    owner_kind: "character", owner_ref: "7", evidence: "ok",
    commit_ref: "abc1234def" },
  { item_key: "b", text: "write the tests", status: "doing",
    owner_kind: "character", owner_ref: "8", evidence: "", commit_ref: null },
  { item_key: "c", text: "ship it", status: "todo",
    owner_kind: null, owner_ref: null, evidence: "", commit_ref: null },
];

const names = { "7": "Mira", "8": "Irena" };

afterEach(cleanup);

describe("PlanBoard", () => {
  it("shows every item's text", () => {
    render(<PlanBoard items={items} names={names} />);
    expect(screen.getByText("parse the config")).toBeTruthy();
    expect(screen.getByText("ship it")).toBeTruthy();
  });

  it("carries each item's status on the row", () => {
    render(<PlanBoard items={items} names={names} />);
    const rows = screen.getAllByTestId("plan-item");
    expect(rows.map((r) => r.getAttribute("data-status"))).toEqual([
      "done", "doing", "todo",
    ]);
  });

  it("resolves an owner ref to the room's name for it", () => {
    render(<PlanBoard items={items} names={names} />);
    expect(screen.getByText("Mira")).toBeTruthy();
    expect(screen.getByText("Irena")).toBeTruthy();
  });

  it("falls back to the ref when the name is not known", () => {
    render(<PlanBoard items={items} names={{}} />);
    expect(screen.getByText("7")).toBeTruthy();
  });

  it("marks an unowned item as unowned rather than as an empty name", () => {
    render(<PlanBoard items={items} names={names} />);
    const rows = screen.getAllByTestId("plan-item");
    expect(rows[2].getAttribute("data-owner")).toBe("");
    expect(rows[0].getAttribute("data-owner")).toBe("7");
  });

  it("shows the promoted commit for a finished item", () => {
    render(<PlanBoard items={items} names={names} />);
    expect(screen.getByTestId("plan-commit").textContent).toBe("abc1234");
  });

  it("shows no commit for an item that has not been promoted", () => {
    render(<PlanBoard items={items} names={names} />);
    expect(screen.getAllByTestId("plan-commit")).toHaveLength(1);
  });

  it("renders an empty board as a line of prose, not as nothing", () => {
    render(<PlanBoard items={[]} names={names} />);
    expect(screen.getByTestId("plan-empty")).toBeTruthy();
    expect(screen.queryByTestId("plan-board")).toBeNull();
  });
});
