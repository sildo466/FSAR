// SPDX-License-Identifier: MIT
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Object3D } from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { AvatarRenderer } from "./AvatarRenderer";
import { VrmAvatar } from "./VrmAvatar";
import { GeometricAvatar } from "./GeometricAvatar";
import { isWebGLAvailable } from "./webgl";

interface AvatarObjectProps {
  model: string | null;
}

function AvatarObject({ model }: AvatarObjectProps) {
  const [obj, setObj] = useState<Object3D | null>(null);

  useEffect(() => {
    const avatar: AvatarRenderer = model === null ? new GeometricAvatar() : new VrmAvatar();
    setObj(avatar.object as Object3D);
    if (model !== null) {
      void (avatar as VrmAvatar).load(model).catch(() => {
        setObj(new GeometricAvatar().object as Object3D);
      });
    }
    avatar.start();
    return () => {
      avatar.stop();
      avatar.dispose();
      setObj(null);
    };
  }, [model]);

  useFrame(() => {});

  return obj ? <primitive object={obj} /> : null;
}

export function AvatarCanvas({ model }: { model: string | null }) {
  const { t } = useTranslation();
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
      <AvatarObject model={model} />
      <OrbitControls target={[0, 1.2, 0]} enablePan={false} minDistance={1.5} maxDistance={5} />
    </Canvas>
  );
}
