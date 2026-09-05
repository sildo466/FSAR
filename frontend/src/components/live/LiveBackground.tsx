// SPDX-License-Identifier: MIT
import type { CSSProperties } from "react";

const STAR_COUNT = 24;

function buildStars(): CSSProperties[] {
  return Array.from({ length: STAR_COUNT }, (_, i) => {
    const left = (i * 37 + 11) % 100;
    const top = (i * 53 + 7) % 100;
    return {
      left: `${left}%`,
      top: `${top}%`,
      animationDelay: `${(i % 6) * 0.8}s`,
      animationDuration: `${6 + (i % 4)}s`,
    };
  });
}

export function LiveBackground({ scene }: { scene: string }) {
  const isImage = scene.startsWith("image:");
  const stars = buildStars();
  return (
    <div
      data-testid="live-bg"
      className={`absolute inset-0 ${isImage ? "" : "deepspace"}`}
      style={
        isImage
          ? {
              backgroundImage: `url("${scene.slice("image:".length)}")`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : {
              background:
                "radial-gradient(ellipse at 30% 20%, #1b2340 0%, #0a0d1a 55%, #05060d 100%)",
            }
      }
    >
      {!isImage &&
        stars.map((s, i) => (
          <span key={i} className="star-mote" style={s} aria-hidden="true" />
        ))}
    </div>
  );
}
