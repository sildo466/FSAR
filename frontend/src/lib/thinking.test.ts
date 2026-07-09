// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { splitThinkBlocks, hasThinkBlocks } from "./thinking";

describe("splitThinkBlocks", () => {
    it("returns single text segment when no think tags present", () => {
        const out = splitThinkBlocks("hello world");
        expect(out).toEqual([{ kind: "text", content: "hello world" }]);
    });

    it("returns [] for empty input", () => {
        expect(splitThinkBlocks("")).toEqual([]);
    });

    it("extracts a single think block from prose", () => {
        const out = splitThinkBlocks(
            "before <think>step 1・step 2</think> after"
        );
        expect(out).toEqual([
            { kind: "text", content: "before " },
            { kind: "think", content: "step 1・step 2" },
            { kind: "text", content: " after" },
        ]);
    });

    it("preserves multiline think content and trims outer whitespace", () => {
        const out = splitThinkBlocks(
            "<think>\n  line A\n  line B\n</think>"
        );
        const think = out.find((s) => s.kind === "think");
        expect(think).toBeDefined();
        expect(think!.kind === "think" && think!.content).toBe("line A\n  line B");
    });

    it("handles multiple think blocks (text / think / text / think / text)", () => {
        const out = splitThinkBlocks(
            "A<think>one</think>B<think>two</think>C"
        );
        expect(out).toEqual([
            { kind: "text", content: "A" },
            { kind: "think", content: "one" },
            { kind: "text", content: "B" },
            { kind: "think", content: "two" },
            { kind: "text", content: "C" },
        ]);
    });

    it("treats unclosed <think> (no /think in stream) as plain text", () => {
        const mid = "<think>halfway through with no closer";
        const out = splitThinkBlocks(mid);
        // No closed <think>...</think> pair → kept as text verbatim.
        expect(out).toEqual([{ kind: "text", content: mid }]);
    });

    it("handles think-only content", () => {
        const out = splitThinkBlocks("<think>only thought</think>");
        expect(out).toEqual([{ kind: "think", content: "only thought" }]);
    });
});

describe("hasThinkBlocks", () => {
    it("returns false for prose with no think tag", () => {
        expect(hasThinkBlocks("plain answer")).toBe(false);
    });
    it("returns true when at least one closed block is present", () => {
        expect(hasThinkBlocks("a<think>r</think>")).toBe(true);
    });
    it("returns false for unclosed (mid-stream) tag", () => {
        expect(hasThinkBlocks("mid <think> only")).toBe(false);
    });
});
