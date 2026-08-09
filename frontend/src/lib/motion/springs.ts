export const springs = {
  default: { type: "spring", stiffness: 260, damping: 26 },
  bouncy: { type: "spring", stiffness: 380, damping: 18 },
  smooth: { type: "spring", stiffness: 200, damping: 24 },
  breath: { type: "spring", stiffness: 80, damping: 14 },
} as const;
