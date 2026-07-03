// SPDX-License-Identifier: Apache-2.0
interface Props {
  width?: number;
}

export function BlackHole({ width = 64 }: Props) {
  const height = Math.round(width * (270 / 80));
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 80 270"
      fill="#0a0a0a"
      aria-hidden="true"
    >
      <path d="M 40,255 C 44,215 75,95 75,55 C 75,2 5,2 5,55 C 5,95 36,215 40,255 Z" />
    </svg>
  );
}
