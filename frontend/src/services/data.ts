import snapshot from "../generated/workspace.json";
import type { Field, Experiment, Metrics } from "../types/index";
export const data = snapshot as unknown as {
  functional_profile: {
    version: number; questions: Record<string,string>; abilities: Record<string,string>;
    wheelchair_types: Record<string,string>; assistance: Record<string,string>;
    complementary: string[]; notes: string[]; mapping: Record<string,unknown>;
  };
  annotation_v4: {
    version: number;
    columns: string[];
    fields: Field[];
    groups: [string, string[]][];
    surface_material_values: string[];
    route_scope_values: string[];
    unknown_reason_values: string[];
  };
  schema: {
    version: number;
    columns: string[];
    fields: Field[];
    labels: Record<string, Record<string, string>>;
    groups: [string, string[]][];
  };
  legacy: Record<string, string>[];
  dataset: {
    total: number;
    statuses: Record<string, number>;
    subsets: Record<string, number>;
    distributions: Record<string, Record<string, number>>;
  };
  experiments: Experiment[];
  pipeline: {
    metrics: { human: Metrics; predicted: Metrics };
    aggregate_delta: number;
    correct_to_wrong: number;
    wrong_to_correct: number;
    sample_count: number;
  };
  comparison: { v1_common: Metrics };
  sources: Record<string, string>;
};
export const label = (field: string, value: string) =>
  data.schema.labels[field]?.[value] ?? value;
export const fieldName = (field: string) =>
  data.schema.fields.find((f) => f.name === field)?.display_name ?? field;
export const classes: Record<string, string> = {
  transitable: "Transitável",
  partially_transitable: "Parcialmente transitável",
  non_transitable: "Não transitável",
  undetermined: "Indeterminado",
};
export const number = (value: number | undefined) =>
  value === undefined
    ? "—"
    : value.toLocaleString("pt-BR", {
        minimumFractionDigits: 4,
        maximumFractionDigits: 4,
      });

export const annotationSchema = data.annotation_v4;

export const functionalSpec = data.functional_profile;
