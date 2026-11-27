export type MobilityAbility = "without_difficulty" | "with_difficulty" | "unable";
export interface FunctionalProfile {
  schema_version: 1;
  wheelchair_type: "manual" | "powered";
  assistance: "none" | "partial" | "constant";
  narrow_spaces: MobilityAbility;
  uneven_surfaces: MobilityAbility;
  small_level_changes: MobilityAbility;
  steps: MobilityAbility;
  tight_maneuvers: MobilityAbility;
  obstacle_avoidance: MobilityAbility;
  requires_ramps: boolean;
  inclines: MobilityAbility;
  accepts_detours: boolean;
}
export type Point = [number, number];
export type Polygons = Point[][];
export type Row = Record<string, string>;
export interface Profile {
  minimum_passage_width: string;
  surface_tolerance: string;
  level_change_tolerance: string;
  accepts_partial_obstruction: boolean;
}
export interface Reason {
  feature: string;
  observed: unknown;
  requirement: unknown;
  impact: string;
  code: string;
  message: string;
  evaluated: boolean;
}
export interface Assessment {
  functional?: FunctionalProfile | null;
  unassessed_functional_needs?: string[] | null;
  translation_notes?: string[] | null;
  profile_index: number;
  classification: string;
  severity: string;
  reasons: Reason[];
  requires_review: boolean;
  unassessed_features: string[];
}
export interface Result {
  mask: { data: string; width: number; height: number } | null;
  features: Record<string, string | string[]>;
  predictions: Record<
    string,
    {
      confidence?: number;
      probabilities: Record<string, number>;
      thresholds?: Record<string, number>;
    }
  >;
  observation: {
    source: string;
    observed_at: string | null;
    evaluated_at: string;
    expires_at: string | null;
    is_valid: boolean;
    message: string;
    code: string;
    validity_seconds: number;
  };
  assessments: Assessment[];
  not_modeled: Record<
    string,
    Record<string, { positive_train: number; reason: string }>
  >;
  inactive_features: string[];
}
export interface Field {
  name: string;
  display_name: string;
  kind: string;
  required: boolean;
  description: string;
  empty_means: string | null;
  options: { value: string; definition: string }[];
}
export interface Metrics {
  foreground_iou?: number;
  dice?: number;
  precision?: number;
  recall?: number;
  aggregate_macro_f1?: number;
  heads?: Record<string, { macro_f1: number; micro_f1?: number }>;
}
export interface Experiment {
  name: string;
  family: string;
  directory: string;
  split: number[];
  metrics: Metrics;
  config: Record<string, unknown>;
  history: Record<string, string>[];
}
