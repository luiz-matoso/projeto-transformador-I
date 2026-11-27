import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import {
  annotationRows,
  parseCSV,
  serializeCSV,
  validatePolygons,
  validateRow,
  coherence,
} from "../src/features/annotation/annotations";
import { imageKey, fileImages } from "../src/features/dataset/files";
const original = readFileSync(
  new URL("../../annotations/transitability_annotations.csv", import.meta.url),
  "utf8",
);
describe("Compatibilidade de anotações", () => {
  it("faz round-trip de todas as 200 anotações reais sem alterar valores", () => {
    const rows = annotationRows(original);
    expect(rows).toHaveLength(200);
    expect(annotationRows(serializeCSV(rows))).toEqual(rows);
  });
  it("preserva aspas, vírgulas e comentários multilinha", () => {
    const row = {
      ...annotationRows(original)[0],
      comment: 'Piso, "irregular"\nsegunda linha',
    };
    expect(annotationRows(serializeCSV([row]))[0]).toEqual(row);
  });
  it("rejeita duplicatas e categorias não existentes", () => {
    const row = annotationRows(original)[0];
    expect(() => annotationRows(serializeCSV([row, row]))).toThrow("duplicado");
    expect(() =>
      validateRow({ ...row, passage_width: "inexistente" }),
    ).toThrow();
  });
  it("distingue multilabel não preenchida de nenhum relevante explícito", () => {
    const row = annotationRows(original)[0];
    expect(() => validateRow({ ...row, obstacle_type: "" })).toThrow();
    expect(() => validateRow({ ...row, obstacle_type: "[]" })).not.toThrow();
  });
  it("valida geometria, estados e nomes relativos seguros", () => {
    expect(() =>
      validatePolygons([
        [
          [0, 0],
          [1, 0],
          [0, 1],
        ],
      ]),
    ).not.toThrow();
    for (const polygon of [
      [
        [
          [2, 0],
          [0, 0],
          [1, 1],
        ],
      ],
      [
        [
          [0, 0],
          [1, 1],
        ],
      ],
      [
        [
          [NaN, 0],
          [1, 0],
          [0, 1],
        ],
      ],
    ])
      expect(() => validatePolygons(polygon)).toThrow();
    const row = annotationRows(original)[0];
    expect(() => validateRow({ ...row, filename: "../outside.png" })).toThrow();
    expect(() =>
      validateRow({ ...row, circulation_path_status: "absent" }),
    ).toThrow();
  });
  it("identifica CSV truncado e mantém referência por subset", () => {
    expect(() => parseCSV('a,b\n"unfinished')).toThrow();
    expect(() => annotationRows("wrong,header\n")).toThrow();
    expect(() => annotationRows("unrelated,header\n")).toThrow();
    expect(imageKey("data/annotation-pilot/images/curb_ramp/file.png")).toBe(
      "curb_ramp/file.png",
    );
    expect(() =>
      fileImages([new File([""], "same.png"), new File([""], "same.png")]),
    ).toThrow();
  });
  it("mantém advertências de coerência revisáveis", () => {
    const row = {
      ...annotationRows(original)[0],
      obstruction: "full",
      path_continuity: "continuous",
    };
    expect(coherence(row).length).toBeGreaterThan(0);
    expect(() => validateRow(row)).not.toThrow();
  });
});
