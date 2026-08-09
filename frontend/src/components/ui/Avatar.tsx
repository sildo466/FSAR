// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";

interface Props {
  name: string;
  avatarPath?: string | null;
  cardId?: number;
  size?: number;
  className?: string;
}

export function Avatar({ name, avatarPath, cardId, size = 36, className }: Props) {
  const [imageFailed, setImageFailed] = useState(false);
  const initial = name?.trim()?.[0]?.toUpperCase() ?? "?";
  const showImage = !!avatarPath && cardId != null && !imageFailed;

  useEffect(() => setImageFailed(false), [avatarPath, cardId]);

  if (showImage) {
    return (
      <img
        src={`/api/card/${cardId}/avatar`}
        alt={name}
        className={`shrink-0 rounded-full object-cover ring-1 ring-border shadow-[0_0_18px_var(--glow-faint)] transition hover:scale-105 hover:shadow-[0_0_22px_var(--glow-soft)] ${className ?? ""}`}
        style={{ width: size, height: size }}
        onError={() => setImageFailed(true)}
      />
    );
  }

  return (
    <div
      className={`flex shrink-0 select-none items-center justify-center rounded-full bg-text font-semibold text-bg ring-1 ring-border shadow-[0_0_18px_var(--glow-faint)] transition hover:scale-105 hover:shadow-[0_0_22px_var(--glow-soft)] ${className ?? ""}`}
      style={{
        width: size,
        height: size,
        fontSize: Math.max(10, Math.floor(size * 0.42)),
      }}
      aria-label={name}
      title={name}
    >
      {initial}
    </div>
  );
}
