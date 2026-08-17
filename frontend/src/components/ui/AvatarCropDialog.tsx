// SPDX-License-Identifier: MIT
import { useCallback, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { X } from "lucide-react";

interface Props {
  open: boolean;
  imageSrc: string | null;
  aspect?: number;
  onCancel: () => void;
  onConfirm: (blob: Blob) => void;
}

export function AvatarCropDialog({ open, imageSrc, aspect = 1, onCancel, onConfirm }: Props) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);

  const onCropComplete = useCallback((_area: Area, pixels: Area) => {
    setCroppedAreaPixels(pixels);
  }, []);

  const handleConfirm = async () => {
    if (!imageSrc) return;
    const blob = await getCroppedBlob(imageSrc, croppedAreaPixels);
    if (blob && blob.size > 0) {
      onConfirm(blob);
    } else {
      alert("Crop produced an empty image — please drag the crop frame first.");
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center"
      data-testid="avatar-crop-dialog"
    >
      <div className="bg-bg border border-border rounded shadow-xl w-[min(640px,92vw)] max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between px-4 h-12 border-b border-border">
          <div className="font-display text-sm font-semibold">Crop avatar</div>
          <button onClick={onCancel} className="p-1 rounded hover:bg-surface" aria-label="close">
            <X size={16} />
          </button>
        </div>
        <div className="relative w-full" style={{ height: 360, background: "#111" }}>
          <Cropper
            image={imageSrc ?? ""}
            crop={crop}
            zoom={zoom}
            aspect={aspect}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
            showGrid={false}
          />
        </div>
        <div className="px-4 py-3 flex items-center gap-3 border-t border-border">
          <label className="text-caption text-text-muted">Zoom</label>
          <input
            type="range"
            min={1}
            max={3}
            step={0.05}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="flex-1"
          />
        </div>
        <div className="px-4 py-3 flex items-center justify-end gap-2 border-t border-border">
          <button onClick={onCancel} className="px-3 h-8 border border-border rounded text-[12px]">
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            data-testid="avatar-crop-confirm"
            className="px-3 h-8 bg-[var(--button-bg)] text-[var(--button-text)] button-tex rounded text-[12px]"
          >
            Use avatar
          </button>
        </div>
      </div>
    </div>
  );
}

async function getCroppedBlob(imageSrc: string, area: Area | null): Promise<Blob | null> {
  const img = await loadImage(imageSrc);
  const w = area?.width ?? img.naturalWidth;
  const h = area?.height ?? img.naturalHeight;
  if (w <= 0 || h <= 0) return null;
  const cropX = area?.x ?? 0;
  const cropY = area?.y ?? 0;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(img, cropX, cropY, w, h, 0, 0, w, h);
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", 0.9));
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}
