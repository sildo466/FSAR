// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { RefreshCw, Power, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { useWS } from "../../stores/ws";

interface Server {
  name: string;
  command: string;
  args: string[];
  enabled: boolean;
  risk: string;
  running: boolean;
}

export function MCPTab() {
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);
  const [servers, setServers] = useState<Server[]>([]);
  const [reloadState, setReloadState] = useState<"idle" | "loading">("idle");

  useEffect(() => {
    send({ type: "mcp.list" });
  }, [send]);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "mcp.status") {
        setServers(msg.servers as unknown as Server[]);
        setReloadState("idle");
      }
    });
  }, [client]);

  function toggle(name: string, enabled: boolean) {
    send({ type: "mcp.toggle", server_name: name, enabled });
  }

  function reload() {
    setReloadState("loading");
    send({ type: "mcp.reload" });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-sm font-semibold">MCP servers</h2>
          <p className="text-[11px] text-text-muted">
            External tool servers loaded as subprocesses. Edit <code className="font-mono">config/fsar.yaml</code>{" "}
            under <code className="font-mono">mcp.servers</code>, then Reload.
          </p>
        </div>
        <button
          onClick={reload}
          disabled={reloadState === "loading"}
          className="flex items-center gap-1 h-7 px-2 border border-border rounded text-[12px] hover:bg-surface disabled:opacity-50"
        >
          {reloadState === "loading" ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} strokeWidth={1.5} />}
          Reload all
        </button>
      </div>

      {servers.length === 0 ? (
        <div className="border border-border rounded p-6 text-[12px] text-text-muted text-center">
          No MCP servers configured. Add entries under <code className="font-mono">mcp.servers</code> in fsar.yaml.
        </div>
      ) : (
        <div className="border border-border rounded overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-bg text-text-muted font-mono text-[10px] uppercase tracking-[0.1em]">
              <tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Command</th>
                <th className="text-left px-3 py-2">Risk</th>
                <th className="text-center px-3 py-2">State</th>
                <th className="text-right px-3 py-2">Enabled</th>
              </tr>
            </thead>
            <tbody>
              {servers.map((s) => (
                <tr key={s.name} className="border-t border-border">
                  <td className="px-3 py-2 font-mono">{s.name}</td>
                  <td className="px-3 py-2 font-mono text-text-muted">
                    {s.command} {(s.args || []).join(" ")}
                  </td>
                  <td className="px-3 py-2 font-mono">{s.risk}</td>
                  <td className="px-3 py-2 text-center">
                    {s.running ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-success font-mono">
                        <CheckCircle2 size={11} strokeWidth={1.5} /> running
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] text-text-muted font-mono">
                        <AlertTriangle size={11} strokeWidth={1.5} /> stopped
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => toggle(s.name, !s.enabled)}
                      className={`inline-flex items-center gap-1 h-6 px-2 rounded border text-[11px] font-mono ${
                        s.enabled
                          ? "border-border bg-text text-bg"
                          : "border-border text-text-muted"
                      }`}
                    >
                      <Power size={10} strokeWidth={1.5} />
                      {s.enabled ? "ON" : "OFF"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
