// SPDX-License-Identifier: MIT
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AvatarCanvas } from "./AvatarCanvas";

const { makeMockAvatar } = vi.hoisted(() => ({
  makeMockAvatar: () =>
    class {
      object = null;
      load = vi.fn(async () => {});
      attach = vi.fn();
      start = vi.fn();
      stop = vi.fn();
      setEmotion = vi.fn();
      speak = vi.fn();
      stopSpeaking = vi.fn();
      dispose = vi.fn();
    },
}));

vi.mock("./VrmAvatar", () => ({
  VrmAvatar: makeMockAvatar(),
  mapEmotionState: () => ({ preset: "relaxed", intensity: 0 }),
}));

vi.mock("./Live2DAvatar", () => ({
  Live2DAvatar: makeMockAvatar(),
}));

vi.mock("./GeometricAvatar", () => ({
  GeometricAvatar: makeMockAvatar(),
}));

describe("AvatarCanvas", () => {
  it("renders the pixi host for .model3.json models", () => {
    render(
      <AvatarCanvas
        model="/api/models/hiyori/hiyori.model3.json"
        rendererRef={{ current: null }}
      />
    );
    expect(screen.getByTestId("live2d-host")).toBeTruthy();
  });
});
