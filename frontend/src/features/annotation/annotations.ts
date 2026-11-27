import { validateV4 } from "./v4";
import { data, annotationSchema } from "../../services/data";
import type { Row, Polygons } from "../../types/index";
export { parseCSV } from "../dataset/csv";
import { parseCSV } from "../dataset/csv";
export function serializeCSV(rows: Row[]): string {
  const escape = (value: string) =>
    /[",\n\r]/.test(value) ? '"' + value.replaceAll('"', '""') + '"' : value;
  const base = rows.some((r) => r.schema_version === "4")
    ? annotationSchema.columns
    : data.schema.columns;
  const columns = [
    ...new Set([...base, ...rows.flatMap((r) => Object.keys(r))]),
  ];
  return (
    columns.map(escape).join(",") +
    "\r\n" +
    rows
      .map((row) => columns.map((k) => escape(row[k] ?? "")).join(","))
      .join("\r\n") +
    "\r\n"
  );
}
export function validatePolygons(value: unknown): asserts value is Polygons {
  if (
    !Array.isArray(value) ||
    value.some(
      (p) =>
        !Array.isArray(p) ||
        p.length < 3 ||
        p.some(
          (v) =>
            !Array.isArray(v) ||
            v.length !== 2 ||
            v.some(
              (n) =>
                typeof n !== "number" || !Number.isFinite(n) || n < 0 || n > 1,
            ),
        ),
    )
  )
    throw new Error(
      "Polígonos precisam de três vértices e coordenadas entre 0 e 1.",
    );
}
export function validateRow(row: Row) {
  if (row.schema_version === "4") {
    validateV4(row);
    return;
  }
  if (
    !row.filename ||
    row.filename.startsWith("/") ||
    row.filename.includes("\\") ||
    row.filename.split("/").includes("..") ||
    row.filename.includes(":")
  )
    throw new Error("Filename inválido.");
  if (Object.keys(row).some((k) => !data.schema.columns.includes(k)))
    throw new Error("CSV com campos desconhecidos.");
  for (const f of data.schema.fields) {
    if (f.kind === "multilabel") {
      let selected: unknown;
      try {
        selected = JSON.parse(row[f.name]);
      } catch {
        throw new Error(`JSON inválido: ${f.display_name}.`);
      }
      if (
        !Array.isArray(selected) ||
        new Set(selected).size !== selected.length ||
        selected.some((v) => !f.options.some((o) => o.value === v))
      )
        throw new Error(`Valores inválidos: ${f.display_name}.`);
    } else if (!f.options.some((o) => o.value === row[f.name]))
      throw new Error(`Preencha ${f.display_name}.`);
  }
  const p = JSON.parse(row.circulation_path || "[]");
  validatePolygons(p);
  if (!["annotated", "absent", "unknown"].includes(row.circulation_path_status))
    throw new Error("Informe o estado da faixa de circulação.");
  if ((row.circulation_path_status === "annotated") !== p.length > 0)
    throw new Error(
      "Faixa identificada requer polígono; outros estados requerem geometria vazia.",
    );
  for (const key of ["image_width", "image_height"])
    if (!/^[1-9]\d*$/.test(row[key]))
      throw new Error("Dimensões originais inválidas.");
  if (
    !["manual", "segformer_v1_accepted", "segformer_v1_corrected"].includes(
      row.circulation_path_origin,
    )
  )
    throw new Error("Origem da geometria inválida.");
  if (row.schema_version !== "3" || !row.annotation_timestamp)
    throw new Error("Metadados da anotação inválidos.");
}
export function annotationRows(text: string): Row[] {
  const header = text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/, 1)[0]
    .split(",");
  const spatial = [
    "circulation_path_status",
    "circulation_path",
    "image_width",
    "image_height",
  ];
  const versions = [
    annotationSchema.columns,
    data.schema.columns,
    data.schema.columns.filter((c) => c !== "circulation_path_origin"),
    data.schema.columns.filter(
      (c) => c !== "circulation_path_origin" && !spatial.includes(c),
    ),
  ];
  if (
    !versions.some(
      (columns) => JSON.stringify(columns) === JSON.stringify(header),
    )
  )
    throw new Error("Cabeçalho de anotações incompatível com o schema.");
  const rows = parseCSV(text);
  const filenames = new Set<string>();
  for (const r of rows) {
    if (filenames.has(r.filename))
      throw new Error(`Filename duplicado: ${r.filename}`);
    filenames.add(r.filename);
    if (!["1", "2", "3", "4"].includes(r.schema_version))
      throw new Error("Versão do schema não suportada.");
    if (["3", "4"].includes(r.schema_version)) validateRow(r);
  }
  return rows;
}
export const blankRow = (
  filename: string,
  width: number,
  height: number,
): Row => ({
  filename,
  ...Object.fromEntries(data.schema.fields.map((f) => [f.name, ""])),
  circulation_path_status: "unknown",
  circulation_path: "[]",
  image_width: String(width),
  image_height: String(height),
  circulation_path_origin: "manual",
  comment: "",
  annotation_timestamp: "",
  schema_version: "3",
});
export function coherence(row: Row): string[] {
  const warnings: string[] = [];
  const obstacles = JSON.parse(row.obstacle_type || "[]");
  const problems = JSON.parse(row.surface_obstacle || "[]");
  if (row.obstruction === "none" && obstacles.length)
    warnings.push("Ausência de obstrução com obstáculos selecionados.");
  if (row.path_continuity === "continuous" && row.obstruction === "full")
    warnings.push("Obstrução total com rota contínua.");
  if (row.path_continuity === "continuous" && row.passage_width === "blocked")
    warnings.push("Passagem bloqueada com rota contínua.");
  if (
    row.ramp_condition === "not_applicable" &&
    ["ramp", "raised_no_ramp"].includes(row.curb_access)
  )
    warnings.push("Revise a condição da rampa e o acesso entre calçada e via.");
  if (
    row.surface_condition === "regular" &&
    problems.some((p: string) =>
      [
        "cracks",
        "bumpy",
        "uneven_slanted",
        "very_broken",
        "pooled_water",
        "debris",
      ].includes(p),
    )
  )
    warnings.push("Superfície regular com problemas específicos selecionados.");
  return warnings;
}
export function downloadCSV(rows: Row[]) {
  const url = URL.createObjectURL(
    new Blob([serializeCSV(rows)], { type: "text/csv;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "transitability_annotations.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
