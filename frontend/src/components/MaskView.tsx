import { useEffect, useRef } from "react";
export function MaskView({
  src,
  mask,
  show = true,
}: {
  src: string;
  mask?: string | null;
  show?: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let active = true;
    async function render() {
      const image = new Image();
      image.src = src;
      await image.decode();
      if (!active || !canvas.current) return;
      const c = canvas.current;
      c.width = image.width;
      c.height = image.height;
      const ctx = c.getContext("2d")!;
      ctx.drawImage(image, 0, 0);
      if (mask && show) {
        const m = new Image();
        m.src = "data:image/png;base64," + mask;
        await m.decode();
        if (!active) return;
        const overlay = document.createElement("canvas");
        overlay.width = c.width;
        overlay.height = c.height;
        const oc = overlay.getContext("2d")!;
        oc.drawImage(m, 0, 0, c.width, c.height);
        const pixels = oc.getImageData(0, 0, c.width, c.height);
        for (let i = 0; i < pixels.data.length; i += 4) {
          const alpha = pixels.data[i];
          pixels.data[i] = 59;
          pixels.data[i + 1] = 130;
          pixels.data[i + 2] = 246;
          pixels.data[i + 3] = Math.round(alpha * 0.45);
        }
        oc.putImageData(pixels, 0, 0);
        ctx.drawImage(overlay, 0, 0);
      }
    }
    render().catch(() => {});
    return () => {
      active = false;
    };
  }, [src, mask, show]);
  return (
    <canvas
      ref={canvas}
      aria-label="Fotografia do trecho com visualização da máscara"
      className="mask-view"
    />
  );
}
