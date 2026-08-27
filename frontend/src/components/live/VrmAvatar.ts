// SPDX-License-Identifier: MIT
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import type { VRM } from "@pixiv/three-vrm";
import type { AvatarRenderer, EmotionState } from "./AvatarRenderer";

const BLINK_INTERVAL_MS = 3200;
const BLINK_CLOSE_MS = 140;
const BREATH_AMPLITUDE = 0.008;

export class VrmAvatar implements AvatarRenderer {
  private vrm: VRM | null = null;
  private group = new THREE.Group();
  private clock = new THREE.Clock();
  private nextBlinkAt = 0;
  private blinkStartedAt = -1;
  private running = false;
  private raf = 0;

  async load(url: string): Promise<void> {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    const gltf = await loader.loadAsync(url);
    const vrm: VRM = gltf.userData.vrm;
    VRMUtils.removeUnnecessaryJoints(gltf.scene);
    this.disposeVrm();
    this.vrm = vrm;
    VRMUtils.rotateVRM0(vrm);
    this.group.add(gltf.scene);
  }

  get object(): THREE.Object3D {
    return this.group;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.clock.start();
    this.nextBlinkAt = performance.now() + BLINK_INTERVAL_MS;
    const tick = () => {
      if (!this.running) return;
      const dt = this.clock.getDelta();
      this.vrm?.update(dt);
      this.animateBreath(performance.now());
      this.animateBlink(performance.now());
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  setEmotion(_state: EmotionState): void {
    // no-op until Stage 3 maps emotion to blend shapes
  }

  dispose(): void {
    this.stop();
    this.disposeVrm();
  }

  private animateBreath(now: number): void {
    if (!this.vrm) return;
    const t = now / 1000;
    this.group.position.y = Math.sin(t * 1.6) * BREATH_AMPLITUDE;
  }

  private animateBlink(now: number): void {
    const manager = this.vrm?.expressionManager;
    if (!manager || manager.getExpression("blink") === null) return;
    if (this.blinkStartedAt < 0 && now >= this.nextBlinkAt) {
      this.blinkStartedAt = now;
      this.nextBlinkAt = now + BLINK_INTERVAL_MS;
    }
    if (this.blinkStartedAt >= 0) {
      const el = (now - this.blinkStartedAt) / BLINK_CLOSE_MS;
      const closing = el <= 1 ? el : Math.max(0, 2 - el);
      manager.setValue("blink", closing);
      if (el >= 2) this.blinkStartedAt = -1;
    }
  }

  private disposeVrm(): void {
    if (this.vrm) {
      VRMUtils.deepDispose(this.vrm.scene);
      this.group.clear();
      this.vrm = null;
    }
  }
}