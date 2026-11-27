import { ImageFrame } from "./ImageFrame";
import { useRef, useState } from "react";
import {
  Undo2,
  Redo2,
  PenLine,
  MousePointer2,
  Trash2,
  RotateCcw,
  Check,
  Eraser,
} from "lucide-react";
import type { Point, Polygons } from "../../types/index";
export function PolygonEditor({
  src,
  width,
  height,
  polygons,
  onChange,
  disabled = false,
  original,
}: {
  src: string;
  width: number;
  height: number;
  polygons: Polygons;
  onChange: (p: Polygons) => void;
  disabled?: boolean;
  original: Polygons;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [mode, setMode] = useState("edit");
  const [draft, setDraft] = useState<Point[]>([]);
  const [past, setPast] = useState<Polygons[]>([]);
  const [future, setFuture] = useState<Polygons[]>([]);
  const [selected, setSelected] = useState(0);
  const drag = useRef<{ p: number; v: number } | null>(null);
  const point = (e: { clientX: number; clientY: number }): Point => {
    const r = svg.current!.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
      Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
    ];
  };
  function commit(p: Polygons) {
    setPast((v) => [...v, structuredClone(polygons)]);
    setFuture([]);
    onChange(p);
  }
  function finish() {
    if (draft.length < 3) return;
    commit([...polygons, draft]);
    setSelected(polygons.length);
    setDraft([]);
    setMode("edit");
  }
  return (
    <>
      <div
        className="editor-toolbar"
        role="toolbar"
        aria-label="Ferramentas do polígono"
      >
        <button
          aria-label="Desenhar"
          aria-pressed={mode === "draw"}
          title="Desenhar: clique nos vértices; Enter ou primeiro ponto fecha; Esc cancela"
          disabled={disabled}
          className={mode === "draw" ? "chosen" : ""}
          onClick={() => {
            setMode("draw");
            setDraft([]);
          }}
        >
          <PenLine size={15} />
        </button>
        <button
          aria-label="Editar"
          aria-pressed={mode === "edit"}
          title="Editar: arraste vértices; botão direito remove um vértice"
          disabled={disabled}
          className={mode === "edit" ? "chosen" : ""}
          onClick={() => {
            setMode("edit");
            setDraft([]);
          }}
        >
          <MousePointer2 size={15} />
        </button>
        <button
          title="Desfazer"
          aria-label="Desfazer"
          disabled={disabled || !past.length}
          onClick={() => {
            setFuture((v) => [polygons, ...v]);
            onChange(past[past.length - 1]);
            setPast((v) => v.slice(0, -1));
          }}
        >
          <Undo2 size={16} />
        </button>
        <button
          title="Refazer"
          aria-label="Refazer"
          disabled={disabled || !future.length}
          onClick={() => {
            setPast((v) => [...v, polygons]);
            onChange(future[0]);
            setFuture((v) => v.slice(1));
          }}
        >
          <Redo2 size={16} />
        </button>
        <button
          aria-label="Excluir polígono"
          title="Excluir polígono selecionado"
          disabled={disabled || !polygons.length}
          onClick={() => commit(polygons.filter((_, i) => i !== selected))}
        >
          <Trash2 size={15} />
        </button>
        <button
          aria-label="Limpar"
          title="Limpar todos os polígonos"
          disabled={disabled || !polygons.length}
          onClick={() => {
            commit([]);
            setDraft([]);
          }}
        >
          <Eraser size={15} />
        </button>
        <button
          disabled={disabled}
          onClick={() => {
            commit(structuredClone(original));
            setDraft([]);
          }}
          title="Restaurar geometria salva"
          aria-label="Restaurar geometria salva"
        >
          <RotateCcw size={15} />
        </button>
        <button aria-label="Fechar polígono" title="Fechar polígono (Enter)" disabled={disabled || draft.length < 3} onClick={finish}>
          <Check size={15} />
        </button>
      </div>
      <ImageFrame
        src={src}
        alt="Imagem em anotação"
        width={width}
        height={height}
      >
        <svg
          ref={svg}
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          tabIndex={0}
          aria-label="Editor da faixa de circulação"
          onKeyDown={(e) => {
            if (e.key === "Escape") setDraft([]);
            if (e.key === "Enter") finish();
          }}
          onClick={(e) => {
            if (!disabled && mode === "draw") setDraft((v) => [...v, point(e)]);
          }}
          onPointerMove={(e) => {
            if (!drag.current || disabled) return;
            const { p, v } = drag.current;
            const next = structuredClone(polygons);
            next[p][v] = point(e);
            onChange(next);
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
        >
          {polygons.map((polygon, p) => (
            <g key={p}>
              <polygon
                points={polygon.map((v) => v.join(",")).join(" ")}
                className={p === selected ? "selected" : ""}
                onClick={(e) => {
                  if (mode === "edit") {
                    e.stopPropagation();
                    setSelected(p);
                  }
                }}
              />
              {mode === "edit" &&
                !disabled &&
                polygon.map((vertex, v) => (
                  <circle
                    key={v}
                    cx={vertex[0]}
                    cy={vertex[1]}
                    r=".006"
                    className="vertex"
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      setSelected(p);
                      setPast((previous) => [
                        ...previous,
                        structuredClone(polygons),
                      ]);
                      setFuture([]);
                      drag.current = { p, v };
                      e.currentTarget.setPointerCapture(e.pointerId);
                    }}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      if (polygon.length > 3)
                        commit(
                          polygons.map((poly, i) =>
                            i === p
                              ? poly.filter((_, index) => index !== v)
                              : poly,
                          ),
                        );
                    }}
                  />
                ))}
            </g>
          ))}
          {draft.length > 0 && (
            <>
              <polyline
                points={draft.map((v) => v.join(",")).join(" ")}
                className="draft"
              />
              {draft.map((p, i) => (
                <circle
                  key={i}
                  cx={p[0]}
                  cy={p[1]}
                  r=".006"
                  className="vertex"
                  onClick={(e) => {
                    if (i === 0) {
                      e.stopPropagation();
                      finish();
                    }
                  }}
                />
              ))}
            </>
          )}
        </svg>
      </ImageFrame>
    </>
  );
}
