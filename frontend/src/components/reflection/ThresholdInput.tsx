// SPDX-License-Identifier: Apache-2.0
interface Props {
  label: string;
  value: number;
  unit: string;
  onChange: (v: number) => void;
}

export function ThresholdInput({ label, value, unit, onChange }: Props) {
  return (
    <label className="inline-flex items-center gap-2 mr-4">
      <span className="text-[13px] text-text-muted">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value || "0", 10))}
        className="w-16 h-7 px-2 bg-surface border border-border rounded text-[13px] font-mono"
      />
      <span className="text-[12px] text-text-muted">{unit}</span>
    </label>
  );
}
