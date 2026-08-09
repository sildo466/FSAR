// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { ArrowLeft, FolderLock, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useWorkspace } from "../stores/workspace";
import { useWS } from "../stores/ws";
import { useSessions } from "../stores/sessions";

export function SettingsWorkspace() {
  const { t } = useTranslation();
  const send = useWS((state) => state.send);
  const config = useWS((state) => state.config);
  const workspaces = useWorkspace((state) => state.workspaces);
  const defaultId = useWorkspace((state) => state.defaultId);
  const bindings = useWorkspace((state) => state.bindings);
  const sessions = useSessions((state) => state.sessions);
  const [name, setName] = useState("");
  const [root, setRoot] = useState("");
  const [template, setTemplate] = useState<"blank" | "user_home" | "full_computer">("blank");
  const security = (config?.security ?? {}) as { power_user_mode?: boolean };

  useEffect(() => {
    send({ type: "workspace.list" });
    send({ type: "conversation.list", limit: 50 });
  }, [send]);
  useEffect(() => {
    sessions.forEach((session) => send({ type: "workspace.get_binding", conversation_id: session.id }));
  }, [sessions, send]);

  function createWorkspace() {
    const trimmed = name.trim();
    if (!trimmed || (template === "blank" && !root.trim())) return;
    send({ type: "workspace.create", name: trimmed, root_path: root.trim() || undefined, template });
    setName("");
    setRoot("");
  }

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-8 px-8 py-10">
      <header className="flex items-end justify-between gap-6">
        <div><Link to="/settings" className="mb-4 inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider text-text-muted hover:text-text"><ArrowLeft size={12} /> {t("settings.title")}</Link><h1 className="font-display text-4xl italic tracking-[-0.02em]">{t("settingsWorkspace.title")}</h1><p className="mt-2 max-w-[620px] text-text-muted">{t("settingsWorkspace.subtitle")}</p></div>
        <div className="hidden rounded-full border border-success/30 bg-success/10 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-success sm:flex"><ShieldCheck size={13} className="mr-2" /> {t("settingsWorkspace.hardlineActive")}</div>
      </header>
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <section className="glass-strong overflow-hidden rounded-[28px] shadow-[0_18px_54px_var(--glow-faint)]">
          <div className="border-b border-border px-6 py-5"><h2 className="font-display text-lg font-semibold">{t("settingsWorkspace.available")}</h2><p className="text-[12px] text-text-muted">{t("settingsWorkspace.availableHint")}</p></div>
          <div className="divide-y divide-border">
            {workspaces.map((workspace) => (
              <article key={workspace.id} className="group flex items-start gap-4 px-6 py-5">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl border border-border bg-bg/50"><FolderLock size={17} /></div>
                <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h3 className="text-[14px] font-semibold">{workspace.name}</h3>{workspace.id === defaultId && <span className="rounded-full bg-success/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-success">{t("settingsWorkspace.default")}</span>}</div><p className="mt-1 truncate font-mono text-[11px] text-text-muted">{workspace.root_path}</p><p className="mt-2 font-mono text-[10px] text-text-faint">{t("settingsWorkspace.allowLabel", { paths: workspace.allowed_paths.join(", ") })}</p></div>
                <div className="flex shrink-0 gap-1">{workspace.id !== defaultId && <button onClick={() => send({ type: "workspace.set_default", id: workspace.id })} className="rounded-full border border-border px-3 py-1.5 text-[10px] hover:bg-surface">{t("settingsWorkspace.setDefault")}</button>}{workspace.id !== defaultId && <button onClick={() => send({ type: "workspace.delete", id: workspace.id })} title={t("common.delete")} className="grid h-7 w-7 place-items-center rounded-full text-text-muted hover:bg-danger/10 hover:text-danger"><Trash2 size={13} /></button>}</div>
              </article>
            ))}
          </div>
        </section>
        <aside className="glass flex h-fit flex-col gap-4 rounded-[28px] p-6">
          <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">{t("settingsWorkspace.newPerimeter")}</p><h2 className="mt-1 font-display text-xl italic">{t("settingsWorkspace.createTitle")}</h2></div>
          {security.power_user_mode && <select value={template} onChange={(event) => setTemplate(event.target.value as typeof template)} className="h-9 bg-bg px-3 text-[12px]"><option value="blank">{t("settingsWorkspace.templateCustom")}</option><option value="user_home">{t("settingsWorkspace.templateUserHome")}</option><option value="full_computer">{t("settingsWorkspace.templateFull")}</option></select>}
          <label className="space-y-1"><span className="font-mono text-[10px] uppercase tracking-wider text-text-muted">{t("settingsWorkspace.nameLabel")}</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("settingsWorkspace.namePlaceholder")} className="h-9 w-full bg-bg px-3 text-[12px]" /></label>
          {template === "blank" && <label className="space-y-1"><span className="font-mono text-[10px] uppercase tracking-wider text-text-muted">{t("settingsWorkspace.rootPathLabel")}</span><input value={root} onChange={(event) => setRoot(event.target.value)} placeholder={t("settingsWorkspace.rootPathPlaceholder")} className="h-9 w-full bg-bg px-3 font-mono text-[11px]" /></label>}
          <button onClick={createWorkspace} className="mt-2 flex h-9 items-center justify-center gap-2 rounded-full bg-text text-[12px] font-medium text-bg"><Plus size={14} /> {t("settingsWorkspace.createButton")}</button>
          {!security.power_user_mode && <p className="text-[11px] leading-relaxed text-text-muted">{t("settingsWorkspace.powerUserHint")}</p>}
        </aside>
      </div>
      <section className="glass-strong overflow-hidden rounded-[28px] shadow-[0_18px_54px_var(--glow-faint)]">
        <div className="border-b border-border px-6 py-5"><h2 className="font-display text-lg font-semibold">{t("settingsWorkspace.bindings")}</h2><p className="text-[12px] text-text-muted">{t("settingsWorkspace.bindingsHint")}</p></div>
        {sessions.length === 0 ? <p className="px-6 py-5 text-[12px] text-text-muted">{t("settingsWorkspace.noConversations")}</p> : <div className="divide-y divide-border">{sessions.map((session) => (
          <div key={session.id} className="grid items-center gap-3 px-6 py-4 sm:grid-cols-[1fr_280px]">
            <div className="min-w-0"><p className="truncate text-[13px] font-medium">{session.title || t("settingsWorkspace.untitled")}</p><p className="font-mono text-[9px] text-text-muted">{session.id}</p></div>
            <select value={bindings[session.id]?.id ?? defaultId ?? ""} onChange={(event) => send({ type: "workspace.switch_binding", conversation_id: session.id, workspace_id: Number(event.target.value) })} className="h-9 bg-bg px-3 text-[12px]">
              {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name} — {workspace.root_path}</option>)}
            </select>
          </div>
        ))}</div>}
      </section>
    </div>
  );
}
