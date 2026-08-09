import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function InlineMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{ p: ({ children: content }) => <span>{content}</span> }}
    >
      {children}
    </ReactMarkdown>
  );
}
