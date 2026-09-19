// SPDX-License-Identifier: MIT
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Paperclip } from "lucide-react";
import { MicButton } from "./MicButton";

export interface ComposerAttachment {
  path: string;
  name: string;
}

const MAX_INPUT_LINES = 4;
const INPUT_LINE_HEIGHT = 22;

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
  busy: boolean;
  attachments: ComposerAttachment[];
  onPickFiles: (files: FileList | null) => void;
  onRemoveAttachment: (index: number) => void;
  /** Runs before Enter-to-send. Call preventDefault to consume the key. */
  onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  uploadError?: string;
  uploading?: boolean;
  placeholder: string;
}

export function ChatComposer({
  value,
  onChange,
  onSend,
  onCancel,
  busy,
  attachments,
  onPickFiles,
  onRemoveAttachment,
  onKeyDown,
  uploadError,
  uploading,
  placeholder,
}: Props) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(
      el.scrollHeight,
      INPUT_LINE_HEIGHT * MAX_INPUT_LINES
    )}px`;
  }, [value]);

  return (
    <div>
      {(attachments.length > 0 || uploadError) && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {attachments.map((a, i) => (
            <span
              key={a.path}
              className="flex items-center gap-1.5 rounded-full border border-[var(--chip-border)] px-3 py-1 text-[11px] text-text-muted"
            >
              📎 {a.name}
              <button
                onClick={() => onRemoveAttachment(i)}
                className="hover:text-text"
              >
                ✕
              </button>
            </span>
          ))}
          {uploadError && (
            <span className="text-[11px] text-danger">{uploadError}</span>
          )}
        </div>
      )}
      <div className="glass-strong glow-focus flex items-end gap-2 rounded-[26px] px-3 py-2 shadow-[0_12px_48px_var(--glow-faint)]">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            onPickFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          title={t("chat.attach")}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-text-muted transition hover:bg-glass hover:text-text disabled:opacity-50"
        >
          <Paperclip size={15} strokeWidth={1.5} />
        </button>
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            onKeyDown?.(e);
            if (e.defaultPrevented) return;
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={placeholder}
          className="max-h-[88px] min-w-0 flex-1 resize-none overflow-y-auto bg-transparent px-2 py-1 text-sm leading-[22px] text-text outline-none placeholder:text-text-muted"
        />
        <MicButton
          onTranscript={(text) =>
            onChange(`${value}${value.trim() ? " " : ""}${text}`)
          }
        />
        {busy ? (
          <button
            onClick={onCancel}
            className="rounded-full px-4 py-2 text-xs text-text-muted transition hover:bg-glass hover:text-text"
          >
            {t("chat.stop")}
          </button>
        ) : (
          <button
            onClick={onSend}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--button-bg)] text-[var(--button-text)] button-tex shadow-[0_0_20px_var(--glow-soft)] transition hover:scale-105"
          >
            ↵
          </button>
        )}
      </div>
    </div>
  );
}
