// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { applyToolEvent } from "./toolEvents";

describe("applyToolEvent", () => {
  it("appends a call, pretty-printing object args", () => {
    const steps = applyToolEvent(undefined, {
      kind: "call", callId: "c1", tool: "read_file", args: { path: "a.txt" },
    });
    expect(steps).toEqual([
      { callId: "c1", tool: "read_file", argsPreview: '{\n  "path": "a.txt"\n}' },
    ]);
  });

  it("keeps string args as they came", () => {
    const steps = applyToolEvent(undefined, {
      kind: "call", callId: "c1", tool: "t", args: "raw",
    });
    expect(steps[0].argsPreview).toBe("raw");
  });

  it("fills in the result of a call it knows", () => {
    const called = applyToolEvent(undefined, {
      kind: "call", callId: "c1", tool: "read_file", args: {},
    });
    const done = applyToolEvent(called, {
      kind: "result", callId: "c1", result: "ok", latencyMs: 12,
    });
    expect(done[0].result).toBe("ok");
    expect(done[0].latencyMs).toBe(12);
  });

  it("does not append a result as if it were a call", () => {
    const steps = applyToolEvent(undefined, {
      kind: "result", callId: "nope", result: "ok", latencyMs: 1,
    });
    expect(steps).toEqual([]);
  });

  it("leaves other calls alone", () => {
    const both = [
      { callId: "c1", tool: "a", argsPreview: "" },
      { callId: "c2", tool: "b", argsPreview: "" },
    ];
    const done = applyToolEvent(both, {
      kind: "result", callId: "c2", result: "r", latencyMs: 2,
    });
    expect(done[0].result).toBeUndefined();
    expect(done[1].result).toBe("r");
  });
});
