// SPDX-License-Identifier: MIT
import { create } from "zustand";

export type WizardStep =
  | "provider" | "embedding" | "character_card" | "user_card" | "tts" | "asr"
  | "submitting" | "completed" | "error";

export type CharacterMode = "use_default" | "pick_existing" | "create_new" | "import_st";
export type EmbedderProvider = "openai" | "lmstudio" | "ollama";

interface ProviderData {
  preset_id: string | null;
  api_key_required?: boolean;
  api_key: string;
  base_url: string;
  model: string;
  input_per_1m: string;
  output_per_1m: string;
  test_result: { ok: boolean; error: string | null; latency_ms: number | null } | null;
}

interface EmbeddingData {
  provider: EmbedderProvider | "";
  api_key: string;
  base_url: string;
  model: string;
  probe_result: { ok: boolean; error: string | null; dim: number | null } | null;
}

interface UserCardData {
  name: string;
  bio: string;
}

interface CharacterCardData {
  mode: CharacterMode;
  picked_card_id: number | null;
  new_card: {
    name: string;
    avatar_file: File | null;
    avatar_path: string | null;
    personality: string;
    system_prompt_override: string;
    tts_voice?: string;
    tts_instructions?: string;
    tts_autoplay_on_card?: boolean;
  };
  st_file: File | null;
}

interface WizardData {
  provider: ProviderData;
  embedding: EmbeddingData;
  user_card: UserCardData;
  character_card: CharacterCardData;
}

interface WizardErrors {
  provider?: string;
  embedding?: string;
  user_card?: string;
  character_card?: string;
  submit?: string;
}

interface WizardState {
  step: WizardStep;
  current_step_index: number;
  data: WizardData;
  errors: WizardErrors;

  setProviderField<K extends keyof ProviderData>(k: K, v: ProviderData[K]): void;
  setEmbeddingField<K extends keyof EmbeddingData>(k: K, v: EmbeddingData[K]): void;
  setUserCardField<K extends keyof UserCardData>(k: K, v: UserCardData[K]): void;
  setCharacterCardField<K extends keyof CharacterCardData>(k: K, v: CharacterCardData[K]): void;
  next(): Promise<boolean>;
  back(): void;
  skip(): void;
  finish(): Promise<void>;
  reset(): void;
}

const STEPS = [0, 1, 2, 3, 4, 5];
const STEP_NAME: Record<number, WizardStep> = {
  0: "provider",
  1: "embedding",
  2: "character_card",
  3: "user_card",
  4: "tts",
  5: "asr",
};

function emptyData(): WizardData {
  return {
    provider: { preset_id: null, api_key: "", base_url: "", model: "", input_per_1m: "", output_per_1m: "", test_result: null },
    embedding: { provider: "", api_key: "", base_url: "", model: "", probe_result: null },
    user_card: { name: "", bio: "" },
    character_card: {
      mode: "use_default",
      picked_card_id: null,
      new_card: { name: "", avatar_file: null, avatar_path: null, personality: "", system_prompt_override: "", tts_voice: "", tts_instructions: "", tts_autoplay_on_card: false },
      st_file: null,
    },
  };
}

export const useWizardState = create<WizardState>((set, get) => ({
  step: "provider",
  current_step_index: 0,
  data: emptyData(),
  errors: {},

  setProviderField: (k, v) => set((s) => ({
    data: { ...s.data, provider: { ...s.data.provider, [k]: v } },
    errors: { ...s.errors, provider: undefined },
  })),
  setEmbeddingField: (k, v) => set((s) => ({
    data: { ...s.data, embedding: { ...s.data.embedding, [k]: v } },
    errors: { ...s.errors, embedding: undefined },
  })),
  setUserCardField: (k, v) => set((s) => ({
    data: { ...s.data, user_card: { ...s.data.user_card, [k]: v } },
    errors: { ...s.errors, user_card: undefined },
  })),
  setCharacterCardField: (k, v) => set((s) => ({
    data: { ...s.data, character_card: { ...s.data.character_card, [k]: v } },
    errors: { ...s.errors, character_card: undefined },
  })),

  next: async () => {
    const s = get();
    const errs: WizardErrors = { ...s.errors };
    if (s.current_step_index === 0) {
      const p = s.data.provider;
      if (!p.preset_id) errs.provider = "select a preset";
      else if (p.api_key_required && !p.api_key.trim()) errs.provider = "enter API key";
      else if (!p.base_url.trim()) errs.provider = "enter base URL";
      else if (!p.model.trim()) errs.provider = "select or type a model";
      if (errs.provider) { set({ errors: errs }); return false; }
      errs.provider = undefined;
    } else if (s.current_step_index === 3) {
      const u = s.data.user_card;
      if (!u.name.trim()) errs.user_card = "enter your name";
      else if (!u.bio.trim()) errs.user_card = "enter a short bio";
      if (errs.user_card) { set({ errors: errs }); return false; }
      errs.user_card = undefined;
    }
    set({ errors: errs });
    const nextIdx = STEPS[Math.min(STEPS.indexOf(s.current_step_index) + 1, 5)];
    set({ current_step_index: nextIdx, step: STEP_NAME[nextIdx] });
    return true;
  },

  back: () => {
    const s = get();
    if (s.current_step_index === 0) return;
    const prevIdx = STEPS[Math.max(STEPS.indexOf(s.current_step_index) - 1, 0)];
    set({ current_step_index: prevIdx, step: STEP_NAME[prevIdx] });
  },

  skip: () => {
    const s = get();
    if (s.current_step_index !== 1 && s.current_step_index !== 2) return;
    const nextIdx = STEPS[Math.min(STEPS.indexOf(s.current_step_index) + 1, 5)];
    set({ current_step_index: nextIdx, step: STEP_NAME[nextIdx] });
  },

  finish: async () => {
    set({ step: "submitting" });
    set({ step: "completed" });
  },

  reset: () => set({ step: "provider", current_step_index: 0, data: emptyData(), errors: {} }),
}));
