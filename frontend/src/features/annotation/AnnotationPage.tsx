import { useEffect, useState, useRef } from "react";
import { ArrowLeft, ArrowRight, Save, Download, PenLine } from "lucide-react";
import { useDataset } from "../dataset/LocalDataset";
import { validateRow, coherence } from "./annotations";
import { annotationSchema, label } from "../../services/data";
import type { Row, Polygons } from "../../types/index";
import { dimensions } from "../dataset/files";
import { migrateV4, newRowV4, matchesStatus, statusLabel } from "./v4";
import { ObstacleEditor } from "./ObstacleEditor";
import { PolygonEditor } from "./PolygonEditor";
import { useFileURL, Notice } from "../../components/ui";
import { ChoiceGroup } from "./ChoiceGroup";
import { prepareReview } from "./review";
import { analyze, session } from "../../services/api";
import { defaultProfiles } from "../demonstration/profiles/profiles";
import { Loading } from "../../components/ui/Loading";
import { maskPolygons } from "./maskPolygons";
import { Definitions } from "./Definitions";
import { attributeGroups, contextFields, sectionIcons } from "./presentation";
export function AnnotationPage({
  initialKey,
  onDirty,
  navigate,
}: {
  initialKey: string | null;
  onDirty: (dirty: boolean) => void;
  navigate: (page: string, key?: string) => void;
}) {
  const d = useDataset();
  const annotationNotice = /^(Anotação salva|CSV salvo|CSV exportado)|não foi possível|falha|autorizar|reabra|retome/i.test(d.notice) ? d.notice : "";
  const [key, setKey] = useState(
      initialKey || d.cursor || d.images[0]?.key || "",
    ),
    [row, setRow] = useState<Row | null>(null),
    [original, setOriginal] = useState<Row | null>(null),
    [editing, setEditing] = useState(false),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [filter, setFilter] = useState("all");
  const [suggestion, setSuggestion] = useState<Polygons | null>(null),
    [source, setSource] = useState(""),
    [date, setDate] = useState("");
  const [tab, setTab] = useState("annotation");
  const attributes = useRef<HTMLDivElement>(null);
  const loadedImageKey = useRef<string | undefined>(undefined);
  const [obstacleControls, setObstacleControls] =
    useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (attributes.current) attributes.current.scrollTop = 0;
  }, [key]);
  const [spatialMode, setSpatialMode] = useState("path");
  useEffect(() => {
    if (d.images.length && !d.images.some((i) => i.key === key))
      setKey(initialKey || d.cursor || d.images[0].key);
  }, [d.images]);
  useEffect(() => {
    if (key && d.images.some((i) => i.key === key)) d.setCursor(key);
  }, [key]);
  const image = d.images.find((i) => i.key === key);
  const src = useFileURL(image?.file);
  useEffect(() => {
    onDirty(dirty);
  }, [dirty, onDirty]);
  useEffect(() => {
    let active = true;
    setError("");
    setSuggestion(null);
    if (loadedImageKey.current !== image?.key) {
      setRow(null);
      loadedImageKey.current = image?.key;
    }
    if (!image) return;
    dimensions(image.file)
      .then(([w, h]) => {
        if (!active) return;
        const saved = d.rowFor(image.key);
        const next = saved ? migrateV4(saved) : newRowV4(image.key, w, h);
        next.filename = image.key;
        if (Number(next.image_width) !== w || Number(next.image_height) !== h) {
          setError(
            "As dimensões da imagem diferem do CSV. Verifique a imagem antes de editar.",
          );
          return;
        }
        if (!next.annotator_id) next.annotator_id = session.username();
        setOriginal(saved ? structuredClone(saved) : null);
        setRow(next);
        setEditing(next.workflow_status !== "finalized");
        setDirty(false);
      })
      .catch(() => setError("Não foi possível decodificar a imagem."));
    return () => {
      active = false;
    };
  }, [image?.key, d.rows]);
  function change(name: string, value: string) {
    setRow((r) => (r ? { ...r, [name]: value } : r));
    setDirty(true);
  }
  function move(next: string) {
    if (dirty && !confirm("Descartar alterações ainda não salvas?")) return;
    setDirty(false);
    setKey(next);
  }
  const list = d.images.filter((i) => matchesStatus(d.rowFor(i.key), filter));
  const index = list.findIndex((i) => i.key === key);
  function polygons() {
    return JSON.parse(row?.circulation_path || "[]") as Polygons;
  }
  function geometry(next: Polygons) {
    setRow((r) =>
      r
        ? {
            ...r,
            circulation_path: JSON.stringify(next),
            circulation_path_status: next.length ? "annotated" : "unknown",
          }
        : r,
    );
    setDirty(true);
  }
  async function save(next = false, exportOnly = false, finalize = false) {
    if (!row || busy) return;
    setError("");
    try {
      const update = prepareReview(
        row,
        session.username(),
        finalize,
        new Date().toISOString(),
      );
      if (!original || row.circulation_path !== original.circulation_path) {
        update.circulation_path_origin = "manual";
      }
      if (suggestion)
        update.comment = (
          update.comment +
          "\nAuxílio visual: SegFormer common-dino-split; geometria revisada manualmente."
        ).trim();
      validateRow(update);
      setBusy(true);
      await d.saveRow(update, exportOnly);
      setDirty(false);
      if (next && index < list.length - 1) setKey(list[index + 1].key);
      if (finalize && attributes.current) attributes.current.scrollTop = 0;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar.");
    } finally {
      setBusy(false);
    }
  }
  async function suggest() {
    if (!image) return;
    setBusy(true);
    setError("");
    try {
      if (!source || !date)
        throw new Error(
          "Para solicitar sugestão à API, informe uma origem e uma data válida. Não use a data atual como captura de uma imagem antiga.",
        );
      const result = await analyze(
        image.file,
        [defaultProfiles[0]],
        source,
        date,
        24,
      );
      if (!result.mask) throw new Error(result.observation.message);
      const converted = await maskPolygons(result.mask.data);
      if (!converted.length)
        throw new Error(
          "A máscara não produziu um contorno utilizável. Desenhe manualmente.",
        );
      setSuggestion(converted);
      geometry(converted);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha na sugestão.");
    } finally {
      setBusy(false);
    }
  }
  if (!d.images.length)
    return (
      <div className="page is-empty">
        <header className="page-heading">
          <h1>Anotação</h1>
        </header>
        <div className="empty">
          <PenLine size={28} />
          <h2>Abra um dataset para começar</h2>
          <button className="primary" onClick={() => navigate("dataset")}>
            Selecionar dataset
          </button>
        </div>
      </div>
    );
  const disabled = !editing || busy;
  function choices(
    name: string,
    title: string,
    options: { value: string; label: string }[],
  ) {
    return (
      <div className="annotation-field" key={name}>
        <span className="annotation-field-title">{title}</span>
        <ChoiceGroup
          field={name}
          label={title}
          value={row?.[name] || ""}
          options={options}
          disabled={disabled}
          onChange={(value) => change(name, value)}
        />
      </div>
    );
  }
  function changeList(name: string, values: string[], availability: string) {
    setRow((r) =>
      r
        ? {
            ...r,
            [name]: JSON.stringify(values),
            [name + "_availability"]: availability,
          }
        : r,
    );
    setDirty(true);
  }
  function renderGroup(group: (typeof attributeGroups)[number]) {
    if (!row) return null;
    return (
      <fieldset
        className="annotation-group"
        key={group.title}
        disabled={disabled}
      >
        <legend>
          <group.icon size={16} aria-hidden="true" />{group.title}
        </legend>
        {group.names.map((name) => {
          const field = annotationSchema.fields.find(
            (f) => f.name === name,
          )!;
          const multiple = field.kind === "multilabel";
          const selected: string[] = multiple
            ? JSON.parse(row[name] || "[]")
            : [];
          return (
            <div className="annotation-field" key={name}>
              <span
                className="annotation-field-title"
                id={name + "-title"}
              >
                {field.display_name}
              </span>
              {multiple ? (
                <div role="group" aria-labelledby={name + "-title"}>
                  <div className="pills annotation-list-status">
                    <button
                      type="button"
                      data-tone="favorable"
                      aria-pressed={
                        !selected.length &&
                        row[name + "_availability"] === "assessed"
                      }
                      className={
                        !selected.length &&
                        row[name + "_availability"] === "assessed"
                          ? "chosen"
                          : ""
                      }
                      onClick={() =>
                        changeList(name, [], "assessed")
                      }
                    >
                      Nenhum relevante
                    </button>
                    <button
                      type="button"
                      data-tone="unknown"
                      aria-pressed={
                        row[name + "_availability"] === "unknown"
                      }
                      className={
                        row[name + "_availability"] === "unknown"
                          ? "chosen"
                          : ""
                      }
                      onClick={() =>
                        change(name + "_availability", "unknown")
                      }
                    >
                      Desconhecida
                    </button>
                    {(
                      <button
                        type="button"
                        disabled={!selected.length || disabled}
                        aria-pressed={
                          selected.length > 0 && row[name + "_availability"] === "assessed"
                        }
                        className={
                          selected.length > 0 && row[name + "_availability"] === "assessed"
                            ? "chosen"
                            : ""
                        }
                        onClick={() =>
                          change(name + "_availability", "assessed")
                        }
                      >
                        Lista revisada
                      </button>
                    )}
                  </div>
                  <div className="pills">
                    {field.options.map((option) => (
                      <button
                        type="button"
                        key={option.value}
                        aria-pressed={selected.includes(
                          option.value,
                        )}
                        className={
                          selected.includes(option.value)
                            ? "chosen"
                            : ""
                        }
                        onClick={() => {
                          const next = selected.includes(
                            option.value,
                          )
                            ? selected.filter(
                                (v) => v !== option.value,
                              )
                            : [...selected, option.value];
                          changeList(
                            name,
                            field.options
                              .map((o) => o.value)
                              .filter((v) => next.includes(v)),
                            next.length ? "assessed" : "unknown",
                          );
                        }}
                      >
                        {label(name, option.value)}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <ChoiceGroup
                  field={name}
                  label={field.display_name}
                  value={row[name]}
                  options={field.options.map((o) => ({
                    value: o.value,
                    label:
                      o.value === "unknown"
                        ? "Desconhecida"
                        : label(name, o.value),
                  }))}
                  onChange={(value) => change(name, value)}
                />
              )}
            </div>
          );
        })}
        {group.title === "Obstáculos" && spatialMode === "objects" && (
          <div className="annotation-field instance-panel">
            <h3>Objetos delimitados</h3>
            <div ref={setObstacleControls} />
          </div>
        )}
      </fieldset>
    );
  }
  return (
    <div className="annotation-workspace">
      <header className="page-heading compact">
        <h1>Anotação</h1>
        <select
          aria-label="Filtrar anotações"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Todas as imagens</option>
          <option value="pending">Todas pendentes</option>
          <option value="pending_review">Pendente de revisão</option>
          <option value="pending_annotation">Pendente de anotação</option>
          <option value="finalized">Finalizadas</option>
          <option value="low">Confiança baixa</option>
        </select>
      </header>
      <div className="annotation-message" aria-live="polite">
        {error ? (
          <Notice error>{error}</Notice>
        ) : annotationNotice ? (
          <Notice>{annotationNotice}</Notice>
        ) : null}
      </div>
      <div className="annotation-layout">
        <section className="annotation-image" aria-label="Imagem e ferramentas">
          <div className="annotation-filename">
            <strong>{image?.key}</strong>
            <span>
              {statusLabel(row || undefined)}
              {dirty ? " · alterações não salvas" : ""}
            </span>
          </div>
          <div className="editor-toolbar editor-modes" role="toolbar" aria-label="Modo de desenho">
            <button
              aria-pressed={spatialMode === "path"}
              className={spatialMode === "path" ? "chosen" : ""}
              onClick={() => setSpatialMode("path")}
            >
              Máscara de circulação
            </button>
            <button
              aria-pressed={spatialMode === "objects"}
              className={spatialMode === "objects" ? "chosen" : ""}
              onClick={() => setSpatialMode("objects")}
            >
              Obstáculos espaciais
            </button>
          </div>
          <div className="annotation-canvas-area">
            {row &&
              src &&
              (spatialMode === "objects" ? (
                <ObstacleEditor
                  key={key}
                  src={src}
                  width={Number(row.image_width)}
                  height={Number(row.image_height)}
                  polygons={polygons()}
                  instances={JSON.parse(row.obstacle_instances || "[]")}
                  disabled={disabled}
                  onChange={(v) =>
                    change("obstacle_instances", JSON.stringify(v))
                  }
                  controlsContainer={obstacleControls}
                />
              ) : (
                <PolygonEditor
                  key={key}
                  src={src}
                  width={Number(row.image_width)}
                  height={Number(row.image_height)}
                  polygons={polygons()}
                  original={JSON.parse(original?.circulation_path || "[]")}
                  onChange={geometry}
                  disabled={disabled}
                />
              ))}
          </div>
          <nav className="pagination" aria-label="Navegar pelas imagens">
            <button
              disabled={busy || index <= 0}
              onClick={() => move(list[index - 1].key)}
            >
              <ArrowLeft size={15} />
              Anterior
            </button>
            <span>
              {index >= 0 ? index + 1 : 0} / {list.length}
            </span>
            <button
              disabled={busy || !list.length || index >= list.length - 1}
              onClick={() => move(list[index + 1].key)}
            >
              Pular / próxima
              <ArrowRight size={15} />
            </button>
          </nav>
        </section>
        <section className="annotation-fields" aria-label="Atributos e revisão">
          <div className="annotation-savebar">
            <span>
              {row
                ? annotationSchema.fields.filter((f) =>
                    f.kind === "multilabel"
                      ? row[f.name + "_availability"] === "assessed"
                      : !!row[f.name],
                  ).length
                : 0}
              /{annotationSchema.fields.length} campos
            </span>
            {!row ? (
              <span role="status">Carregando imagem…</span>
            ) : !editing ? (
              <button
                disabled={!row || busy}
                className="primary"
                onClick={() => setEditing(true)}
              >
                Editar anotação
              </button>
            ) : (
              <>
                <button
                  disabled={!row || busy}
                  onClick={() => {
                    if (dirty && !confirm("Descartar esta edição?")) return;
                    const restored = original
                      ? structuredClone(original)
                      : newRowV4(
                          key,
                          Number(row?.image_width),
                          Number(row?.image_height),
                        );
                    if (!restored.annotator_id)
                      restored.annotator_id = session.username();
                    setRow(restored);
                    setDirty(false);
                  }}
                >
                  Cancelar
                </button>
                <button disabled={!row || busy} onClick={() => save()}>
                  <Save size={15} />
                  Salvar
                </button>
                <button
                  className="primary"
                  disabled={!row || busy}
                  onClick={() => save(true, false, true)}
                >
                  Finalizar e próxima
                </button>
              </>
            )}
          </div>
          <div className="annotation-tabs" role="tablist" aria-label="Editor de anotação"
            onKeyDown={event => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const next = event.key === "Home" ? "annotation" : event.key === "End" ? "definitions" : tab === "annotation" ? "definitions" : "annotation";
              setTab(next);
              document.getElementById(next + "-tab")?.focus();
            }}>
            <button id="annotation-tab" role="tab" aria-selected={tab === "annotation"} aria-controls="annotation-panel" tabIndex={tab === "annotation" ? 0 : -1} onClick={() => setTab("annotation")}>Anotação</button>
            <button id="definitions-tab" role="tab" aria-selected={tab === "definitions"} aria-controls="definitions-panel" tabIndex={tab === "definitions" ? 0 : -1} onClick={() => setTab("definitions")}>Definições</button>
          </div>
          <div
            id="annotation-panel"
            role="tabpanel"
            hidden={tab !== "annotation"}
            className="annotation-attributes-scroll"
            ref={attributes}
            tabIndex={0}
            aria-label="Painel de atributos"
          >
            {row && (
              <>
                <fieldset className="annotation-group" disabled={disabled}>
                  <legend><sectionIcons.path size={16} aria-hidden="true" />Faixa de circulação</legend>
                  <ChoiceGroup
                    label="Estado da faixa de circulação"
                    value={row.circulation_path_status}
                    options={[
                      { value: "annotated", label: "Identificada" },
                      { value: "absent", label: "Ausente" },
                      { value: "unknown", label: "Desconhecida" },
                    ]}
                    onChange={(value) => {
                      setRow({
                        ...row,
                        circulation_path_status: value,
                        circulation_path:
                          value === "annotated" ? row.circulation_path : "[]",
                      });
                      setDirty(true);
                    }}
                  />
                </fieldset>
                {attributeGroups.filter(g => g.title !== "Revisão").map(renderGroup)}
                <fieldset className="annotation-group" disabled={disabled}>
                  <legend><sectionIcons.context size={16} aria-hidden="true" />Material e contexto</legend>
                  {contextFields.map(field => choices(field.name, field.title, field.options))}
                </fieldset>
                {attributeGroups.filter(g => g.title === "Revisão").map(renderGroup)}
                <details className="annotation-group">
                  <summary>Motivos de informação insuficiente</summary>
                  <fieldset disabled={disabled}>
                    {annotationSchema.fields
                      .filter(
                        (f) =>
                          row[f.name] === "unknown" ||
                          row[f.name + "_availability"] === "unknown",
                      )
                      .map((f) => (
                        <label key={f.name}>
                          {f.display_name}
                          <select
                            value={
                              JSON.parse(row.feature_unknown_reasons || "{}")[
                                f.name
                              ] || ""
                            }
                            onChange={(e) => {
                              const reasons = JSON.parse(
                                row.feature_unknown_reasons || "{}",
                              );
                              if (e.target.value)
                                reasons[f.name] = e.target.value;
                              else delete reasons[f.name];
                              change(
                                "feature_unknown_reasons",
                                JSON.stringify(reasons),
                              );
                            }}
                          >
                            <option value="">Não especificado</option>
                            {annotationSchema.unknown_reason_values.map((v) => (
                              <option key={v} value={v}>
                                {
                                  (
                                    {
                                      occlusion: "Oclusão",
                                      out_of_frame: "Fora do enquadramento",
                                      too_small: "Muito distante / pequeno",
                                      poor_image: "Imagem insuficiente",
                                      ambiguous_context: "Contexto ambíguo",
                                    } as Record<string, string>
                                  )[v]
                                }
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                  </fieldset>
                </details>
                <div className="annotation-group">
                  <label htmlFor="annotation-comment">Comentário</label>
                  <textarea
                    id="annotation-comment"
                    value={row.comment}
                    disabled={disabled}
                    onChange={(e) => change("comment", e.target.value)}
                  />
                </div>
                {coherence(row).map((w) => (
                  <Notice key={w}>{w} Revise antes de salvar.</Notice>
                ))}
                <details className="annotation-group">
                  <summary>Revisão, histórico e proveniência</summary>
                  <p className="caption">
                    {d.manifest[key]?.pilot === "true"
                      ? "Piloto de consistência. "
                      : ""}
                    {d.manifest[key]?.experimental_partition === "holdout"
                      ? "Holdout protegido: não usar sugestões dos modelos, treinamento ou calibração."
                      : "Desenvolvimento — elegibilidade depende de revisão."}
                  </p>
                  <p className="caption">
                    Sinalizações:{" "}
                    {JSON.parse(row.review_flags || "[]").join(", ") ||
                      "nenhuma"}
                    . Origem da máscara:{" "}
                    {original?.circulation_path_origin || "manual"}.
                  </p>
                  <label>
                    Anotador / revisor
                    <input
                      readOnly
                      value={row.annotator_id || session.username()}
                    />
                  </label>
                  <label>
                    Data de captura (somente se verificada)
                    <input
                      disabled={disabled}
                      value={row.captured_at || ""}
                      placeholder="Deixar vazio quando desconhecida"
                      onChange={(e) => change("captured_at", e.target.value)}
                    />
                  </label>
                  <details>
                    <summary>Registro anterior preservado</summary>
                    <pre className="legacy-preview">
                      {JSON.stringify(
                        JSON.parse(row.legacy_annotation || "{}"),
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                  <details>
                    <summary>Referência original do Project Sidewalk</summary>
                    <dl>
                      {[
                        "subset",
                        "original_split",
                        "original_labels",
                        "normalized_x",
                        "normalized_y",
                      ].map((name) => (
                        <div key={name}>
                          <dt>{name}</dt>
                          <dd>{d.manifest[key]?.[name]}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                  <button disabled={disabled} onClick={() => save(false, true)}>
                    <Download size={15} />
                    Exportar edição em CSV
                  </button>
                </details>
                {editing &&
                  d.manifest[key]?.experimental_partition !== "holdout" && (
                    <details className="annotation-group">
                      <summary>Auxílio de segmentação pela API</summary>
                      <label>
                        Origem da observação
                        <input
                          value={source}
                          onChange={(e) => setSource(e.target.value)}
                        />
                      </label>
                      <label>
                        Data da observação
                        <input
                          type="datetime-local"
                          value={date}
                          onChange={(e) => setDate(e.target.value)}
                        />
                      </label>
                      <button disabled={busy} onClick={suggest}>
                        {busy ? <Loading /> : "Gerar sugestão real"}
                      </button>
                      {suggestion && (
                        <button
                          onClick={() => geometry(structuredClone(suggestion))}
                        >
                          Restaurar sugestão
                        </button>
                      )}
                    </details>
                  )}
              </>
            )}
          </div>
          <div id="definitions-panel" role="tabpanel" aria-labelledby="definitions-tab" hidden={tab !== "definitions"} className="annotation-attributes-scroll annotation-definitions" tabIndex={0}>
            <Definitions />
          </div>
        </section>
      </div>
    </div>
  );
}
