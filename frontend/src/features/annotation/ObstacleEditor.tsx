import { createPortal } from "react-dom";
import { ImageFrame } from "./ImageFrame";
import { useRef, useState } from "react";
import type { Polygons, Point } from "../../types/index";
import { annotationSchema, label } from "../../services/data";
import type { ObstacleInstance } from "./v4";
export function ObstacleEditor({
  src,
  width,
  height,
  polygons,
  instances,
  onChange,
  disabled,
  controlsContainer,
}: {
  src: string;
  width: number;
  height: number;
  polygons: Polygons;
  instances: ObstacleInstance[];
  onChange: (v: ObstacleInstance[]) => void;
  disabled: boolean;
  controlsContainer?: HTMLElement | null;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [selected, setSelected] = useState("");
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<Point | null>(null);
  const [end, setEnd] = useState<Point | null>(null);
  const drag = useRef<{
    id: string;
    corner: number;
    start: Point;
    box: ObstacleInstance["bbox"];
  } | null>(null);
  const point = (event: { clientX: number; clientY: number }): Point => {
    const r = svg.current!.getBoundingClientRect();
    return [
      Math.max(0, Math.min(1, (event.clientX - r.left) / r.width)),
      Math.max(0, Math.min(1, (event.clientY - r.top) / r.height)),
    ];
  };
  const update = (id: string, patch: Partial<ObstacleInstance>) =>
    onChange(instances.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  function finish() {
    if (
      draft &&
      end &&
      Math.abs(end[0] - draft[0]) > 0.003 &&
      Math.abs(end[1] - draft[1]) > 0.003
    ) {
      const id = crypto.randomUUID();
      onChange([
        ...instances,
        {
          id,
          type: "",
          bbox: [
            Math.min(draft[0], end[0]),
            Math.min(draft[1], end[1]),
            Math.max(draft[0], end[0]),
            Math.max(draft[1], end[1]),
          ],
          path_relation: "unknown",
        },
      ]);
      setSelected(id);
      setDrawing(false);
    }
    setDraft(null);
    setEnd(null);
    drag.current = null;
  }
  const controls = instances.map((i, n) => (
    <fieldset key={i.id} disabled={disabled} className="instance-fields">
      <legend>
        <button onClick={() => setSelected(i.id)}>Objeto {n + 1}</button>
      </legend>
      <label>
        Tipo do objeto {n + 1}
        <select
          aria-label={`Tipo do objeto ${n + 1}`}
          value={i.type}
          onChange={(e) => update(i.id, { type: e.target.value })}
        >
          <option value="">Selecionar…</option>
          {annotationSchema.fields
            .find((f) => f.name === "obstacle_type")!
            .options.map((o) => (
              <option key={o.value} value={o.value}>
                {label("obstacle_type", o.value)}
              </option>
            ))}
        </select>
      </label>
      <label>
        Relação com a faixa {n + 1}
        <select
          aria-label={`Relação com a faixa ${n + 1}`}
          value={i.path_relation}
          onChange={(e) => update(i.id, { path_relation: e.target.value })}
        >
          {Object.entries({
            outside: "Fora da faixa",
            encroaching: "Invade a borda",
            on_path: "Na faixa",
            unknown: "Não é possível determinar",
          }).map(([v, text]) => (
            <option key={v} value={v}>
              {text}
            </option>
          ))}
        </select>
      </label>
    </fieldset>
  ));
  return (
    <>
      <div className="editor-toolbar obstacle-toolbar" role="toolbar" aria-label="Ferramentas dos obstáculos">
        <button
          title="Arraste para delimitar o obstáculo"
          aria-pressed={drawing}
          disabled={disabled}
          className={drawing ? "chosen" : ""}
          onClick={() => setDrawing(!drawing)}
        >
          Delimitar obstáculo
        </button>
        <button
          title="Excluir a caixa selecionada"
          disabled={disabled || !selected}
          onClick={() => {
            onChange(instances.filter((i) => i.id !== selected));
            setSelected("");
          }}
        >
          Excluir caixa
        </button>
      </div>
      <ImageFrame
        src={src}
        alt="Objetos e faixa de circulação"
        width={width}
        height={height}
      >
        <svg
          ref={svg}
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          aria-label="Editor de caixas de obstáculos"
          onPointerDown={(e) => {
            if (disabled || !drawing) return;
            setDraft(point(e));
            setEnd(point(e));
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (disabled) return;
            const p = point(e);
            if (draft) {
              setEnd(p);
              return;
            }
            if (drag.current) {
              const d = drag.current;
              let box = [...d.box] as ObstacleInstance["bbox"];
              if (d.corner === -1) {
                const dx = Math.max(
                  -box[0],
                  Math.min(1 - box[2], p[0] - d.start[0]),
                );
                const dy = Math.max(
                  -box[1],
                  Math.min(1 - box[3], p[1] - d.start[1]),
                );
                box = [box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy];
              } else {
                box[d.corner === 0 || d.corner === 3 ? 0 : 2] = p[0];
                box[d.corner < 2 ? 1 : 3] = p[1];
              }
              if (box[0] < box[2] && box[1] < box[3])
                update(d.id, { bbox: box });
            }
          }}
          onPointerUp={finish}
          onPointerCancel={() => {
            drag.current = null;
            setDraft(null);
          }}
        >
          {polygons.map((p, i) => (
            <polygon
              key={i}
              points={p.map((v) => v.join(",")).join(" ")}
              style={{ pointerEvents: "none", fill: "none" }}
            />
          ))}
          {instances.map((i) => (
            <g key={i.id}>
              <rect
                x={i.bbox[0]}
                y={i.bbox[1]}
                width={i.bbox[2] - i.bbox[0]}
                height={i.bbox[3] - i.bbox[1]}
                className="obstacle-box"
                strokeWidth={i.id === selected ? 3 : 1.5}
                onPointerDown={(e) => {
                  if (disabled || drawing) return;
                  e.stopPropagation();
                  setSelected(i.id);
                  drag.current = {
                    id: i.id,
                    corner: -1,
                    start: point(e),
                    box: i.bbox,
                  };
                  e.currentTarget.setPointerCapture(e.pointerId);
                }}
              />
              {i.id === selected &&
                !disabled &&
                [
                  [i.bbox[0], i.bbox[1]],
                  [i.bbox[2], i.bbox[1]],
                  [i.bbox[2], i.bbox[3]],
                  [i.bbox[0], i.bbox[3]],
                ].map((p, c) => (
                  <circle
                    key={c}
                    cx={p[0]}
                    cy={p[1]}
                    r=".008"
                    className="vertex"
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      drag.current = {
                        id: i.id,
                        corner: c,
                        start: point(e),
                        box: i.bbox,
                      };
                      e.currentTarget.setPointerCapture(e.pointerId);
                    }}
                  />
                ))}
            </g>
          ))}
          {draft && end && (
            <rect
              x={Math.min(draft[0], end[0])}
              y={Math.min(draft[1], end[1])}
              width={Math.abs(end[0] - draft[0])}
              height={Math.abs(end[1] - draft[1])}
              className="obstacle-box"
            />
          )}
        </svg>
      </ImageFrame>
      {controlsContainer
        ? createPortal(controls, controlsContainer)
        : controlsContainer === undefined
          ? controls
          : null}
    </>
  );
}
