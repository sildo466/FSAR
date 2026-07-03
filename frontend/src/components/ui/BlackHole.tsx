// SPDX-License-Identifier: Apache-2.0
interface Props {
  size?: number;
}

export function BlackHole({ size = 96 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      aria-hidden="true"
    >
      <circle cx="50" cy="50" r="44" />
      <circle cx="50" cy="50" r="32" />
      <circle cx="50" cy="50" r="20" />
      <circle cx="50" cy="50" r="8" fill="currentColor" stroke="none" />
    </svg>
  );
}
