// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { fetchModelList } from "./modelsApi";

interface ModelPickerProps {
  value: string | null;
  onSelect: (name: string | null) => void;
}

export function ModelPicker({ value, onSelect }: ModelPickerProps) {
  const [models, setModels] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    void fetchModelList().then((list) => {
      if (alive) setModels(list);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="live-model" className="text-sm text-text-muted">
        Model
      </label>
      <select
        id="live-model"
        className="rounded-lg glass border border-border px-2 py-1 text-sm"
        value={value ?? ""}
        onChange={(e) => onSelect(e.target.value || null)}
      >
        <option value="">None (geometric)</option>
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  );
}
