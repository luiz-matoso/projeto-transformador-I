import { annotationSchema, data } from "../../services/data";
import type { Row } from "../../types/index";
import { validatePolygons } from "./annotations";
export type ObstacleInstance = {
  id: string;
  type: string;
  bbox: [number, number, number, number];
  path_relation: string;
};
export const statusLabel = (row?: Row) =>
  ({
    pending_review: "Pendente de revisão",
    pending_annotation: "Pendente de anotação",
    finalized: "Finalizada",
  })[row?.workflow_status || "pending_annotation"] || "Pendente de revisão";
export const matchesStatus = (row: Row | undefined, filter: string) =>
  filter === "all" ||
  (filter === "pending"
    ? row?.workflow_status !== "finalized"
    : filter === "low"
      ? row?.annotation_confidence === "low"
      : filter === "annotated"
        ? row?.workflow_status === "finalized"
        : row?.workflow_status === filter);
export function migrateV4(row: Row): Row {
  if (row.schema_version === "4") return structuredClone(row);
  const flags = ["legacy_protocol_review"];
  const signs = JSON.parse(row.surface_obstacle || "[]") as string[];
  if (signs.some((v) => ["debris", "brick_cobblestone"].includes(v)))
    flags.push("surface_semantics_changed");
  if (row.circulation_path_origin !== "manual")
    flags.push("model_assisted_mask");
  return {
    ...row,
    ...Object.fromEntries(
      annotationSchema.columns
        .filter((k) => !data.schema.columns.includes(k))
        .map((k) => [k, ""]),
    ),
    schema_version: "4",
    obstacle_instances: "[]",
    instances_availability: "unknown",
    obstacle_type_availability: "unknown",
    surface_obstacle_availability: "unknown",
    surface_material: "unknown",
    route_scope: "unknown",
    feature_unknown_reasons: "{}",
    workflow_status: "pending_review",
    review_flags: JSON.stringify(flags),
    review_acknowledged: "false",
    protocol_version: "4.0",
    source_metadata: "{}",
    legacy_annotation: JSON.stringify(row),
    surface_obstacle: JSON.stringify(
      signs.filter((v) => !["debris", "brick_cobblestone"].includes(v)),
    ),
  };
}
export function newRowV4(filename: string, width: number, height: number): Row {
  return {
    ...Object.fromEntries(annotationSchema.columns.map((k) => [k, ""])),
    filename,
    image_width: String(width),
    image_height: String(height),
    schema_version: "4",
    circulation_path: "[]",
    circulation_path_status: "unknown",
    circulation_path_origin: "manual",
    obstacle_type: "[]",
    surface_obstacle: "[]",
    obstacle_instances: "[]",
    instances_availability: "unknown",
    obstacle_type_availability: "unknown",
    surface_obstacle_availability: "unknown",
    surface_material: "unknown",
    route_scope: "unknown",
    feature_unknown_reasons: "{}",
    workflow_status: "pending_annotation",
    review_flags: "[]",
    review_acknowledged: "false",
    protocol_version: "4.0",
    source_metadata: "{}",
    legacy_annotation: "{}",
  };
}
export function validateV4(row: Row) {
  if (
    !row.filename ||
    row.filename.startsWith("/") ||
    row.filename.includes("\\") ||
    row.filename.includes(":") ||
    row.filename.split("/").includes("..")
  )
    throw Error("Filename inválido.");
  const final = row.workflow_status === "finalized";
  if (
    !["pending_review", "pending_annotation", "finalized"].includes(
      row.workflow_status,
    )
  )
    throw Error("Estado de trabalho inválido.");
  for (const field of annotationSchema.fields) {
    const value = row[field.name];
    if (field.kind === "multilabel") {
      const items = JSON.parse(value || "[]");
      if (
        !Array.isArray(items) ||
        new Set(items).size !== items.length ||
        items.some((v) => !field.options.some((o) => o.value === v))
      )
        throw Error(`Valores inválidos: ${field.display_name}`);
    } else if (
      (value || final) &&
      !field.options.some((o) => o.value === value)
    )
      throw Error(`Preencha ${field.display_name}.`);
  }
  const polygons = JSON.parse(row.circulation_path || "[]");
  validatePolygons(polygons);
  if (
    !["annotated", "absent", "unknown"].includes(row.circulation_path_status) ||
    (row.circulation_path_status === "annotated") !== !!polygons.length
  )
    throw Error("Estado da faixa incompatível com a geometria.");
  for (const key of ["image_width", "image_height"])
    if (!/^[1-9]\d*$/.test(row[key])) throw Error("Dimensões inválidas.");
  for (const key of [
    "instances_availability",
    "obstacle_type_availability",
    "surface_obstacle_availability",
  ])
    if (!["assessed", "unknown"].includes(row[key]))
      throw Error("Informe a disponibilidade das listas.");
  const boxes = JSON.parse(row.obstacle_instances || "[]");
  if (!Array.isArray(boxes)) throw Error("Instâncias inválidas.");
  const ids = new Set();
  for (const item of boxes) {
    const box = item.bbox;
    if (
      !item.id ||
      ids.has(item.id) ||
      Object.keys(item).sort().join(",") !== "bbox,id,path_relation,type" ||
      !annotationSchema.fields
        .find((f) => f.name === "obstacle_type")!
        .options.some((o) => o.value === item.type) ||
      !["outside", "encroaching", "on_path", "unknown"].includes(
        item.path_relation,
      ) ||
      !Array.isArray(box) ||
      box.length !== 4 ||
      box.some(
        (v: unknown) =>
          typeof v !== "number" || !Number.isFinite(v) || v < 0 || v > 1,
      ) ||
      box[0] >= box[2] ||
      box[1] >= box[3]
    )
      throw Error("Caixa, tipo ou relação de obstáculo inválida.");
    ids.add(item.id);
  }
  for (const key of [
    "source_metadata",
    "legacy_annotation",
    "feature_unknown_reasons",
  ]) {
    const v = JSON.parse(row[key] || "{}");
    if (!v || typeof v !== "object" || Array.isArray(v))
      throw Error(`Metadado inválido: ${key}`);
  }
  if (!Array.isArray(JSON.parse(row.review_flags || "[]")))
    throw Error("Sinalizações inválidas.");
  const reasons = JSON.parse(row.feature_unknown_reasons || "{}");
  if (
    Object.entries(reasons).some(
      ([k, v]) =>
        !annotationSchema.fields.some((f) => f.name === k) ||
        !annotationSchema.unknown_reason_values.includes(v as string),
    )
  )
    throw Error("Motivo de informação insuficiente inválido.");
  if (
    !["manual", "segformer_v1_accepted", "segformer_v1_corrected"].includes(
      row.circulation_path_origin,
    ) ||
    !["true", "false"].includes(row.review_acknowledged)
  )
    throw Error("Metadados de revisão inválidos.");
  if (
    !annotationSchema.surface_material_values.includes(row.surface_material) ||
    !annotationSchema.route_scope_values.includes(row.route_scope)
  )
    throw Error("Material ou contexto inválido.");
  if (
    final &&
    (!row.annotator_id?.trim() ||
      row.review_acknowledged !== "true" ||
      !row.reviewed_at)
  )
    throw Error("Para finalizar, informe o anotador e confirme a revisão.");
}
