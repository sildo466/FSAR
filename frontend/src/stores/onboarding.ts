// SPDX-License-Identifier: Apache-2.0
import { create } from "zustand";

export type WizardStep =
  | "provider" | "user_card" | "character_card"
  | "submitting" | "completed" | "error";

export type CharacterMode = "use_default" | "pick_existing" | "create_new" | "import_st";

interface ProviderData {
  preset_id: string | null;
  api_key: string;
  base_url: string;
  model: string;
  test_result: { ok: boolean; error: string | null; latency_ms: number | null } | null;
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
  };
  st_file: File | null;
}

interface WizardData {
  provider: ProviderData;
  user_card: UserCardData;
  character_card: CharacterCardData;
}

interface WizardErrors {
  provider?: string;
  user_card?: string;
  character_card?: string;
  submit?: string;
}

interface WizardState {
  step: WizardStep;
  current_step_index: 0 | 1 | 2;
  data: WizardData;
  errors: WizardErrors;

  setProviderField<K extends keyof ProviderData>(k: K, v: ProviderData[K]): void;
  setUserCardField<K extends keyof UserCardData>(k: K, v: UserCardData[K]): void;
  setCharacterCardField<K extends keyof CharacterCardData>(k: K, v: CharacterCardData[K]): void;
  next(): Promise<void>;
  back(): void;
  skip(): void;
  finish(): Promise<void>;
  reset(): void;
}

const STEPS: Array<0 | 1 | 2> = [0, 1, 2];

function emptyData(): WizardData {
  return {
    provider: { preset_id: null, api_key: "", base_url: "", model: "", test_result: null },
    user_card: { name: "", bio: "" },
    character_card: {
      mode: "use_default",
      picked_card_id: null,
      new_card: { name: "", avatar_file: null, avatar_path: null, personality: "", system_prompt_override: "" },
      st_file: null,
    },
  };
}

export const useWizardState = create<WizardState>((set, get) => ({
  step: "provider",
  current_step_index: 0,
  data: emptyData(),
  errors: {},

  setProviderField: (k, v) => set((s) => ({ data: { ...s.data, provider: { ...s.data.provider, [k]: v } } })),
  setUserCardField: (k, v) => set((s) => ({ data: { ...s.data, user_card: { ...s.data.user_card, [k]: v } } })),
  setCharacterCardField: (k, v) => set((s) => ({ data: { ...s.data, character_card: { ...s.data.character_card, [k]: v } } })),

  next: async () => {
    const s = get();
    const errs: WizardErrors = { ...s.errors };
    if (s.current_step_index === 0) {
      const p = s.data.provider;
      if (!p.preset_id) errs.provider = "select a preset";
      else if (!p.api_key.trim()) errs.provider = "enter API key";
      else if (!p.base_url.trim()) errs.provider = "enter base URL";
      else if (!p.model.trim()) errs.provider = "select or type a model";
      if (errs.provider) { set({ errors: errs }); return; }
      errs.provider = undefined;
    } else if (s.current_step_index === 1) {
      const u = s.data.user_card;
      if (!u.name.trim()) errs.user_card = "enter your name";
      else if (!u.bio.trim()) errs.user_card = "enter a short bio";
      if (errs.user_card) { set({ errors: errs }); return; }
      errs.user_card = undefined;
    }
    set({ errors: errs });
    const next = STEPS[Math.min(STEPS.indexOf(s.current_step_index) + 1, 2)];
    set({ current_step_index: next, step: next === 0 ? "provider" : next === 1 ? "user_card" : "character_card" });
  },

  back: () => {
    const s = get();
    if (s.current_step_index === 0) return;
    const prev = STEPS[Math.max(STEPS.indexOf(s.current_step_index) - 1, 0)];
    set({ current_step_index: prev, step: prev === 0 ? "provider" : prev === 1 ? "user_card" : "character_card" });
  },

  skip: () => {
    const s = get();
    if (s.current_step_index !== 2) return;
    set({ step: "submitting" });
  },

  finish: async () => {
    set({ step: "submitting" });
    set({ step: "completed" });
  },

  reset: () => set({ step: "provider", current_step_index: 0, data: emptyData(), errors: {} }),
}));
