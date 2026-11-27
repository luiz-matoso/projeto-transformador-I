import { describe, it, expect } from "vitest";
import {
  PROFILE_STORAGE_KEY,
  defaultProfiles,
  migrateLocalProfiles,
  readProfiles,
  validateProfile,
  type SavedProfile,
} from "../src/features/demonstration/profiles/profiles";
const first: SavedProfile = {
  id: "profile-1",
  name: "Piso tolerante",
  requirements: defaultProfiles[0],
};
function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
}
function seed(local:Pick<Storage,"setItem">,profiles:SavedProfile[]) {
 local.setItem(PROFILE_STORAGE_KEY,JSON.stringify({version:1,profiles}));
}
describe("Leitura e migração de perfis legados", () => {
  it("inicia sem inventar perfis cadastrados", () =>
    expect(readProfiles(storage())).toEqual([]));
  it("lê nome e somente os quatro requisitos legados suportados", () => {
    const local = storage();
    seed(local, [first]);
    expect(readProfiles(local)).toEqual([first]);
    expect(Object.keys(readProfiles(local)[0].requirements)).toHaveLength(4);
    expect(local.getItem(PROFILE_STORAGE_KEY)).not.toContain("access_token");
  });
  it("mantém edição e exclusão após nova leitura", () => {
    const local = storage();
    seed(local, [
      first,
      {
        id: "profile-2",
        name: "Outro perfil",
        requirements: defaultProfiles[1],
      },
    ]);
    const edited = readProfiles(local).map((p) =>
      p.id === first.id ? { ...p, name: "Nome editado" } : p,
    );
    seed(local, edited);
    expect(readProfiles(local)[0].name).toBe("Nome editado");
    seed(
      local,
      edited.filter((p) => p.id !== first.id),
    );
    expect(readProfiles(local)).toHaveLength(1);
  });
  it("rejeita nomes vazios, atributos estranhos e valores não suportados", () => {
    expect(() => validateProfile({ ...first, name: "  " })).toThrow();
    expect(() =>
      validateProfile({
        ...first,
        requirements: { ...first.requirements, minimum_passage_width: "90cm" },
      }),
    ).toThrow();
    expect(() =>
      validateProfile({
        ...first,
        requirements: { ...first.requirements, slope: "unknown" } as never,
      }),
    ).toThrow();
  });
  it("não aceita dados corrompidos ou IDs duplicados", () => {
    const local = storage();
    local.setItem(PROFILE_STORAGE_KEY, "not-json");
    expect(() => readProfiles(local)).toThrow();
    local.setItem(
      PROFILE_STORAGE_KEY,
      JSON.stringify({ version: 1, profiles: [first, first] }),
    );
    expect(() => readProfiles(local)).toThrow();
  });
  it("não oculta falha ao remover dados legados após a migração", async () => {
    const local=storage();seed(local,[first]);
    await expect(migrateLocalProfiles({...local,removeItem(){throw new Error("Quota");}},async()=>{})).rejects.toThrow("Quota");
    expect(readProfiles(local)).toEqual([first]);
  });
});
