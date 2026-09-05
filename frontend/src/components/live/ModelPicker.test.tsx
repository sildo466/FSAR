// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModelPicker } from "./ModelPicker";
import { initI18n } from "../../lib/i18nSetup";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(() => cleanup());

vi.mock("./modelsApi", () => ({
  fetchModelList: async () => ["girl.vrm", "hiyori/hiyori.model3.json", "moc.vrm"],
}));

describe("ModelPicker", () => {
  it("groups VRM and Live2D models under separate optgroups", async () => {
    render(<ModelPicker value={null} onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole("option").length).toBe(4)); // None + 2 vrm + 1 l2d
    const groups = screen.getAllByRole("group");
    expect(groups).toHaveLength(2);
    const labels = groups.map((g) => g.getAttribute("label"));
    expect(labels).toContain("VRM");
    expect(labels).toContain("Live2D");
  });

  it("keeps the relative path as the option value", async () => {
    const onSelect = vi.fn();
    render(<ModelPicker value={null} onSelect={onSelect} />);
    await waitFor(() =>
      expect(screen.getByText("hiyori/hiyori.model3.json")).toBeTruthy()
    );
    fireEvent.change(screen.getByTestId("live-model-select"), {
      target: { value: "hiyori/hiyori.model3.json" },
    });
    expect(onSelect).toHaveBeenCalledWith("hiyori/hiyori.model3.json");
  });
});
