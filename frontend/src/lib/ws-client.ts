// SPDX-License-Identifier: Apache-2.0

export type ClientMsg =
  | { type: "chat.send"; conversation_id?: string; character_id?: number; content: string; mode: "agent" | "companion"; attached_files?: string[] }
  | { type: "chat.cancel" }
  | { type: "chat.rate"; message_id: string; score: 1 | 2 | 3 | 4 | 5; reason?: string }
  | { type: "conversation.list"; limit?: number }
  | { type: "conversation.create" }
  | { type: "conversation.switch"; conversation_id: string }
  | { type: "conversation.history"; conversation_id: string; limit?: number }
  | { type: "conversation.rename"; conversation_id: string; title: string }
  | { type: "conversation.pin"; conversation_id: string; pinned: boolean }
  | { type: "conversation.delete"; conversation_id: string }
  | { type: "risk.respond"; call_id: string; response: "y" | "n" | "all" | "server" | "never" }
  | { type: "reflection.set_intensity"; intensity: "off" | "low" | "medium" | "high" }
  | { type: "settings.get" }
  | { type: "settings.patch"; patch: Record<string, unknown> }
  | { type: "memory.search"; query: string }
  | { type: "memory.remember"; body: string }
  | { type: "memory.sessions"; limit?: number }
  | { type: "memory.transcript"; session_id: string }
  | { type: "memory.facts" }
  | { type: "library.list" }
  | { type: "library.create"; name: string; category: string; description?: string; body: string; created_by?: string }
  | { type: "library.update"; name: string; category?: string; description?: string; body?: string }
  | { type: "library.delete"; name: string }
  | { type: "library.archive"; name: string }
  | { type: "card.list"; kind: "character" | "user" }
  | { type: "card.get"; kind: "character" | "user"; id: number }
  | { type: "card.upsert"; kind: "character" | "user"; card: Record<string, unknown> }
  | { type: "card.delete"; kind: "character" | "user"; id: number }
  | { type: "card.set_default"; kind: "character" | "user"; id: number }
  | { type: "card.import_v2"; json_text: string }
  | { type: "card.export"; id: number }
  | { type: "card.set_session_character"; session_id: string; character_id: number }
  | { type: "card.list_session_character"; session_id: string }
  | { type: "card.validate_formula"; character_id: number; formula: string }
  | { type: "card.get_emotion"; character_id: number }
  | { type: "card.set_emotion_schema"; character_id: number; schema: unknown[]; formulas: Record<string, string> }
  | { type: "insights.get" }
  | { type: "usage.range"; from: string; to: string }
  | { type: "llm.set_active"; provider_id: string }
  | { type: "permissions.patch"; patch: Record<string, unknown> }
  | { type: "provider.list_presets" }
  | { type: "provider.create_builtin"; preset_id: string; label: string; api_key: string; base_url: string; model: string; pricing?: { input_per_1m: number; output_per_1m: number } }
  | { type: "provider.test_connection"; preset_id: string; base_url: string; api_key: string; model?: string }
  | { type: "provider.fetch_models"; preset_id: string; base_url: string; api_key: string }
  | { type: "onboarding.get_state" }
  | { type: "onboarding.complete_step"; step: string; data?: Record<string, unknown> }
  | { type: "onboarding.complete" }
  | { type: "onboarding.skip" }
  | { type: "embedding.upsert"; provider: "openai" | "lmstudio" | "ollama"; base_url: string; model: string; api_key?: string; timeout?: number }
  | { type: "embedding.probe"; provider?: "openai" | "lmstudio" | "ollama"; base_url?: string; model?: string; api_key?: string }
  | { type: "onboarding.reset" }
  | { type: "style.patch"; patch: Record<string, unknown> }
  | { type: "style.set_theme"; theme: "light" | "dark" | "system" }
  | { type: "mcp.list" }
  | { type: "mcp.reload"; server_name?: string }
  | { type: "mcp.toggle"; server_name: string; enabled: boolean }
  | { type: "tools.list" }
  | { type: "heartbeat" };

export interface SessionMeta {
  id: string;
  title: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface StoredMessage {
  id: number;
  session_id: string;
  role: string;
  content: string;
  summary: string;
  tags: string;
  timestamp: string;
  character_id?: number;
  character_name?: string;
}

export interface OnboardingStatePayload {
  required: boolean;
  completed: boolean;
  completed_steps: string[];
  current_step: string | null;
}

export type ServerMsg =
  | { type: "snapshot"; config: Record<string, unknown>; runtime?: Record<string, unknown>; onboarding?: OnboardingStatePayload }
  | { type: "onboarding.state"; required: boolean; completed: boolean; completed_steps: string[]; current_step: string | null }
  | { type: "provider.presets"; presets: Array<Record<string, unknown>> }
  | { type: "provider.created"; provider: { id: string; preset_id: string; model: string; family: string; [k: string]: unknown }; providers: Array<Record<string, unknown>>; active: string }
  | { type: "provider.test_result"; ok: boolean; error: string | null; latency_ms: number | null }
  | { type: "provider.models"; ok: boolean; models: string[]; error: string | null }
  | { type: "onboarding.step_completed"; step: string }
  | { type: "onboarding.completed"; redirect: string }
  | { type: "onboarding.error"; step: string; code: string; message: string }
  | { type: "chat.delta"; message_id: string; content: string; character_id?: number; character_name?: string }
  | { type: "chat.thinking"; message_id: string; conversation_id?: string; character_id?: number; character_name?: string }
  | { type: "chat.tool_call"; message_id: string; call_id: string; tool: string; args: unknown; risk: "SAFE" | "LOW" | "MEDIUM" | "HIGH" }
  | { type: "chat.tool_result"; call_id: string; result: unknown; latency_ms: number }
  | { type: "chat.done"; message_id: string; outcome: "success" | "failure" | "timeout"; summary?: string; character_id?: number; character_name?: string; emotion_state?: Record<string, number> }
  | { type: "chat.rate.ack"; message_id: string; status: "ok" | "no_message" | "error"; db_id?: number; error?: string }
  | { type: "conversation.list"; sessions: SessionMeta[] }
  | { type: "conversation.created"; session: SessionMeta }
  | { type: "conversation.switched"; conversation_id: string; session: SessionMeta | null }
  | { type: "conversation.history"; conversation_id: string; messages: StoredMessage[] }
  | { type: "conversation.title_updated"; conversation_id: string; title: string }
  | { type: "conversation.updated"; session: SessionMeta }
  | { type: "conversation.deleted"; conversation_id: string }
  | { type: "chat.risk_request"; call_id: string; tool: string; args_preview: string; reason: string }
  | { type: "reflection.event"; event: { task_id: string; outcome: string; suggested_strategy: string; step_count: number; tools_used: string[]; created_at: string } }
  | { type: "reflection.intensity_changed"; intensity: string; triggers?: Record<string, unknown> }
  | { type: "settings.changed"; patch: Record<string, unknown> }
  | { type: "library.changed"; op: string; name: string }
  | { type: "memory.search_results"; query: string; results: Array<{ session_id: string; snippet: string; score: number }> }
  | { type: "memory.sessions_result"; sessions: Array<{ session_id: string; count: number; first_ts: string; last_ts: string }> }
  | { type: "memory.transcript_result"; session_id: string; messages: Array<{ role: string; content: string; timestamp: string }> }
  | { type: "memory.facts_result"; facts: Array<{ id: number; source: string; title: string; body: string; created_at: string }> }
  | { type: "library.list_result"; experiences: Array<Record<string, unknown>> }
  | { type: "insights.snapshot"; kpis: Record<string, number>; tool_stats: Array<Record<string, unknown>>; active_strategies_markdown: string; recent_decisions: Array<Record<string, unknown>> }
  | { type: "usage.snapshot"; kpis: Record<string, number>; timeline: unknown[]; per_provider: unknown[]; per_tool: unknown[]; cache: Record<string, number> }
  | { type: "llm.provider_changed"; provider_id: string; model: string }
  | { type: "experience.created"; experience: { id: number; name: string; category: string; description: string; body: string; trigger_patterns: string[]; pitfalls: string[]; use_count: number; state: string; pinned: boolean; created_by: string; created_at: string; updated_at: string } }
  | { type: "tools.list_result"; tools: Array<{ name: string; description: string; risk_level: string }> }
  | { type: "mcp.status"; servers: Array<{ name: string; command: string; args: string[]; enabled: boolean; risk: string; running: boolean }> }
  | { type: "style.changed"; style: Record<string, unknown>; by?: string }
  | { type: "card.list_result"; kind: string; cards: Array<Record<string, unknown>> }
  | { type: "card.got"; kind: string; card: Record<string, unknown> }
  | { type: "card.upserted"; kind: string; id: number }
  | { type: "card.deleted"; kind: string; id: number; ok: boolean }
  | { type: "card.default_changed"; kind: string; id: number }
  | { type: "card.imported"; card_id: number; warnings: string[] }
  | { type: "card.exported"; card: Record<string, unknown> }
  | { type: "card.session_character_set"; session_id: string; character_id: number }
  | { type: "card.session_character"; session_id: string; character_id: number | null }
  | { type: "card.formula_validated"; valid: boolean; error?: string | null }
  | { type: "card.emotion"; character_id: number; state: Record<string, number>; schema: unknown[]; formulas: Record<string, string> }
  | { type: "card.emotion_schema_set"; character_id: number }
  | { type: "card.user_card_renamed"; user_card_id: number; name: string }
  | { type: "card.emotion_state_updated"; character_id: number; state: Record<string, number>; source: string }
  | { type: "card.error"; code: string; message?: string }
  | { type: "error"; code: string; message: string; recoverable: boolean }
  | { type: "heartbeat"; ts: number };

export type Listener = (msg: ServerMsg) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners = new Set<Listener>();
  private reconnectAttempts = 0;
  private reconnectTimer: number | null = null;
  private pending: ClientMsg[] = [];
  private ready = false;
  private onReadyCallbacks: Array<() => void> = [];

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.ready = true;
      const queue = this.pending;
      this.pending = [];
      for (const m of queue) this.ws?.send(JSON.stringify(m));
      const cbs = this.onReadyCallbacks;
      this.onReadyCallbacks = [];
      cbs.forEach((cb) => cb());
    };
    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as ServerMsg;
        this.listeners.forEach((l) => l(msg));
      } catch (err) {
        console.error("ws parse error", err);
      }
    };
    this.ws.onclose = () => {
      this.ready = false;
      this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(msg: ClientMsg): void {
    if (this.ready && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    } else {
      this.pending.push(msg);
    }
  }

  whenReady(cb: () => void): void {
    if (this.ready) cb();
    else this.onReadyCallbacks.push(cb);
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return;
    const delay = Math.min(30000, 1000 * Math.pow(2, this.reconnectAttempts));
    this.reconnectAttempts++;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }
}
