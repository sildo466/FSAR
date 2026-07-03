// SPDX-License-Identifier: Apache-2.0
export interface SlashCommand {
  name: string;
  description: string;
  usage: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "memory", description: "Manage memory database", usage: "/memory [stats|sessions|delete <id>]" },
  { name: "stats", description: "Tool decision-log aggregates", usage: "/stats [tool <name>|recent]" },
  { name: "exp", description: "Experience library CRUD", usage: "/exp [view|del|stale|archive] <name>" },
  { name: "learn", description: "Persist a new experience", usage: "/learn <name> <category> \"<description>\"" },
  { name: "remember", description: "Save a cross-session fact", usage: "/remember \"<fact>\"" },
  { name: "facts", description: "List / search saved facts", usage: "/facts [keyword]" },
  { name: "import", description: "Import external skill markdown", usage: "/import <path>" },
  { name: "skills", description: "External skills CRUD", usage: "/skills [status|activity <name> <enable|disable>]|delete <name>" },
];

export function filterCommands(query: string): SlashCommand[] {
  const q = query.toLowerCase();
  if (!q) return SLASH_COMMANDS.slice(0, 4);
  return SLASH_COMMANDS.filter((c) => c.name.startsWith(q));
}
