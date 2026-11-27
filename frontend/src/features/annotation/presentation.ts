import { ArrowUpDown, Box, ClipboardCheck, Layers, MoveHorizontal, Route, Map } from "lucide-react";
import { annotationSchema } from "../../services/data";

export type Tone = "plain" | "favorable" | "caution" | "critical" | "unknown";
const tones: Record<string, Record<string, Tone>> = {
  passage_width: { wide: "favorable", adequate: "favorable", narrow: "caution", very_narrow: "critical", blocked: "critical" },
  obstruction: { none: "favorable", partial: "caution", full: "critical" },
  surface_condition: { regular: "favorable", minor_problem: "caution", major_problem: "critical" },
  level_change: { none: "favorable", minor: "caution", step: "critical" },
  path_continuity: { continuous: "favorable", restricted: "caution", interrupted: "critical" },
  ramp_condition: { clear: "favorable", problematic: "caution", blocked: "critical", missing_required: "critical" },
  curb_access: { level: "favorable", ramp: "favorable", raised_no_ramp: "critical", blocked: "critical" },
  slope: { flat_gentle: "favorable", inclined: "caution", steep: "critical" },
  detour: { not_needed: "favorable", available: "caution", unavailable: "critical" },
  annotation_confidence: { high: "favorable", medium: "caution", low: "caution" },
};
export function optionTone(field: string, value: string): Tone {
  if (value === "unknown" || value === "not_applicable") return "unknown";
  return tones[field]?.[value] ?? "plain";
}
// Presentation only: source fields, options and stored values remain the v4 schema.
const groups = [
  ["PASSAGEM", "Passagem", MoveHorizontal],
  ["SUPERFÍCIE", "Superfície", Layers],
  ["OBJETOS", "Obstáculos", Box],
  ["TRANSIÇÕES E CONTEXTO", "Transições", ArrowUpDown],
  ["REVISÃO", "Revisão", ClipboardCheck],
] as const;
export const attributeGroups = groups.map(([source, title, icon]) => ({
  title, icon, names: annotationSchema.groups.find(([name]) => name === source)![1],
}));
export const sectionIcons = { path: Route, context: Map, review: ClipboardCheck };
export const contextFields = [
  { name: "surface_material", title: "Material aparente do piso", options: [
    { value: "unknown", label: "Desconhecido", definition: "O material não pode ser identificado com segurança." },
    { value: "hard_surface", label: "Superfície rígida", definition: "Pavimento rígido aparente, como concreto ou asfalto." },
    { value: "brick_cobblestone", label: "Blocos / paralelepípedos", definition: "Piso de blocos, tijolos ou paralelepípedos." },
    { value: "loose_surface", label: "Superfície solta", definition: "Material solto, como terra, areia ou cascalho." },
    { value: "vegetated_surface", label: "Superfície vegetada", definition: "Superfície predominantemente coberta por vegetação." },
    { value: "mixed", label: "Misto", definition: "Mais de um material relevante no trecho." },
    { value: "other", label: "Outro", definition: "Material não contemplado pelas demais opções." },
  ] },
  { name: "route_scope", title: "Contexto do percurso", options: [
    { value: "unknown", label: "Desconhecido", definition: "Não é possível identificar o contexto do percurso." },
    { value: "sidewalk_segment", label: "Segmento de calçada", definition: "Trecho de circulação ao longo da calçada." },
    { value: "crossing_transition", label: "Transição / travessia", definition: "Transição entre calçada e via ou área de travessia." },
  ] },
  { name: "instances_availability", title: "Levantamento de instâncias", options: [
    { value: "unknown", label: "Não avaliado / desconhecido", definition: "A lista de objetos não foi confirmada como avaliada; não implica ausência." },
    { value: "assessed", label: "Avaliado", definition: "O levantamento das instâncias foi revisado explicitamente." },
  ] },
];
