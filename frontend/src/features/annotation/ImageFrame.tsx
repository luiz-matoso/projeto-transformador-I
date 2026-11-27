import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
export function ImageFrame({
  src,
  alt,
  width,
  height,
  children,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
  children: ReactNode;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.min(
        entry.contentRect.width,
        (entry.contentRect.height * width) / height,
      );
      setSize({ width: w, height: (w * height) / width });
    });
    observer.observe(stage.current!);
    return () => observer.disconnect();
  }, [width, height]);
  return (
    <div className="annotation-image-stage" ref={stage}>
      <div className="polygon-frame" style={size}>
        <img src={src} alt={alt} draggable={false} />
        {children}
      </div>
    </div>
  );
}
