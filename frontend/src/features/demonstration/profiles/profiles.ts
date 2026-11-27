import { functionalSpec } from "../../../services/data";
import type { FunctionalProfile, Profile } from "../../../types/index";
export interface SavedProfile {
  id: string;
  name: string;
  requirements: Profile;
  functional?: FunctionalProfile | null;
}
export const PROFILE_STORAGE_KEY = "permear.profiles.v1";
export const defaultProfiles: Profile[] = [
  {
    minimum_passage_width: "adequate",
    surface_tolerance: "minor_problems",
    level_change_tolerance: "minor",
    accepts_partial_obstruction: true,
  },
  {
    minimum_passage_width: "wide",
    surface_tolerance: "regular_only",
    level_change_tolerance: "none",
    accepts_partial_obstruction: false,
  },
];
export const profileChoices = {
  minimum_passage_width: {
    label: "Largura mínima",
    options: { wide: "Ampla", adequate: "Adequada", narrow: "Estreita" },
  },
  surface_tolerance: {
    label: "Tolerância ao piso",
    options: {
      regular_only: "Somente regular",
      minor_problems: "Aceita problemas leves",
      major_problems: "Aceita problemas graves",
    },
  },
  level_change_tolerance: {
    label: "Desnível tolerado",
    options: { none: "Nenhum", minor: "Pequeno", step: "Degrau" },
  },
};
export function validateProfile(profile: SavedProfile): SavedProfile {
  if (
    !profile ||
    typeof profile.id !== "string" ||
    !profile.id ||
    typeof profile.name !== "string" ||
    !profile.name.trim() ||
    profile.name.trim().length > 80
  )
    throw new Error("Informe um nome de até 80 caracteres.");
  const r = profile.requirements;
  if (!r || typeof r.accepts_partial_obstruction !== "boolean")
    throw new Error("Atributos funcionais inválidos.");
  if (
    Object.keys(r).some(
      (key) =>
        !Object.keys(profileChoices).includes(key) &&
        key !== "accepts_partial_obstruction",
    )
  )
    throw new Error("O perfil contém atributos não suportados.");
  for (const [key, definition] of Object.entries(profileChoices))
    if (!Object.hasOwn(definition.options, r[key as keyof Profile] as string))
      throw new Error("Atributos funcionais inválidos.");
  return {
    id: profile.id,
    name: profile.name.trim(),
    ...(profile.functional ? {functional: validateFunctional(profile.functional)} : {}),
    requirements: {
      minimum_passage_width: r.minimum_passage_width,
      surface_tolerance: r.surface_tolerance,
      level_change_tolerance: r.level_change_tolerance,
      accepts_partial_obstruction: r.accepts_partial_obstruction,
    },
  };
}
export function readProfiles(
  storage: Pick<Storage, "getItem">,
): SavedProfile[] {
  const raw = storage.getItem(PROFILE_STORAGE_KEY);
  if (!raw) return [];
  const payload = JSON.parse(raw);
  if (payload.version !== 1 || !Array.isArray(payload.profiles))
    throw new Error("Formato de perfis locais inválido.");
  const profiles = payload.profiles.map(validateProfile);
  if (new Set(profiles.map((p: SavedProfile) => p.id)).size !== profiles.length)
    throw new Error("Perfis locais duplicados.");
  return profiles;
}
export async function migrateLocalProfiles(
  storage: Pick<Storage, "getItem" | "removeItem">,
  save: (profile: SavedProfile) => Promise<unknown>,
) {
  const original = storage.getItem(PROFILE_STORAGE_KEY);
  const profiles = readProfiles(storage);
  for (const profile of profiles) await save(profile);
  if (storage.getItem(PROFILE_STORAGE_KEY) !== original)
    throw new Error(
      "Os perfis locais mudaram durante a migração; foram preservados para revisão.",
    );
  storage.removeItem(PROFILE_STORAGE_KEY);
}

export function validateFunctional(value: unknown): FunctionalProfile {
  if (!value || typeof value !== "object") throw new Error("Complete as respostas funcionais.");
  const a = value as Record<string, unknown>;
  const keys = ["schema_version", "wheelchair_type", "assistance", ...Object.keys(functionalSpec.questions), "requires_ramps", "accepts_detours"];
  if (Object.keys(a).some(k => !keys.includes(k)) || keys.some(k => a[k] === undefined) || a.schema_version !== 1)
    throw new Error("Complete todas as respostas do perfil, sem presumir capacidades.");
  if (!Object.hasOwn(functionalSpec.wheelchair_types, String(a.wheelchair_type)) || !Object.hasOwn(functionalSpec.assistance, String(a.assistance)))
    throw new Error("Informe o tipo de cadeira e a necessidade de assistência.");
  if (Object.keys(functionalSpec.questions).some(k => !Object.hasOwn(functionalSpec.abilities, String(a[k]))) || typeof a.requires_ramps !== "boolean" || typeof a.accepts_detours !== "boolean")
    throw new Error("Respostas funcionais inválidas.");
  if (a.small_level_changes === "unable" && a.steps !== "unable")
    throw new Error("Revise as respostas sobre pequenos desníveis e degraus.");
  return structuredClone(a) as unknown as FunctionalProfile;
}
