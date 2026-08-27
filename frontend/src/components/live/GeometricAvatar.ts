// SPDX-License-Identifier: MIT
import * as THREE from "three";
import type { AvatarRenderer, EmotionState } from "./AvatarRenderer";

export class GeometricAvatar implements AvatarRenderer {
  private mesh: THREE.Mesh;
  private basePositions: Float32Array;
  private running = false;
  private raf = 0;

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
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  setEmotion(_state: EmotionState): void {}

  dispose(): void {
    this.stop();
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
