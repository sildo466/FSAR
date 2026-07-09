// SPDX-License-Identifier: Apache-2.0

export type ThinkSegment =
    | { kind: "think"; content: string }
    | { kind: "text"; content: string };

const THINK_RE = /<think\b[^>]*>([\s\S]*?)<\/think>/gi;

/**
 * Split assistant content into alternating plain-text / ＆lt;think＆gt; blocks.
 * Inline / streaming content may contain partial `＆lt;think＆gt;` tags; treat
 * any opening tag without a matching closer as plain text (no partial emits).
 */
export function splitThinkBlocks(content: string): ThinkSegment[] {
    if (!content) return [];
    const segments: ThinkSegment[] = [];
    let last = 0;
    THINK_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = THINK_RE.exec(content)) !== null) {
        if (m.index > last) {
            segments.push({ kind: "text", content: content.slice(last, m.index) });
        }
        segments.push({ kind: "think", content: (m[1] || "").trim() });
        last = m.index + m[0].length;
    }
    if (last < content.length) {
        segments.push({ kind: "text", content: content.slice(last) });
    }
    return segments;
}

/** True iff the content contains at least one closed `＆lt;think＆gt;` block. */
export function hasThinkBlocks(content: string): boolean {
    THINK_RE.lastIndex = 0;
    return THINK_RE.test(content);
}
