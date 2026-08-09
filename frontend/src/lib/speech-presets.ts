// SPDX-License-Identifier: MIT
import ttsCatalog from "../../../data/presets/tts-providers.json";
import asrCatalog from "../../../data/presets/asr-providers.json";

export interface SpeechPreset {
  id: string;
  label: string;
  family: string;
  default_base_url?: string;
  api_key_required: boolean;
  deferred: boolean;
  voice_placeholder?: string;
  model_placeholder?: string;
  voices?: string[];
  language_placeholder?: string;
}

export const ttsPresets = ttsCatalog as SpeechPreset[];
export const asrPresets = asrCatalog as SpeechPreset[];
