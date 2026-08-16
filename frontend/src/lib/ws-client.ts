// SPDX-License-Identifier: MIT

export type ClientMsg =
  | { type: "chat.send"; conversation_id?: string; character_id?: number; content: string; mode: "agent" | "companion"; attached_files?: string[]; selected_chat_model?: Record<string, unknown>; workspace_id?: number }
  | { type: "chat.cancel"; conversation_id?: string }
  | { type: "chat.regenerate"; conversation_id?: string; mode: "agent" | "companion"; selected_chat_model?: Record<string, unknown> }
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
  | { type: "style.set_locale"; locale: string }
  | { type: "tts.synthesize"; request_id: string; text: string; message_id?: string; voice_override?: string; instructions_override?: string; bypass_cache?: boolean }
  | { type: "tts.voices"; request_id: string; provider_id: string }
  | { type: "asr.transcribe"; request_id: string; audio: string; mime_type: string; language?: string }
  | { type: "asr.model_list"; request_id: string }
  | { type: "asr.model_download"; request_id: string; size: string }
  | { type: "asr.model_delete"; request_id: string; size: string }
  | { type: "memory.search"; query: string }
  | { type: "memory.remember"; body: string }
  | { type: "memory.sessions"; limit?: number }
  | { type: "memory.transcript"; session_id: string }
  | { type: "memory.facts" }
  | { type: "memory.profile" }
  | { type: "reflection.list"; limit?: number }
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
  | { type: "integration.list" }
  | { type: "integration.save"; payload: Record<string, unknown> }
  | { type: "integration.delete"; payload: { id: number } }
  | { type: "integration.run"; payload: { id: number; message: string; mode: "replay" | "estimate" } }
  | { type: "integration.run_sub_replies"; payload: { run_id: string } }
  | { type: "permissions.patch"; patch: Record<string, unknown> }
  | { type: "provider.list_presets" }
  | { type: "provider.create_builtin"; preset_id: string; label: string; api_key: string; base_url: string; model: string; pricing?: { input_per_1m: number; output_per_1m: number }; format?: string }
  | { type: "provider.test_connection"; preset_id: string; base_url: string; api_key: string; model?: string }
  | { type: "provider.fetch_models"; preset_id: string; base_url: string; api_key: string }
  | { type: "onboarding.get_state" }
  | { type: "onboarding.complete_step"; step: string; data?: Record<string, unknown> }
  | { type: "onboarding.complete" }
  | { type: "onboarding.skip_step"; step: "tts" | "asr" }
  | { type: "onboarding.skip" }
  | { type: "embedding.upsert"; provider: "openai" | "lmstudio" | "ollama"; base_url: string; model: string; api_key?: string; timeout?: number }
  | { type: "embedding.probe"; provider?: "openai" | "lmstudio" | "ollama"; base_url?: string; model?: string; api_key?: string }
  | { type: "onboarding.reset" }
  | { type: "style.patch"; patch: Record<string, unknown> }
  | { type: "style.set_theme"; theme: "light" | "dark" | "system" }
  | { type: "skin.list" }
  | { type: "skin.set_active"; skin_id: string }
  | { type: "mcp.list" }
  | { type: "mcp.reload"; server_name?: string }
  | { type: "mcp.toggle"; server_name: string; enabled: boolean }
  | { type: "tools.list" }
  | { type: "workspace.list" }
  | { type: "workspace.get"; id: number }
  | { type: "workspace.create"; name: string; root_path?: string; allowed_paths?: string[]; blocked_patterns?: string[]; set_default?: boolean; template?: "blank" | "user_home" | "full_computer" }
  | { type: "workspace.update"; id: number; name?: string; root_path?: string; allowed_paths?: string[]; blocked_patterns?: string[] }
  | { type: "workspace.delete"; id: number }
  | { type: "workspace.set_default"; id: number }
  | { type: "workspace.bind" | "workspace.switch_binding"; conversation_id: string; workspace_id: number }
  | { type: "workspace.get_binding"; conversation_id: string }
  | { type: "hardline.list_classes" | "hardline.restore_all" }
  | { type: "hardline.set_disabled"; classes: string[] }
  | { type: "sensitive.list" }
  | { type: "sensitive.add_custom" | "sensitive.remove_custom"; pattern: string }
  | { type: "sensitive.report_missing"; path: string; context?: string }
  | { type: "sandbox_audit.list"; since?: string; conversation_id?: string; limit?: number }
  | { type: "tool.sandbox.escape_decision"; request_id: string; decision: "deny" | "allow_once" | "allow_session" | "allow_always" }
  | { type: "heartbeat" };

export interface WorkspaceInfo {
  id: number;
  name: string;
  root_path: string;
  allowed_paths: string[];
  blocked_patterns: string[];
  default_for_new: boolean;
  created_at: string;
  updated_at: string;
}

export interface HardlineClassInfo {
  id: string;
  label: string;
  enabled: boolean;
  pattern_count: number;
}

export interface SensitiveClassInfo {
  id: string;
  label: string;
  pattern_count: number;
}

export interface SandboxAuditEvent {
  id: number;
  created_at: string;
  tool: string;
  operation?: string;
  target_path?: string;
  command?: string;
  verdict: string;
  reason: string;
}

export interface SandboxEscapeRequest {
  request_id: string;
  tool: string;
  operation: string;
  target_path: string;
  reason: string;
  risk_level: "CRITICAL";
  context: { workspace_id: number; workspace_root: string; matched_rule: string; is_sensitive: boolean };
  options: Array<"deny" | "allow_once" | "allow_session" | "allow_always">;
}

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
  | { type: "snapshot"; config: Record<string, unknown>; runtime?: Record<string, unknown>; chat_models?: Array<Record<string, unknown>>; selected_chat_model?: Record<string, unknown>; onboarding?: OnboardingStatePayload; workspace?: { current_binding: { conversation_id: string; workspace: WorkspaceInfo } | null; default_workspace_id: number | null; all_workspaces: WorkspaceInfo[] }; security?: { hardline_disabled_classes: string[]; power_user_mode: boolean; hardline_classes: HardlineClassInfo[] }; sensitive?: { classes: SensitiveClassInfo[]; custom: string[] } }
  | { type: "integration.list_result"; items: Array<Record<string, unknown>>; models?: Array<Record<string, unknown>> }
  | { type: "integration.saved"; id: number; integration?: Record<string, unknown> }
  | { type: "integration.deleted"; id: number }
  | { type: "integration.error"; code: string; message?: string; path?: number[] }
  | { type: "integration.run_started"; run_id: string; integration_id: number; sub_count: number }
  | { type: "integration.routing_done"; run_id: string; selected: string[]; reasoning: string }
  | { type: "integration.sub_started"; run_id: string; sub_id: string }
  | { type: "integration.sub_done"; run_id: string; sub_id: string; ms: number; ok: boolean; error?: string }
  | { type: "integration.debate_round_done"; run_id: string; round: number; all_consensus: boolean }
  | { type: "integration.synthesis_delta"; run_id: string; content: string }
  | { type: "integration.run_done"; run_id: string; status: string; total_calls: number; total_calls_only?: number; total_cost_usd?: number | null; total_ms?: number; final_reply?: string }
  | { type: "integration.run_sub_replies_result"; run_id: string; rounds: Array<Record<string, unknown>>; route?: Record<string, unknown>; final_reply?: string }
  | { type: "chat.default_model_fallback"; selected_chat_model: Record<string, unknown> }
  | { type: "onboarding.state"; required: boolean; completed: boolean; completed_steps: string[]; current_step: string | null }
  | { type: "provider.presets"; presets: Array<Record<string, unknown>> }
  | { type: "provider.created"; provider: { id: string; preset_id: string; model: string; family: string; [k: string]: unknown }; providers: Array<Record<string, unknown>>; active: string }
  | { type: "provider.test_result"; ok: boolean; error: string | null; latency_ms: number | null }
  | { type: "provider.models"; ok: boolean; models: string[]; error: string | null }
  | { type: "onboarding.step_completed"; step: string }
  | { type: "onboarding.step_skipped"; step: string }
  | { type: "onboarding.completed"; redirect: string }
  | { type: "onboarding.error"; step: string; code: string; message: string }
  | { type: "chat.delta"; message_id: string; conversation_id?: string; content: string; character_id?: number; character_name?: string }
  | { type: "chat.thinking"; message_id: string; conversation_id?: string; character_id?: number; character_name?: string }
  | { type: "chat.tool_call"; message_id: string; conversation_id?: string; call_id: string; tool: string; args: unknown; risk: "SAFE" | "LOW" | "MEDIUM" | "HIGH"; agent_id?: string }
  | { type: "chat.tool_result"; call_id: string; conversation_id?: string; result: unknown; latency_ms: number; agent_id?: string }
  | { type: "chat.done"; message_id: string; conversation_id?: string; outcome: "success" | "failure" | "timeout"; summary?: string; character_id?: number; character_name?: string; emotion_state?: Record<string, number> }
  | { type: "tts.audio"; request_id: string; mime: string; audio: string }
  | { type: "tts.voices_result"; request_id: string; voices: string[] }
  | { type: "tts.error"; request_id: string; code: string; message: string; http_status?: number }
  | { type: "tts.synthesize_queued"; message_id: string; text_preview: string }
  | { type: "asr.text"; request_id: string; text: string; language: string }
  | { type: "asr.error"; request_id: string; code: string; message: string; http_status?: number }
  | { type: "asr.model_list_result"; request_id: string; downloaded: string[]; available: string[]; sizes: Record<string, number> }
  | { type: "asr.model_download_started"; request_id: string; size: string; total_bytes: number; endpoint?: string; endpoint_source?: "override" | "mirror" | "official" }
  | { type: "asr.model_download_progress"; request_id: string; size: string; received_bytes: number; percent: number }
  | { type: "asr.model_download_done"; request_id: string; size: string; path: string }
  | { type: "asr.model_download_error"; request_id: string; size: string; code: string; message: string }
  | { type: "asr.model_deleted"; request_id: string; size: string; ok: boolean }
  | { type: "agent.run.started"; task_id: string; message_id: string; tier: string }
  | { type: "agent.run.finished"; task_id: string; outcome: "success" | "failure" }
  | { type: "agent.status"; task_id: string; agent_id: string; parent_id: string | null; depth: number; kind: "main" | "subagent"; label: string; status: string; detail: string }
  | { type: "agent.plan.updated"; task_id: string; agent_id: string; items: Array<{ id: string; content: string; status: string }> }
  | { type: "agent.context.compacted"; task_id: string; agent_id: string; tokens_before: number; tokens_after: number }
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
  | { type: "reflection.list_result"; events: Array<{ task_id: string; outcome: string; suggested_strategy: string; step_count: number; tools_used: string[]; created_at: string }> }
  | { type: "reflection.intensity_changed"; intensity: string; triggers?: Record<string, unknown> }
  | { type: "settings.changed"; patch: Record<string, unknown> }
  | { type: "library.changed"; op: string; name: string }
  | { type: "memory.search_results"; query: string; results: Array<{ session_id: string; snippet: string; score: number }> }
  | { type: "memory.sessions_result"; sessions: Array<{ session_id: string; count: number; first_ts: string; last_ts: string }> }
  | { type: "memory.transcript_result"; session_id: string; messages: Array<{ role: string; content: string; timestamp: string }> }
  | { type: "memory.facts_result"; facts: Array<{ id: number; source: string; title: string; body: string; created_at: string }> }
  | { type: "memory.profile_result"; profile: Record<string, string> }
  | { type: "library.list_result"; experiences: Array<Record<string, unknown>> }
  | { type: "insights.snapshot"; kpis: Record<string, number>; tool_stats: Array<Record<string, unknown>>; active_strategies_markdown: string; recent_decisions: Array<Record<string, unknown>> }
  | { type: "usage.snapshot"; kpis: Record<string, number>; timeline: unknown[]; per_provider: unknown[]; per_tool: unknown[]; cache: Record<string, number> }
  | { type: "llm.provider_changed"; provider_id: string; model: string }
  | { type: "experience.created"; experience: { id: number; name: string; category: string; description: string; body: string; trigger_patterns: string[]; pitfalls: string[]; use_count: number; state: string; pinned: boolean; created_by: string; created_at: string; updated_at: string } }
  | { type: "tools.list_result"; tools: Array<{ name: string; description: string; risk_level: string }> }
  | { type: "workspace.list_result"; workspaces: WorkspaceInfo[] }
  | { type: "workspace.got"; workspace: WorkspaceInfo | null }
  | { type: "workspace.created" | "workspace.updated"; workspace: WorkspaceInfo }
  | { type: "workspace.deleted"; id: number; ok: boolean }
  | { type: "workspace.default_changed"; id: number }
  | { type: "workspace.bound" | "workspace.binding_changed"; conversation_id: string; workspace_id: number; workspace?: WorkspaceInfo | null }
  | { type: "hardline.classes_result"; classes: HardlineClassInfo[] }
  | { type: "sensitive.list_result"; classes: SensitiveClassInfo[]; custom: string[] }
  | { type: "sensitive.custom_added" | "sensitive.custom_removed"; pattern: string }
  | { type: "sensitive.reported"; path: string }
  | { type: "sandbox_audit.list_result"; events: SandboxAuditEvent[] }
  | ({ type: "tool.sandbox.request_escape" } & SandboxEscapeRequest)
  | { type: "tool.sandbox.escape_ack"; request_id: string; ok: boolean }
  | { type: "mcp.status"; servers: Array<{ name: string; command: string; args: string[]; enabled: boolean; risk: string; running: boolean }> }
  | { type: "style.changed"; style: Record<string, unknown>; by?: string }
  | { type: "skin.list"; skins: Array<{ id: string; name: string; base: "light" | "dark"; palette: Record<string, string> }> }
  | { type: "skin.changed"; skin_id: string }
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
  private token: string;
  private refreshToken?: () => Promise<string>;
  private listeners = new Set<Listener>();
  private reconnectAttempts = 0;
  private reconnectTimer: number | null = null;
  private pending: ClientMsg[] = [];
  private ready = false;
  private onReadyCallbacks: Array<() => void> = [];

  constructor(url: string, token: string, refreshToken?: () => Promise<string>) {
    this.url = url;
    this.token = token;
    this.refreshToken = refreshToken;
  }

  connect(): void {
    this.ws = new WebSocket(this.url, ["fsar-v1", this.token]);
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
    this.ws.onclose = (event) => {
      this.ready = false;
      this.scheduleReconnect(event.code === 1008);
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

  private scheduleReconnect(refreshToken: boolean): void {
    if (this.reconnectTimer !== null) return;
    const delay = Math.min(30000, 1000 * Math.pow(2, this.reconnectAttempts));
    this.reconnectAttempts++;
    this.reconnectTimer = window.setTimeout(async () => {
      this.reconnectTimer = null;
      if (refreshToken && this.refreshToken) {
        try {
          this.token = await this.refreshToken();
        } catch {
          this.scheduleReconnect(true);
          return;
        }
      }
      this.connect();
    }, delay);
  }
}
