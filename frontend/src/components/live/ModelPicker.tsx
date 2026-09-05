// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchModelList } from "./modelsApi";
import { getModelKind } from "./modelKind";

interface ModelPickerProps {
  value: string | null;
  onSelect: (name: string | null) => void;
}

export function ModelPicker({ value, onSelect }: ModelPickerProps) {
  const { t } = useTranslation();
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

  const vrm = models.filter((m) => getModelKind(m) === "vrm");
  const live2d = models.filter((m) => getModelKind(m) === "live2d");

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="live-model" className="text-sm text-text-muted">
        {t("live.lobby.model")}
      </label>
      <select
        id="live-model"
        data-testid="live-model-select"
        className="rounded-lg glass border border-border px-2 py-1 text-sm"
        value={value ?? ""}
        onChange={(e) => onSelect(e.target.value || null)}
      >
        <option value="">{t("live.lobby.none")}</option>
        {vrm.length > 0 && (
          <optgroup label={t("live.lobby.vrmGroup")}>
            {vrm.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </optgroup>
        )}
        {live2d.length > 0 && (
          <optgroup label={t("live.lobby.live2dGroup")}>
            {live2d.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </div>
  );
}
