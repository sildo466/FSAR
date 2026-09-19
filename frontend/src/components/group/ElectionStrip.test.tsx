// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { ElectionStrip } from "./ElectionStrip";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

it("renders nothing when there are no candidates", () => {
  const { container } = render(
    <ElectionStrip candidates={[]} running={false} />
  );
  expect(container).toBeEmptyDOMElement();
});

it("shows eagerness and reason per candidate", () => {
  render(
    <ElectionStrip
      running
      candidates={[
        {
          character_id: 7,
          character_name: "Mira",
          eagerness: 8,
          reason: "wants to speak",
        },
      ]}
    />
  );
  expect(screen.getByText("Mira")).toBeInTheDocument();
  expect(screen.getByText("8/10")).toBeInTheDocument();
  expect(screen.getByText("wants to speak")).toBeInTheDocument();
});

it("labels the region for screen readers", () => {
  render(
    <ElectionStrip
      running={false}
      candidates={[
        {
          character_id: 7,
          character_name: "Mira",
          eagerness: 0,
          reason: "",
        },
      ]}
    />
  );
  expect(screen.getByRole("region")).toHaveAccessibleName("Election results");
});

it("lists every candidate", () => {
  render(
    <ElectionStrip
      running
      candidates={[
        { character_id: 7, character_name: "Mira", eagerness: 9, reason: "a" },
        { character_id: 8, character_name: "Kai", eagerness: 4, reason: "b" },
      ]}
    />
  );
  expect(screen.getByText("Mira")).toBeInTheDocument();
  expect(screen.getByText("Kai")).toBeInTheDocument();
  expect(screen.getByText("4/10")).toBeInTheDocument();
});
