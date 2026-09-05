// SPDX-License-Identifier: MIT
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Object3D } from "three";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { AvatarRenderer } from "./AvatarRenderer";
import { VrmAvatar } from "./VrmAvatar";
import { GeometricAvatar } from "./GeometricAvatar";
import { Live2DAvatar } from "./Live2DAvatar";
import { isWebGLAvailable } from "./webgl";
import { getModelKind } from "./modelKind";

interface AvatarObjectProps {
  model: string | null;
  rendererRef: React.MutableRefObject<AvatarRenderer | null>;
}

function AvatarObject({ model, rendererRef }: AvatarObjectProps) {
  const [obj, setObj] = useState<Object3D | null>(null);

  useEffect(() => {
    const avatar: AvatarRenderer = model === null ? new GeometricAvatar() : new VrmAvatar();
    rendererRef.current = avatar;
    setObj(avatar.object as Object3D);
    if (model !== null) {
      void (avatar as VrmAvatar).load(model).catch(() => {
        const fallback = new GeometricAvatar();
        rendererRef.current = fallback;
        setObj(fallback.object as Object3D);
      });
    }
    avatar.start();
    return () => {
      avatar.stop();
      avatar.dispose();
      if (rendererRef.current === avatar) rendererRef.current = null;
      setObj(null);
    };
  }, [model, rendererRef]);

  return obj ? <primitive object={obj} /> : null;
}

// Live2D models are DOM-canvas based (pixi), not three.js scenes — they get
// their own host node and never appear inside the R3F <Canvas>.
function Live2DHost({ model, rendererRef }: AvatarObjectProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (model === null) return;
    const avatar = new Live2DAvatar();
    rendererRef.current = avatar;
    let alive = true;
    void avatar
      .load(model)
      .then(() => {
        if (!alive || !hostRef.current) return;
        avatar.attach(hostRef.current);
        avatar.start();
      })
      .catch(() => {
        if (!alive) return;
        avatar.dispose();
        if (rendererRef.current === avatar) rendererRef.current = null;
        setFailed(true);
      });
    return () => {
      alive = false;
      avatar.stop();
      avatar.dispose();
      if (rendererRef.current === avatar) rendererRef.current = null;
    };
  }, [model, rendererRef]);

  if (failed) {
    // Load failure (e.g. Cubism Core missing) → fall back to the geometric avatar.
    return <AvatarObject model={null} rendererRef={rendererRef} />;
  }

  return (
    <div
      ref={hostRef}
      data-testid="live2d-host"
      className="h-full w-full"
      aria-label={t("live.avatar")}
    />
  );
}

export function AvatarCanvas({
  model,
  rendererRef,
}: {
  model: string | null;
  rendererRef: React.MutableRefObject<AvatarRenderer | null>;
}) {
  const { t } = useTranslation();

  if (getModelKind(model) === "live2d") {
    return <Live2DHost model={model} rendererRef={rendererRef} />;
  }

  if (!isWebGLAvailable()) {
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-text-muted">
        {t("live.webglUnavailable")}
      </div>
    );
  }
  return (
    <Canvas camera={{ position: [0, 1.5, 3.0], fov: 45 }} style={{ width: "100%", height: "100%" }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[2, 4, 3]} intensity={1.2} />
      <AvatarObject model={model} rendererRef={rendererRef} />
      <OrbitControls target={[0, 1.2, 0]} enablePan={false} minDistance={1.5} maxDistance={5} />
    </Canvas>
  );
}
