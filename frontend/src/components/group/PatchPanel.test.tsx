// SPDX-License-Identifier: MIT
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { PatchPanel } from "./PatchPanel";
import type { PatchItem } from "../../stores/group";

function _patch(id: number, over: Partial<PatchItem> = {}): PatchItem {
  return {
    id,
    room_id: 1,
    member_ref: "claude-laptop",
    item_key: "parse",
    digest: "a".repeat(64),
    size: 120,
    state: "pending",
    verdict_reason: "",
    decided_by: null,
    created_at: "2026-10-01T00:00:00Z",
    decided_at: null,
    ...over,
  };
}

const props = { texts: {}, onLoad: () => {}, onDecide: () => {} };

afterEach(cleanup);

describe("PatchPanel", () => {
  it("renders an empty queue as a line of prose, not as nothing", () => {
    render(<PatchPanel patches={[]} {...props} />);
    expect(screen.getByTestId("patch-empty")).toBeTruthy();
    expect(screen.queryByTestId("patch-list")).toBeNull();
  });

  it("carries each patch's state and sender on the row", () => {
    render(
      <PatchPanel
        patches={[
          _patch(1),
          _patch(2, { member_ref: "other-box", state: "landed" }),
        ]}
        {...props}
      />,
    );
    const rows = screen.getAllByTestId("patch-item");
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual([
      "pending", "landed",
    ]);
    expect(rows.map((r) => r.getAttribute("data-member"))).toEqual([
      "claude-laptop", "other-box",
    ]);
  });

  it("offers approve and refuse only while a patch is waiting", () => {
    render(
      <PatchPanel
        patches={[_patch(1), _patch(2, { state: "rejected" })]}
        {...props}
      />,
    );
    expect(screen.getAllByTestId("patch-approve")).toHaveLength(1);
    expect(screen.getAllByTestId("patch-reject")).toHaveLength(1);
  });

  it("asks for the text when someone wants to look", () => {
    const onLoad = vi.fn();
    render(<PatchPanel patches={[_patch(7)]} texts={{}} onLoad={onLoad} onDecide={() => {}} />);

    fireEvent.click(screen.getByTestId("patch-view"));

    expect(onLoad).toHaveBeenCalledWith(7);
  });

  it("shows the diff once it has arrived", () => {
    render(
      <PatchPanel
        patches={[_patch(7)]}
        texts={{ 7: "-x = 1\n+x = 2" }}
        onLoad={() => {}}
        onDecide={() => {}}
      />,
    );
    expect(screen.getByTestId("patch-diff").textContent).toContain("+x = 2");
  });

  it("shows nothing to expand before the text is fetched", () => {
    render(<PatchPanel patches={[_patch(7)]} {...props} />);
    expect(screen.queryByTestId("patch-diff")).toBeNull();
  });

  it("says why a patch was refused", () => {
    render(
      <PatchPanel
        patches={[_patch(1, {
          state: "rejected",
          verdict_reason: "Makefile is on the execution surface",
        })]}
        {...props}
      />,
    );
    expect(screen.getByTestId("patch-reason").textContent).toContain(
      "execution surface",
    );
  });

  it("reports the decision with the patch it belongs to", () => {
    const onDecide = vi.fn();
    render(
      <PatchPanel patches={[_patch(9)]} texts={{}} onLoad={() => {}} onDecide={onDecide} />,
    );

    fireEvent.click(screen.getByTestId("patch-approve"));

    expect(onDecide).toHaveBeenCalledWith(9, true);
  });
});
