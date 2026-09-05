// SPDX-License-Identifier: MIT
import type * as PIXI from "pixi.js";
import type { Live2DModel as L2DModel } from "pixi-live2d-display/cubism4";
import type { AvatarRenderer, EmotionState } from "./AvatarRenderer";
import { mapEmotionState, type ExpressionPreset } from "./VrmAvatar";
import { getActiveLipsync } from "../../stores/speech";

export function mapPresetToLive2DExpression(preset: ExpressionPreset): string {
  return preset === "relaxed" ? "" : preset;
}

export function computeMouthOpen(volume: number): number {
  return volume < 0 ? 0 : volume > 1 ? 1 : volume;
}

// pixi-live2d-display needs window.PIXI.Ticker so models auto-update; keep
// the assignment lazy so this module stays importable in jsdom unit tests.
async function ensureWindowPixi(): Promise<typeof import("pixi.js")> {
  const pixi = await import("pixi.js");
  const w = window as unknown as { PIXI?: unknown };
  if (!w.PIXI) w.PIXI = pixi;
  return pixi;
}

interface CoreModelLike {
  setParameterValueById(id: string, value: number, weight?: number): void;
}

interface ExpressionManagerLike {
  setExpression(name: string): Promise<boolean>;
  resetExpression(): void;
}

const MOUTH_SMOOTH = 0.4;
const MOUTH_WEIGHT = 0.8;

export class Live2DAvatar implements AvatarRenderer {
  private app: PIXI.Application | null = null;
  private model: L2DModel | null = null;
  private host: HTMLElement | null = null;
  private observer: ResizeObserver | null = null;
  private speaking = false;
  private mouthOpen = 0;
  private naturalW = 0;
  private naturalH = 0;

  get object(): null {
    return null;
  }

  async load(url: string): Promise<void> {
    await ensureWindowPixi();
    const { Live2DModel } = await import("pixi-live2d-display/cubism4");
    this.model = await Live2DModel.from(url, { autoInteract: false });
    this.model.anchor.set(0.5, 0.5);
    // Read the unscaled size once; scale then would feed back into bounds.
    this.naturalW = this.model.width || 1;
    this.naturalH = this.model.height || 1;
  }

  attach(host: HTMLElement): void {
    this.host = host;
    void ensureWindowPixi().then((pixi) => {
      if (!this.host) return;
      this.app = new pixi.Application({
        width: host.clientWidth || 400,
        height: host.clientHeight || 400,
        backgroundAlpha: 0,
        antialias: true,
      });
      host.appendChild(this.app.view as HTMLCanvasElement);
      if (this.model) {
        this.app.stage.addChild(this.model as unknown as PIXI.DisplayObject);
        this.layout();
      }
    });
    this.observer = new ResizeObserver(() => this.layout());
    this.observer.observe(host);
  }

  start(): void {
    this.app?.ticker.add(this.tick);
  }

  stop(): void {
    this.app?.ticker.remove(this.tick);
  }

  speak(): void {
    this.speaking = true;
  }

  stopSpeaking(): void {
    this.speaking = false;
  }

  setEmotion(state: EmotionState): void {
    if (!this.model) return;
    const mapped = mapEmotionState(state);
    const name = mapPresetToLive2DExpression(mapped.preset);
    const manager = (
      this.model.internalModel as { expressionManager?: ExpressionManagerLike }
    ).expressionManager;
    if (!manager) return;
    if (name) {
      void manager.setExpression(name).catch(() => {});
    } else {
      manager.resetExpression();
    }
  }

  dispose(): void {
    this.stop();
    this.observer?.disconnect();
    this.observer = null;
    this.model?.destroy();
    this.model = null;
    this.app?.destroy(true);
    this.app = null;
    this.host = null;
  }

  private layout(): void {
    if (!this.app || !this.model || !this.host) return;
    const w = this.host.clientWidth || 400;
    const h = this.host.clientHeight || 400;
    if (this.app.renderer.width !== w || this.app.renderer.height !== h) {
      this.app.renderer.resize(w, h);
    }
    const scale = Math.min(w / this.naturalW, h / this.naturalH) * 0.85;
    this.model.scale.set(scale);
    this.model.position.set(w / 2, h / 2);
  }

  private tick = (): void => {
    if (!this.app || !this.model) return;
    const core = (
      this.model.internalModel as { coreModel?: CoreModelLike }
    ).coreModel;
    if (!core) return;
    const lipsync = getActiveLipsync();
    const target = this.speaking && lipsync ? computeMouthOpen(lipsync.read().volume) : 0;
    this.mouthOpen += (target - this.mouthOpen) * MOUTH_SMOOTH;
    try {
      core.setParameterValueById("ParamMouthOpenY", this.mouthOpen, MOUTH_WEIGHT);
    } catch {
      // Parameter missing on this model; skip the frame.
    }
  };
}
