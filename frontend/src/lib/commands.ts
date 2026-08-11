// SPDX-License-Identifier: MIT
export interface SlashCommand {
  name: string;
  description: string;
  usage: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "help", description: "List all commands", usage: "/help" },
  { name: "memory", description: "Manage memory database", usage: "/memory [stats|sessions|session <id>|delete <id>|search <kw>]" },
  { name: "history", description: "Recent messages in context", usage: "/history" },
  { name: "search", description: "Search long-term memory", usage: "/search <keyword>" },
  { name: "clear", description: "Clear conversation context", usage: "/clear" },
  { name: "resume", description: "Load a past session", usage: "/resume [id]" },
  { name: "config", description: "Show active provider config", usage: "/config" },
  { name: "tools", description: "List available tools", usage: "/tools" },
  { name: "mcp", description: "MCP server status / reload", usage: "/mcp [reload]" },
  { name: "perm", description: "Permission control", usage: "/perm [mode|trust|deny|grant|revoke|reset]" },
  { name: "audit", description: "Recent audit log", usage: "/audit [N]" },
  { name: "rate", description: "Rate the most recent reply", usage: "/rate <1-5> [reason]" },
  { name: "profile", description: "View / edit user profile", usage: "/profile [set <k> <v>|del <k>]" },
  { name: "prefs", description: "Preferences CRUD", usage: "/prefs [set|get|del]" },
  { name: "feedback", description: "Rating statistics", usage: "/feedback" },
  { name: "reflect", description: "Force immediate reflection", usage: "/reflect" },
  { name: "stats", description: "Tool decision-log aggregates", usage: "/stats [tool <name>|recent]" },
  { name: "exp", description: "Experience library CRUD", usage: "/exp [view|del|stale|archive] <name>" },
  { name: "use", description: "Load a learned skill/experience into context", usage: "/use <name> [task...]" },
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
