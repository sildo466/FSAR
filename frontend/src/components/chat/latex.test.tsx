// SPDX-License-Identifier: MIT
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

function render(src: string): string {
    return renderToStaticMarkup(
        ReactMarkdown({
            remarkPlugins: [remarkGfm, remarkMath],
            rehypePlugins: [[rehypeKatex, { throwOnError: false }]],
            children: src,
        } as any)
    );
}

describe("markdown + LaTeX + GFM rendering", () => {
    it("renders inline $...$ as KaTeX", () => {
        const html = render("Inline $E=mc^2$ sample.");
        expect(html).toContain('class="katex"');
        expect(html).toContain("<mi>E</mi>");
    });

    it("renders display $$...$$ as KaTeX block", () => {
        const html = render("Display: $$\n\\int_0^1 x^2 \\,dx = \\frac{1}{3}\n$$");
        expect(html).toContain('class="katex-display"');
        expect(html).toContain('class="katex"');
    });

    it("leaves pure markdown alone — no KaTeX injected", () => {
        const html = render("Just *markdown* with `code`, no math.");
        expect(html).not.toContain("katex");
        expect(html).toContain("<em>markdown</em>");
        expect(html).toContain("<code>code</code>");
    });

    it("does not interfere with non-math content (code blocks stay + no KaTeX bleeding)", () => {
        const html = render("```py\nprint(1)\n```");
        expect(html).not.toContain("katex");
        expect(html).toContain("<pre");
        expect(html).toContain('<code class="language-py">');
    });

    it("renders GFM tables", () => {
        const html = render(
            "| col A | col B |\n|-------|-------|\n| 1     | 2     |\n| 3     | 4     |\n"
        );
        expect(html).toContain("<table");
        expect(html).toContain("<th");
        expect(html).toContain("<td");
        expect(html).toContain("col A");
    });

    it("renders GFM strikethrough", () => {
        const html = render("~~old~~ new");
        expect(html).toContain("<del>old</del>");
    });

    it("renders GFM task lists", () => {
        const html = render("- [x] done\n- [ ] todo");
        expect(html).toContain('type="checkbox"');
        expect(html).toMatch(/checked[^>]*>\s*done|s>done/);
    });

    it("tolerates broken LaTeX mid-stream (throwOnError:false)", () => {
        // Streaming chunks may leave LaTeX half-formed — must not throw, must
        // surface the partial text so the user sees something rather than a
        // crash. Verifies rehype-katex was wired with `throwOnError: false`.
        expect(() => render("Partial: $\\frac{1}{")).not.toThrow();
        const html = render("Partial: $\\frac{1}{");
        // KaTeX either renders a best-effort fragment or echoes the source —
        // either way the function returned without throwing.
        expect(html.length).toBeGreaterThan(0);
    });
});
