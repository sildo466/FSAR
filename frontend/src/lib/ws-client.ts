// SPDX-License-Identifier: Apache-2.0

export type ClientMsg =
  | { type: "chat.send"; content: string; mode: "agent" | "companion"; attached_files?: string[] }
  | { type: "chat.cancel" }
  | { type: "chat.rate"; message_id: string; score: 1 | 2 | 3 | 4 | 5; reason?: string }
  | { type: "risk.respond"; call_id: string; response: "y" | "n" | "all" | "server" | "never" }
  | { type: "reflection.set_intensity"; intensity: "off" | "low" | "medium" | "high" }
  | { type: "settings.get" }
  | { type: "settings.patch"; patch: Record<string, unknown> }
  | { type: "memory.search"; query: string }
  | { type: "memory.remember"; body: string }
  | { type: "usage.range"; from: string; to: string }
  | { type: "llm.set_active"; provider_id: string }
  | { type: "mcp.reload"; server_name?: string }
  | { type: "heartbeat" };

export type ServerMsg =
  | { type: "snapshot"; config: Record<string, unknown>; runtime?: Record<string, unknown> }
  | { type: "chat.delta"; message_id: string; content: string }
  | { type: "chat.thinking"; message_id: string }
  | { type: "chat.tool_call"; message_id: string; call_id: string; tool: string; args: unknown; risk: "SAFE" | "LOW" | "MEDIUM" | "HIGH" }
  | { type: "chat.tool_result"; call_id: string; result: unknown; latency_ms: number }
  | { type: "chat.done"; message_id: string; outcome: "success" | "failure" | "timeout"; summary?: string }
  | { type: "chat.risk_request"; call_id: string; tool: string; args_preview: string; reason: string }
  | { type: "reflection.event"; event: { task_id: string; outcome: string; suggested_strategy: string; step_count: number; tools_used: string[]; created_at: string } }
  | { type: "reflection.intensity_changed"; intensity: string; triggers?: Record<string, unknown> }
  | { type: "settings.changed"; patch: Record<string, unknown> }
  | { type: "library.changed"; op: string; name: string }
  | { type: "memory.search_results"; query: string; results: Array<{ session_id: string; snippet: string; score: number }> }
  | { type: "usage.snapshot"; kpis: Record<string, number>; timeline: unknown[]; per_provider: unknown[]; per_tool: unknown[]; cache: Record<string, unknown> }
  | { type: "llm.provider_changed"; provider_id: string; model: string }
  | { type: "mcp.status"; servers: Array<{ name: string; enabled: boolean; running: boolean; tools: number }> }
  | { type: "error"; code: string; message: string; recoverable: boolean }
  | { type: "heartbeat"; ts: number };

export type Listener = (msg: ServerMsg) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners = new Set<Listener>();
  private reconnectAttempts = 0;
  private reconnectTimer: number | null = null;

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
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
      this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(msg: ClientMsg): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
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
