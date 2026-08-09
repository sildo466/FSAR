import { create } from "zustand";
import { fetchSocialStatuses, type PlatformStatus } from "../clients/socialClient";

type PlatformName = PlatformStatus["platform"];

type SocialState = {
  statuses: Record<PlatformName, PlatformStatus>;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
};

const initialStatuses: SocialState["statuses"] = {
  telegram: { platform: "telegram", state: "unknown" },
  feishu: { platform: "feishu", state: "unknown" },
  wechat: { platform: "wechat", state: "unknown" },
};

export const useSocialStore = create<SocialState>((set) => ({
  statuses: initialStatuses,
  loading: false,
  error: "",
  refresh: async () => {
    set({ loading: true, error: "" });
    try {
      const statuses = await fetchSocialStatuses();
      set((state) => ({
        statuses: statuses.reduce(
          (next, status) => ({ ...next, [status.platform]: status }),
          state.statuses,
        ),
        loading: false,
      }));
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "Status unavailable",
      });
    }
  },
}));
