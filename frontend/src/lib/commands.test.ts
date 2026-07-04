// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { SLASH_COMMANDS, filterCommands } from "./commands";

describe("filterCommands", () => {
  it("returns the first 4 commands when query is empty", () => {
    const out = filterCommands("");
    expect(out).toHaveLength(4);
    expect(out[0].name).toBe(SLASH_COMMANDS[0].name);
  });

  it("filters by prefix", () => {
    const out = filterCommands("s");
    expect(out.map((c) => c.name)).toEqual(["stats", "skills"]);
  });

  it("returns multiple matches for shared prefix", () => {
    const out = filterCommands("sk");
    expect(out.map((c) => c.name)).toEqual(["skills"]);
  });

  it("returns empty when no match", () => {
    const out = filterCommands("zzzzz");
    expect(out).toHaveLength(0);
  });

  it("matches case-insensitively", () => {
    const out = filterCommands("M");
    expect(out.length).toBeGreaterThan(0);
    expect(out[0].name).toMatch(/^m/);
  });

  it("contains all 8 commands in the full pool", () => {
    expect(SLASH_COMMANDS).toHaveLength(8);
  });
});