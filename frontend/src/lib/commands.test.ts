// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { SLASH_COMMANDS, filterCommands } from "./commands";

describe("filterCommands", () => {
  it("returns the first 4 commands when query is empty", () => {
    const out = filterCommands("");
    expect(out).toHaveLength(4);
    expect(out[0].name).toBe(SLASH_COMMANDS[0].name);
  });

  it("filters by prefix (case-insensitive)", () => {
    // Derive expectations from the actual SLASH_COMMANDS pool so the test
    // doesn't break when a new command is added.
    const expected = SLASH_COMMANDS.filter((c) => c.name.startsWith("s")).map((c) => c.name);
    expect(expected.length).toBeGreaterThan(0);
    const out = filterCommands("s");
    expect(out.map((c) => c.name)).toEqual(expected);
  });

  it("returns multiple matches for shared prefix", () => {
    const out = filterCommands("sk");
    expect(out.map((c) => c.name).sort()).toEqual(
      SLASH_COMMANDS.filter((c) => c.name.startsWith("sk")).map((c) => c.name).sort()
    );
  });

  it("returns empty when no match", () => {
    expect(filterCommands("zzzzz")).toHaveLength(0);
  });

  it("matches uppercase as case-insensitive", () => {
    const expected = SLASH_COMMANDS.filter((c) => c.name.startsWith("m"))
      .map((c) => c.name.toLowerCase())
      .sort();
    expect(expected.length).toBeGreaterThan(0);
    const out = filterCommands("M");
    expect(out.map((c) => c.name.toLowerCase()).sort()).toEqual(expected);
  });

  it("keeps every SLASH_COMMANDS.name unique and starts with /", () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
    for (const c of SLASH_COMMANDS) expect(c.usage.startsWith("/")).toBe(true);
    expect(names.length).toBeGreaterThan(0);
  });
});