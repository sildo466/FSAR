// SPDX-License-Identifier: MIT
import { useEffect } from "react";
import { useWS } from "../stores/ws";
import { useLocale } from "../stores/locale";

export function useLocaleApplication(): void {
  const config = useWS((s) => s.config);
  const hydrate = useLocale((s) => s.hydrateFromConfig);

  useEffect(() => {
    const style = (config?.style ?? {}) as { locale?: string };
    void hydrate(style.locale);
  }, [config, hydrate]);
}