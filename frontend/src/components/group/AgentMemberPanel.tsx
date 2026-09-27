// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Ban, KeyRound, Square, UserMinus } from "lucide-react";
import { useGroup } from "../../stores/group";
import type { AgentMemberSummary, RoomSummary } from "../../lib/ws-client";

interface Props {
  room: RoomSummary;
  onClose: () => void;
}

export function AgentMemberPanel({ room, onClose }: Props) {
  const { t } = useTranslation();
  const members = room.agent_members ?? [];
  const details = useGroup((s) => s.agentMembers[room.id]) ?? [];
  const addAgent = useGroup((s) => s.addAgentMember);
  const listAgents = useGroup((s) => s.listAgentMembers);
  const mute = useGroup((s) => s.muteAgentMember);
  const kick = useGroup((s) => s.removeAgentMember);
  const issue = useGroup((s) => s.issueMemberToken);
  const revoke = useGroup((s) => s.revokeMemberToken);
  const stopAll = useGroup((s) => s.stopAllChains);
  const [ref, setRef] = useState("");
  const [displayName, setDisplayName] = useState("");

  useEffect(() => {
    listAgents(room.id);
  }, [listAgents, room.id]);

  const tokensFor = (member: AgentMemberSummary) =>
    details.find((d) => d.ref === member.ref)?.tokens ?? [];

  const submit = () => {
    const trimmed = ref.trim();
    if (!trimmed) return;
    addAgent(room.id, trimmed, displayName.trim() || trimmed);
    setRef("");
    setDisplayName("");
  };

  return (
    <aside className="glass flex h-full w-80 shrink-0 flex-col gap-4 overflow-y-auto rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <span className="font-display text-xs tracking-[0.08em] text-text-muted">
          {t("group.agentMembers")}
        </span>
        <button
          data-testid="close-agent-panel"
          onClick={onClose}
          className="rounded-full p-1 text-text-muted transition hover:text-text"
        >
          ×
        </button>
      </div>

      <p className="text-[11px] text-text-faint">{t("group.agentModeHint")}</p>

      <button
        data-testid="stop-all-chains"
        onClick={stopAll}
        className="flex items-center justify-center gap-1 rounded-xl border border-border px-3 py-2 text-[11px] text-danger transition hover:bg-glass"
      >
        <Square size={11} />
        {t("group.stopAll")}
      </button>

      {members.length === 0 ? (
        <p data-testid="agent-members-empty" className="text-[11px] text-text-faint">
          {t("group.agentMembersEmpty")}
        </p>
      ) : (
        members.map((member) => (
          <div
            key={member.ref}
            data-testid={`agent-member-${member.ref}`}
            className="flex flex-col gap-2 rounded-xl border border-border bg-surface px-3 py-2"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[12px] text-text">
                {member.display_name}
              </span>
              <span className="shrink-0 font-mono text-[10px] text-text-faint">
                {member.ref}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                data-testid={`mute-${member.ref}`}
                onClick={() => mute(room.id, member.ref, member.state !== "muted")}
                className="flex items-center gap-1 rounded-full border border-border px-2 py-1 text-[11px] text-text-muted transition hover:bg-glass hover:text-text"
              >
                <Ban size={11} />
                {member.state === "muted" ? t("group.unmute") : t("group.mute")}
              </button>
              <button
                data-testid={`issue-token-${member.ref}`}
                onClick={() => issue(room.id, member.ref)}
                className="flex items-center gap-1 rounded-full border border-border px-2 py-1 text-[11px] text-text-muted transition hover:bg-glass hover:text-text"
              >
                <KeyRound size={11} />
                {t("group.issueToken")}
              </button>
              <button
                data-testid={`kick-${member.ref}`}
                onClick={() => kick(room.id, member.ref)}
                className="flex items-center gap-1 rounded-full border border-border px-2 py-1 text-[11px] text-text-muted transition hover:bg-glass hover:text-danger"
              >
                <UserMinus size={11} />
                {t("group.kick")}
              </button>
            </div>

            {tokensFor(member).length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-text-faint">
                  {t("group.tokensLabel")}
                </span>
                {tokensFor(member).map((token) => (
                  <div
                    key={token.id}
                    data-testid={`agent-token-${token.id}`}
                    className="flex items-center justify-between gap-2"
                  >
                    <span
                      data-testid={`token-${token.id}`}
                      className={`truncate font-mono text-[10px] ${
                        token.revoked_at ? "text-text-faint line-through" : "text-text-muted"
                      }`}
                    >
                      #{token.id}
                      {token.label ? ` · ${token.label}` : ""}
                      {token.bound_ip ? ` · ${token.bound_ip}` : ""}
                      {token.expires_at
                        ? ` · ${new Date(token.expires_at).toLocaleDateString()}`
                        : ""}
                    </span>
                    {!token.revoked_at && (
                      <button
                        data-testid={`revoke-token-${token.id}`}
                        onClick={() => revoke(room.id, member.ref, token.id)}
                        className="shrink-0 text-[10px] text-text-muted transition hover:text-danger"
                      >
                        {t("group.revokeToken")}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))
      )}

      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <label className="text-[11px] text-text-muted" htmlFor="agent-ref">
          {t("group.agentRef")}
        </label>
        <input
          id="agent-ref"
          data-testid="agent-ref-input"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder="claude@laptop"
          className="rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
        />
        <label className="text-[11px] text-text-muted" htmlFor="agent-name">
          {t("group.agentDisplayName")}
        </label>
        <input
          id="agent-name"
          data-testid="agent-display-name-input"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text outline-none"
        />
        <button
          data-testid="add-agent-submit"
          onClick={submit}
          disabled={!ref.trim()}
          className="rounded-full bg-[var(--button-bg)] px-4 py-2 text-xs text-[var(--button-text)] disabled:opacity-50"
        >
          {t("group.addAgent")}
        </button>
      </div>
    </aside>
  );
}
