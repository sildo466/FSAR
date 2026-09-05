// SPDX-License-Identifier: MIT
export type LiveModelKind = "none" | "vrm" | "live2d";

export function getModelKind(name: string | null): LiveModelKind {
  if (name === null) return "none";
  if (name.toLowerCase().endsWith(".model3.json")) return "live2d";
  return "vrm";
}

export function buildModelUrl(name: string): string {
  const encoded = name.split("/").map((seg) => encodeURIComponent(seg)).join("/");
  return `/api/models/${encoded}`;
}
