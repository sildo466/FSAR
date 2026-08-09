import { integrationClient, type IntegrationSnapshot } from "./integrationClient";
import { useWS } from "../stores/ws";

export interface ChatModelItem {
  kind: "model" | "integration";
  id?: number;
  provider?: string;
  model?: string;
  label: string;
  est_calls: number;
}

export const chatClient = {
  async snapshot(): Promise<{ chat_models: ChatModelItem[]; selected_chat_model: Record<string, unknown> }> {
    const config = useWS.getState().config ?? {};
    const llm = (config.llm ?? {}) as Record<string, any>;
    const providers = Array.isArray(llm.providers) ? llm.providers : [];
    const integrations: IntegrationSnapshot[] = await integrationClient.list().catch(() => []);
    const models = providers.filter((provider: any) => provider.enabled !== false).map((provider: any) => ({
      kind: "model" as const,
      provider: provider.id,
      model: provider.model,
      label: provider.label || provider.id,
      est_calls: 1,
    }));
    return {
      chat_models: [
        ...models,
        ...integrations.map((integration) => ({
          kind: "integration" as const,
          id: integration.id,
          label: integration.name,
          est_calls: integration.est_calls ?? 2,
        })),
      ],
      selected_chat_model: ((config.chat as any)?.default_model ?? { kind: "model", provider: llm.active, model: llm.providers?.[0]?.model }) as Record<string, unknown>,
    };
  },
};
