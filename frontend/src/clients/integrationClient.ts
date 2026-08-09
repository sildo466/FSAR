import { send, subscribe } from "./ws";

export type SubKind = "model" | "integration";

export interface ModelSpec {
  id?: number;
  provider: string;
  base_url: string;
  api_key?: string;
  protocol?: string;
  model: string;
  persona_prompt: string;
  specialty?: string;
  temperature?: number;
  max_tokens?: number | null;
}

export interface IntegrationSub {
  id?: number;
  position?: number;
  display_name: string;
  kind: SubKind;
  model_id?: number | null;
  child_integration_id?: number | null;
  model?: ModelSpec | null;
  child?: IntegrationSnapshot | null;
}

export interface IntegrationDraft {
  id?: number;
  name: string;
  description?: string;
  main_model_id: number;
  main_model?: ModelSpec;
  rounds: number;
  max_depth: number;
  max_subs_picked: number;
  is_default?: number;
  subs: IntegrationSub[];
}

export interface IntegrationSnapshot extends IntegrationDraft {
  id: number;
  created_at?: string;
  updated_at?: string;
  est_calls?: number;
}

export type RunEvent = Record<string, any> & { type: string; run_id?: string };
export interface RunFinalResponse {
  type?: string;
  run_id: string;
  status: string;
  total_calls: number;
  total_cost_usd?: number | null;
  total_ms?: number;
  final_reply?: string;
  errors?: string[];
}

async function request<T extends Record<string, any>>(message: Record<string, any>): Promise<T> {
  return (await send(message)) as T;
}

export const integrationClient = {
  async list(): Promise<IntegrationSnapshot[]> {
    const result = await request<{ items?: IntegrationSnapshot[] }>({ type: "integration.list" });
    return result.items ?? [];
  },

  async save(draft: IntegrationDraft): Promise<{ id: number; integration?: IntegrationSnapshot }> {
    const result = await request<{ id?: number; integration?: IntegrationSnapshot; code?: string; path?: number[] }>({
      type: "integration.save", payload: draft,
    });
    if (result.code) throw result;
    if (typeof result.id !== "number") throw new Error("integration save returned no id");
    return { id: result.id, integration: result.integration };
  },

  async delete(id: number): Promise<void> {
    const result = await request<{ code?: string }>({ type: "integration.delete", payload: { id } });
    if (result.code) throw result;
  },

  async run(id: number, message: string, mode: "replay" | "estimate", onEvent: (event: RunEvent) => void): Promise<RunFinalResponse> {
    const events: RunEvent[] = [];
    const off = subscribe((event) => {
      if (!event.type.startsWith("integration.")) return;
      const item = event as RunEvent;
      events.push(item);
      onEvent(item);
    });
    try {
      const result = (await send(
        { type: "integration.run", payload: { id, message, mode } },
        (event) => (event as any).type === "integration.run_done",
      )) as RunFinalResponse;
      return result;
    } finally {
      off();
    }
  },

  async estimateCalls(id: number): Promise<{ total_calls: number }> {
    const result = await this.run(id, "", "estimate", () => undefined);
    return { total_calls: result.total_calls ?? (result as any).total_calls_only ?? 0 };
  },
};
