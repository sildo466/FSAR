// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useWS } from "../stores/ws";

interface SearchResult {
  session_id: string;
  snippet: string;
  score: number;
}

interface SessionRow {
  session_id: string;
  count: number;
  first_ts: string;
  last_ts: string;
}

interface FactRow {
  id: number;
  title: string;
  body: string;
  created_at: string;
}

interface TranscriptMsg {
  role: string;
  content: string;
  timestamp: string;
}

export function Memory() {
  const config = useWS((s) => s.config);
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [facts, setFacts] = useState<FactRow[]>([]);
  const [transcript, setTranscript] = useState<TranscriptMsg[] | null>(null);
  const [rememberOpen, setRememberOpen] = useState(false);
  const [rememberText, setRememberText] = useState("");
  const [modalSession, setModalSession] = useState<string | null>(null);

  useEffect(() => {
    if (!client) return;
    const off = client.on((msg) => {
      if (msg.type === "memory.search_results") {
        if (msg.query === query) {
          setResults(msg.results);
        }
      } else if (msg.type === "memory.sessions_result") {
        setSessions(msg.sessions);
      } else if (msg.type === "memory.facts_result") {
        setFacts(msg.facts);
      } else if (msg.type === "memory.transcript_result") {
        setTranscript(msg.messages);
      }
    });
    send({ type: "memory.sessions" });
    send({ type: "memory.facts" });
    return off;
  }, [client, query, send]);

  const openSession = (sid: string) => {
    setTranscript(null);
    setModalSession(sid);
    send({ type: "memory.transcript", session_id: sid });
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    send({ type: "memory.search", query: query.trim() });
  };

  const handleRememberSave = () => {
    const body = rememberText.trim();
    if (!body) return;
    send({ type: "memory.remember", body });
    setRememberText("");
    setRememberOpen(false);
  };

  const profile = (config?.user ?? config?.profile ?? {}) as Record<string, unknown>;
  const profileEntries = Object.entries(profile);

  const searching = results !== null;

  return (
    <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">Memory</h1>
        <p className="text-text-muted">Everything FSAR remembers about you</p>
      </header>

      <form onSubmit={handleSearch} className="flex items-center gap-3">
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!e.target.value.trim()) setResults(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setQuery("");
              setResults(null);
            }
          }}
          placeholder="🔍 Search memory (semantic + keyword)"
          className="flex-1 h-9 px-3 bg-surface border border-border rounded text-[13px]"
        />
        <button
          type="submit"
          className="px-3 h-9 rounded border border-border-strong text-[13px]"
        >
          ↵
        </button>
      </form>

      {searching ? (
        <section>
          <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
            Search results · {results!.length}
          </div>
          {results!.length === 0 ? (
            <p className="text-text-muted text-sm">No matches for &quot;{query}&quot;.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {results!.map((r, i) => (
                <li key={i} className="py-3 flex flex-col gap-1">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-text-muted">
                      score {(r.score * 100).toFixed(0)}%
                    </span>
                    {r.session_id && (
                      <button
                        onClick={() => openSession(r.session_id)}
                        className="font-mono text-xs text-text underline hover:opacity-80"
                      >
                        {r.session_id.slice(0, 16)}
                      </button>
                    )}
                  </div>
                  <p className="text-sm">{r.snippet}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <>
          <section>
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
              Profile
            </div>
            {profileEntries.length === 0 ? (
              <p className="text-text-muted text-sm">No profile yet.</p>
            ) : (
              <div className="border border-border rounded p-4 text-[13px]">
                {profileEntries.map(([k, v]) => (
                  <span key={k} className="mr-3">
                    <span className="text-text-muted">{k}:</span> {String(v)}
                  </span>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
              Sessions · {sessions.length}
            </div>
            {sessions.length === 0 ? (
              <p className="text-text-muted text-sm">No sessions yet.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {sessions.map((s) => (
                  <li key={s.session_id} className="py-2 flex items-center gap-3">
                    <button
                      onClick={() => openSession(s.session_id)}
                      className="font-mono text-xs text-text underline hover:opacity-80"
                    >
                      {s.session_id.slice(0, 16)}
                    </button>
                    <span className="text-text-muted text-xs">{s.count} msgs</span>
                    <span className="text-text-muted text-xs ml-auto font-mono">
                      {String(s.last_ts).slice(0, 16)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="flex items-center justify-between mb-3">
              <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
                Facts
              </div>
              <button
                onClick={() => setRememberOpen((v) => !v)}
                className="px-3 h-7 rounded border border-border-strong text-[12px]"
              >
                + Remember
              </button>
            </div>
            {rememberOpen && (
              <div className="border border-border rounded p-3 mb-3 flex flex-col gap-2">
                <textarea
                  value={rememberText}
                  onChange={(e) => setRememberText(e.target.value)}
                  rows={3}
                  placeholder="A fact worth remembering…"
                  className="w-full px-2 py-1 bg-bg border border-border rounded text-[13px] resize-none"
                />
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => {
                      setRememberOpen(false);
                      setRememberText("");
                    }}
                    className="px-3 h-7 rounded border border-border text-[12px]"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleRememberSave}
                    className="px-3 h-7 rounded border border-border-strong bg-text text-surface text-[12px]"
                  >
                    Save
                  </button>
                </div>
              </div>
            )}
            {facts.length === 0 ? (
              <p className="text-text-muted text-sm">No facts yet.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {facts.map((f) => (
                  <li key={f.id} className="py-2">
                    <div className="text-[13px] font-medium">{f.title}</div>
                    <div className="text-text-muted text-xs">{f.body.slice(0, 160)}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      {modalSession && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={() => setModalSession(null)}
        >
          <dialog
            open
            className="w-[80vw] max-w-[720px] max-h-[80vh] overflow-auto bg-surface border border-border rounded p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-lg font-semibold">Session {modalSession.slice(0, 16)}</h2>
              <button
                onClick={() => setModalSession(null)}
                className="px-2 h-7 rounded border border-border text-[12px]"
              >
                Close
              </button>
            </div>
            {transcript === null ? (
              <p className="text-text-muted text-sm">Loading transcript…</p>
            ) : transcript.length === 0 ? (
              <p className="text-text-muted text-sm">Empty session.</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {transcript.map((m, i) => (
                  <li key={i} className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                      <span className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
                        {m.role}
                      </span>
                      <span className="font-mono text-[11px] text-text-muted">
                        {m.timestamp.slice(0, 16)}
                      </span>
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{m.content}</p>
                  </li>
                ))}
              </ul>
            )}
          </dialog>
        </div>
      )}
    </div>
  );
}