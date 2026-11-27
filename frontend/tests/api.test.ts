import { afterEach, describe, it, expect, vi } from "vitest";
import { login, analyze, session } from "../src/services/api";
const saved = new Map<string, string>();
vi.stubGlobal("sessionStorage", {
  getItem: (k: string) => saved.get(k) || null,
  setItem: (k: string, v: string) => saved.set(k, v),
  removeItem: (k: string) => saved.delete(k),
});
const events = new EventTarget();
vi.stubGlobal("window", events);
const profiles = [
  {
    minimum_passage_width: "adequate",
    surface_tolerance: "minor_problems",
    level_change_tolerance: "minor",
    accepts_partial_obstruction: true,
  },
];
afterEach(() => {
  session.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
describe("Cliente do contrato real", () => {
  it("envia os dois perfis em um único multipart e persiste JWT na sessão da aba", async () => {
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        Response.json({ access_token: "unit-test-token", expires_in: 7200 }),
      )
      .mockResolvedValueOnce(Response.json({ features: {} }));
    await login("unit-test-user", "unit-test-password");
    await analyze(
      new File(["x"], "scene.png"),
      [...profiles, ...profiles],
      "test",
      "",
      24,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
    const request = fetcher.mock.calls[1][1]!;
    expect(new Headers(request.headers).get("Authorization")).toBe(
      "Bearer unit-test-token",
    );
    const metadata = JSON.parse(
      (request.body as FormData).get("metadata") as string,
    );
    expect(metadata.profiles).toHaveLength(2);
    expect(metadata.observation.observed_at).toBeNull();
  });
  it("expira a sessão sem enviar uma imagem", async () => {
    vi.useFakeTimers();
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        Response.json({ access_token: "unit-test-token", expires_in: 1 }),
      );
    await login("unit", "unit");
    vi.advanceTimersByTime(1001);
    await expect(
      analyze(new File([""], "a.png"), profiles, "test", "", 24),
    ).rejects.toMatchObject({ status: 401 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("invalida o token em 401 e informa limites de requisição", async () => {
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        Response.json({ access_token: "test", expires_in: 7200 }),
      )
      .mockResolvedValueOnce(new Response("", { status: 401 }));
    await login("unit", "unit");
    await expect(
      analyze(new File([""], "a.png"), profiles, "test", "", 24),
    ).rejects.toMatchObject({ status: 401 });
    expect(session.expires()).toBe(0);
    fetcher.mockResolvedValueOnce(
      new Response("", { status: 429, headers: { "Retry-After": "60" } }),
    );
    await expect(login("unit", "unit")).rejects.toMatchObject({
      status: 429,
      retryAfter: "60",
    });
  });
});

describe("Sessão por aba", () => {
  it("restaura a sessão sem estender a validade original", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ access_token: "test", expires_in: 7200 }),
    );
    await login("actual-demo-user", "test");
    const expiration = session.expires();
    expect(session.restore()).toBe(true);
    expect(session.expires()).toBe(expiration);
    expect(session.username()).toBe("actual-demo-user");
    session.clear();
    expect(session.restore()).toBe(false);
    expect(saved.size).toBe(0);
  });
  it("não restaura dados inválidos nem expirados", () => {
    saved.set("permear.session.v1", "{");
    expect(session.restore()).toBe(false);
    saved.set(
      "permear.session.v1",
      JSON.stringify({ token: "expired", expiresAt: 1, username: "user" }),
    );
    expect(session.restore()).toBe(false);
  });
});

it("respeita o exp original do JWT mesmo que o armazenamento seja alterado", () => {
  const payload = btoa(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 10 }),
  );
  saved.set(
    "permear.session.v1",
    JSON.stringify({
      token: "header." + payload + ".signature",
      username: "user",
      expiresAt: Date.now() + 100000,
    }),
  );
  expect(session.restore()).toBe(false);
  expect(saved.size).toBe(0);
});


it("envia respostas funcionais completas para a tradução no backend", async () => {
 const functional={schema_version:1 as const,wheelchair_type:"manual" as const,assistance:"partial" as const,narrow_spaces:"without_difficulty" as const,uneven_surfaces:"with_difficulty" as const,small_level_changes:"with_difficulty" as const,steps:"unable" as const,tight_maneuvers:"with_difficulty" as const,obstacle_avoidance:"without_difficulty" as const,requires_ramps:true,inclines:"unable" as const,accepts_detours:true};
 const fetcher=vi.spyOn(globalThis,"fetch").mockResolvedValueOnce(Response.json({access_token:"unit-token",expires_in:7200})).mockResolvedValueOnce(Response.json({features:{}}));
 await login("unit","unit");await analyze(new File(["x"],"scene.png"),[{functional},{functional:{...functional,small_level_changes:"unable"}}],"simulated test","",24);
 const payload=JSON.parse((fetcher.mock.calls[1][1]!.body as FormData).get("metadata") as string);
 expect(payload.profiles[0]).toEqual({functional});expect(payload.profiles[1].functional.small_level_changes).toBe("unable");expect(payload.profiles[0]).not.toHaveProperty("minimum_passage_width");
});
