import { describe, it, expect, vi } from "vitest";
import { workspaceApi } from "../src/services/workspace";
import { request } from "../src/services/api";
import {
  migrateLocalProfiles,
  PROFILE_STORAGE_KEY,
  defaultProfiles,
} from "../src/features/demonstration/profiles/profiles";
vi.mock("../src/services/api", () => ({ request: vi.fn() }));
const profile = {
  id: "00000000-0000-4000-8000-000000000001",
  name: "Example",
  requirements: defaultProfiles[0],
};
describe("Persistência Workspace", () => {
  it("normaliza a resposta remota para snapshots compatíveis", async () => {
    vi.mocked(request).mockResolvedValueOnce([
      {
        ...profile,
        created_at: "now",
        requirements: { ...profile.requirements, accepts_detour: null },
      },
    ]);
    expect(await workspaceApi.profiles()).toEqual([profile]);
  });
  it("abre histórico sem chamar inferência e exclui usando autenticação", async () => {
    vi.mocked(request).mockClear().mockResolvedValue({});
    await workspaceApi.detail(profile.id);
    await workspaceApi.deleteAnalysis(profile.id);
    expect(request).toHaveBeenNthCalledWith(
      1,
      "/analyses/" + profile.id,
      {},
      true,
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/analyses/" + profile.id,
      { method: "DELETE" },
      true,
    );
  });
  it("mantém dados locais quando a migração falha; retry preserva os ids", async () => {
    const raw = JSON.stringify({
      version: 1,
      profiles: [
        profile,
        {
          ...profile,
          id: "00000000-0000-4000-8000-000000000002",
          name: "Second",
        },
      ],
    });
    let value: string | null = raw;
    const storage = {
      getItem: () => value,
      removeItem: vi.fn(() => {
        value = null;
      }),
    };
    const save = vi
      .fn()
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error("offline"));
    await expect(migrateLocalProfiles(storage, save)).rejects.toThrow(
      "offline",
    );
    expect(value).toBe(raw);
    expect(storage.removeItem).not.toHaveBeenCalled();
    save.mockResolvedValue({});
    await migrateLocalProfiles(storage, save);
    expect(save.mock.calls[0][0].id).toBe(save.mock.calls[2][0].id);
    expect(storage.removeItem).toHaveBeenCalledWith(PROFILE_STORAGE_KEY);
    expect(value).toBeNull();
  });
  it("não apaga edições de outra aba durante a migração", async () => {
    let raw = JSON.stringify({ version: 1, profiles: [profile] });
    const storage = { getItem: () => raw, removeItem: vi.fn() };
    await expect(
      migrateLocalProfiles(storage, async () => {
        raw = "updated-by-another-tab";
      }),
    ).rejects.toThrow("mudaram");
    expect(storage.removeItem).not.toHaveBeenCalled();
  });
});

it("compartilha requisições simultâneas de perfis sem manter cache desatualizado",async()=>{
 vi.mocked(request).mockClear().mockResolvedValueOnce([]);
 const first=workspaceApi.profiles(),second=workspaceApi.profiles();expect(first).toBe(second);await first;expect(request).toHaveBeenCalledTimes(1);
 vi.mocked(request).mockResolvedValueOnce([profile]);expect(await workspaceApi.profiles()).toEqual([profile]);expect(request).toHaveBeenCalledTimes(2);
});
