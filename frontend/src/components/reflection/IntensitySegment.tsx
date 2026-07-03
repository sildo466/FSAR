// SPDX-License-Identifier: Apache-2.0
const LEVELS = ["off", "low", "medium", "high"] as const;
type Level = (typeof LEVELS)[number];

interface Props {
  value: Level;
  onChange: (v: Level) => void;
}

export function IntensitySegment({ value, onChange }: Props) {
  return (
    <div className="inline-flex border border-border-strong rounded overflow-hidden">
      {LEVELS.map((l) => (
        <button
          key={l}
          onClick={() => onChange(l)}
          className={`px-6 h-9 text-[13px] font-medium uppercase tracking-wider transition-colors duration-200 ${
            l === value ? "bg-text text-surface" : "bg-surface text-text hover:bg-bg"
          }`}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
