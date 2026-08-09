// SPDX-License-Identifier: MIT
interface Props {
  width?: number;
}

export function BlackHole({ width = 64 }: Props) {
  const height = width;
  return (
    <div className="breath-glow relative rounded-full" style={{ width, height }} aria-hidden="true">
      <div className="absolute inset-[12%] rounded-full bg-text shadow-[0_0_28px_var(--glow-soft)]" />
      <div className="absolute inset-[30%] rounded-full bg-bg" />
    </div>
  );
}
