// SPDX-License-Identifier: MIT
export async function fetchModelList(): Promise<string[]> {
  try {
    const res = await fetch("/api/models", {
      headers: { accept: "application/json" },
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { models?: string[] };
    return Array.isArray(data.models) ? data.models : [];
  } catch {
    return [];
  }
}
