// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it } from "vitest";
import { useWizardState } from "./onboarding";

describe("useWizardState", () => {
  beforeEach(() => {
    useWizardState.getState().reset();
  });


  it("starts at provider step with empty data", () => {
    const state = useWizardState.getState();
    expect(state.step).toBe("provider");
    expect(state.current_step_index).toBe(0);
    expect(state.data.provider.preset_id).toBe(null);
  });

  it("setProviderField updates provider data", () => {
    useWizardState.getState().setProviderField("preset_id", "openai");
    useWizardState.getState().setProviderField("api_key", "sk-test");
    const s = useWizardState.getState();
    expect(s.data.provider.preset_id).toBe("openai");
    expect(s.data.provider.api_key).toBe("sk-test");
  });

  it("setUserCardField updates user card data", () => {
    useWizardState.getState().setUserCardField("name", "Alice");
    useWizardState.getState().setUserCardField("bio", "I work on AI");
    const s = useWizardState.getState();
    expect(s.data.user_card.name).toBe("Alice");
    expect(s.data.user_card.bio).toBe("I work on AI");
  });

  it("setCharacterCardField updates character card data", () => {
    useWizardState.getState().setCharacterCardField("mode", "create_new");
    useWizardState.getState().setCharacterCardField("picked_card_id", 5);
    const s = useWizardState.getState();
    expect(s.data.character_card.mode).toBe("create_new");
    expect(s.data.character_card.picked_card_id).toBe(5);
  });

  it("next() advances step index when valid", async () => {
    useWizardState.setState({
      data: {
        provider: { preset_id: "openai", api_key: "sk-test", base_url: "https://x", model: "gpt-4o-mini", input_per_1m: "", output_per_1m: "", test_result: null },
        embedding: { provider: "", api_key: "", base_url: "", model: "", probe_result: null },
        user_card: { name: "A", bio: "B" },
        character_card: {
          mode: "use_default", picked_card_id: null,
          new_card: { name: "", avatar_file: null, avatar_path: null, personality: "", system_prompt_override: "" },
          st_file: null,
        },
      },
    });
    await useWizardState.getState().next();
    expect(useWizardState.getState().current_step_index).toBe(1);
    expect(useWizardState.getState().step).toBe("embedding");
  });

  it("allows a provider preset that does not require an API key", async () => {
    useWizardState.getState().setProviderField("preset_id", "lmstudio");
    useWizardState.getState().setProviderField("api_key_required", false);
    useWizardState.getState().setProviderField("base_url", "http://localhost:1234/v1");
    useWizardState.getState().setProviderField("model", "local-model");

    const advanced = await useWizardState.getState().next();

    expect(advanced).toBe(true);
    expect(useWizardState.getState().step).toBe("embedding");
  });

  it("requires an API key only when the selected preset requires one", async () => {
    useWizardState.getState().setProviderField("preset_id", "openai");
    useWizardState.getState().setProviderField("api_key_required", true);
    useWizardState.getState().setProviderField("base_url", "https://api.openai.com/v1");
    useWizardState.getState().setProviderField("model", "gpt-4o-mini");

    const advanced = await useWizardState.getState().next();

    expect(advanced).toBe(false);
    expect(useWizardState.getState().step).toBe("provider");
    expect(useWizardState.getState().errors.provider).toBe("enter API key");
  });

  it("next() blocks when provider step has empty fields", async () => {
    useWizardState.setState({
      data: {
        provider: { preset_id: null, api_key: "", base_url: "", model: "", input_per_1m: "", output_per_1m: "", test_result: null },
        embedding: { provider: "", api_key: "", base_url: "", model: "", probe_result: null },
        user_card: { name: "", bio: "" },
        character_card: {
          mode: "use_default", picked_card_id: null,
          new_card: { name: "", avatar_file: null, avatar_path: null, personality: "", system_prompt_override: "" },
          st_file: null,
        },
      },
    });
    await useWizardState.getState().next();
    expect(useWizardState.getState().current_step_index).toBe(0);
    expect(useWizardState.getState().errors.provider).toBeDefined();
  });

  it("back() decrements step index without backend call", () => {
    useWizardState.setState({ current_step_index: 2, step: "user_card" });
    useWizardState.getState().back();
    expect(useWizardState.getState().current_step_index).toBe(1);
    expect(useWizardState.getState().step).toBe("embedding");
  });

  it("skip() advances the optional embedding step", () => {
    useWizardState.setState({ current_step_index: 1, step: "embedding" });
    useWizardState.getState().skip();
    expect(useWizardState.getState().current_step_index).toBe(2);
    expect(useWizardState.getState().step).toBe("character_card");
  });

  it("finish() sets step to submitting then completed", async () => {
    useWizardState.setState({ current_step_index: 3, step: "character_card" });
    await useWizardState.getState().finish();
    expect(["submitting", "completed"]).toContain(useWizardState.getState().step);
  });
});
