// SPDX-License-Identifier: MIT
import * as THREE from "three";
import type { AvatarRenderer, EmotionState } from "./AvatarRenderer";
import { mapEmotionState, type ExpressionPreset } from "./VrmAvatar";
import { getActiveLipsync } from "../../stores/speech";

const EMOTION_COLORS: Record<ExpressionPreset, number> = {
  happy: 0xd9a53a,
  angry: 0xb3342a,
  sad: 0x33507a,
  relaxed: 0x3a7a5c,
  surprised: 0x8a5ac0,
};

export class GeometricAvatar implements AvatarRenderer {
  private mesh: THREE.Mesh;
  private basePositions: Float32Array;
  private running = false;
  private raf = 0;
  private speaking = false;
  private mouthScale = 0;
  private emotionPreset: ExpressionPreset = "relaxed";
  private emotionIntensity = 0;

  constructor() {
    const geo = new THREE.IcosahedronGeometry(1, 5);
    const mat = new THREE.MeshStandardMaterial({
      color: 0x111111,
      roughness: 0.55,
      metalness: 0.35,
      flatShading: true,
    });
    this.mesh = new THREE.Mesh(geo, mat);
    geo.computeVertexNormals();
    this.basePositions = new Float32Array((geo.attributes.position as THREE.BufferAttribute).array.slice() as unknown as number[]);
  }

  get object(): THREE.Object3D {
    return this.mesh;
  }

  async load(_url: string): Promise<void> {}

  start(): void {
    if (this.running) return;
    this.running = true;
    const tick = (now: number) => {
      if (!this.running) return;
      const t = now / 1000;
      const geo = this.mesh.geometry as THREE.BufferGeometry;
      const pos = geo.attributes.position as THREE.BufferAttribute;
      const arr = pos.array as Float32Array;
      for (let i = 0; i < arr.length; i++) {
        const base = this.basePositions[i];
        const js = Math.sin(t * 1.3 + i * 0.9);
        arr[i] = base * (1 + 0.03 * js);
      }
      pos.needsUpdate = true;
      geo.computeVertexNormals();
      this.mesh.rotation.y += 0.003;
      this.mesh.rotation.x = Math.sin(t * 0.4) * 0.15;
      this.animateMouth();
      this.animateEmotion();
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  speak(): void {
    this.speaking = true;
  }

  stopSpeaking(): void {
    this.speaking = false;
  }

  setEmotion(state: EmotionState): void {
    const mapped = mapEmotionState(state);
    this.emotionPreset = mapped.preset;
    this.emotionIntensity = mapped.intensity;
  }

  dispose(): void {
    this.stop();
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }

  private animateMouth(): void {
    const lipsync = getActiveLipsync();
    if (this.speaking && lipsync) {
      const frame = lipsync.read();
      this.mouthScale += (frame.volume - this.mouthScale) * 0.4;
    } else {
      this.mouthScale *= 0.8;
      if (this.mouthScale < 0.005) this.mouthScale = 0;
    }
    const s = 1 + this.mouthScale * 0.12;
    this.mesh.scale.set(s, s, s);
  }

  private animateEmotion(): void {
    const target = new THREE.Color(EMOTION_COLORS[this.emotionPreset]).lerp(
      new THREE.Color(0x111111),
      1 - this.emotionIntensity,
    );
    const mat = this.mesh.material as THREE.MeshStandardMaterial;
    mat.color.lerp(target, 0.05);
  }
}
