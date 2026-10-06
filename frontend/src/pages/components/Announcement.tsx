// SPDX-License-Identifier: MIT
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const HEADING = "font-semibold text-text";

/**
 * Tailwind's preflight strips heading sizes and list markers, so markdown body
 * text renders flat unless every element is styled explicitly here.
 */
const COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className={`${HEADING} mb-2 mt-4 text-[16px] first:mt-0`}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className={`${HEADING} mb-2 mt-4 text-[15px] first:mt-0`}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className={`${HEADING} mb-1.5 mt-3 text-[14px] first:mt-0`}>{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className={`${HEADING} mb-1 mt-3 text-[13px]`}>{children}</h4>
  ),
  h5: ({ children }) => (
    <h5 className={`${HEADING} mb-1 mt-3 text-[13px]`}>{children}</h5>
  ),
  h6: ({ children }) => (
    <h6 className={`${HEADING} mb-1 mt-3 text-[13px]`}>{children}</h6>
  ),
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
  li: ({ children }) => <li className="my-0.5 leading-relaxed">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="underline underline-offset-2 hover:text-text"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-border pl-3 text-text-muted">
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-surface px-1 py-0.5 font-mono text-[11px]">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded bg-surface px-2 py-1.5 font-mono text-[11px]">
      {children}
    </pre>
  ),
  hr: () => <hr className="my-4 border-border" />,
  table: ({ children }) => (
    <table className="my-2 w-full border-collapse text-left text-[12px]">{children}</table>
  ),
  th: ({ children }) => (
    <th className="border border-border px-2 py-1 font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
};

/**
 * Announcement title for the feed row.
 *
 * A filename is a poor heading ("first-announcement.md"), so prefer the
 * document's first heading and fall back to the bare filename without its
 * extension. Fenced code is skipped so a `#` inside a sample is not mistaken
 * for the title.
 */
export function announcementTitle(body: string, filename: string): string {
  let inFence = false;
  for (const line of body.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const match = /^#{1,6}\s+(.+)$/.exec(trimmed);
    if (!match) continue;
    const text = match[1]
      .replace(/\s*#+\s*$/, "")
      .replace(/[*_`]/g, "")
      .trim();
    if (text) return text;
  }
  return filename.replace(/\.md$/i, "");
}

export function AnnouncementBody({ body }: { body: string }) {
  return (
    <div className="text-[13px] leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {body}
      </ReactMarkdown>
    </div>
  );
}
