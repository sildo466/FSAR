// SPDX-License-Identifier: MIT
/** One tool call in an agent turn, and what came back. */
export interface ToolEvent {
  callId: string;
  tool: string;
  argsPreview: string;
  result?: string;
  latencyMs?: number;
}

export type ToolEventInput =
  | { kind: "call"; callId: string; tool: string; args: unknown }
  | { kind: "result"; callId: string; result: unknown; latencyMs: number };

/** How a tool argument is shown. Exported so the approval card formats it the
 *  same way the step row does — two spellings of this drift. */
export function asPreview(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/**
 * Fold one tool event into a message's steps.
 *
 * Pure, so the chat page (which keeps its own message list) and the room
 * (which keeps a store) do not each carry their own copy of the rule.
 */
export function applyToolEvent(
  steps: ToolEvent[] | undefined,
  event: ToolEventInput,
): ToolEvent[] {
  const current = steps ?? [];
  if (event.kind === "call") {
    return [
      ...current,
      {
        callId: event.callId,
        tool: event.tool,
        argsPreview: asPreview(event.args),
      },
    ];
  }
  return current.map((step) =>
    step.callId === event.callId
      ? { ...step, result: asPreview(event.result), latencyMs: event.latencyMs }
      : step,
  );
}
