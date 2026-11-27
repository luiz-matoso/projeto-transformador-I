import type { FunctionalProfile, Profile, Result } from "../types/index";
export const API_URL = import.meta.env.DEV
  ? import.meta.env.BASE_URL + "api"
  : (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(
      /\/$/,
      "",
    );
let accessToken: string | null = null;
let expiresAt = 0;
let username = "";
export const SESSION_KEY = "permear.session.v1";
function tokenExpiration(token: string): number {
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    return typeof payload.exp === "number" ? payload.exp * 1000 : Infinity;
  } catch {
    return Infinity;
  }
}
export const session = {
  restore() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
      if (
        saved &&
        typeof saved.token === "string" &&
        typeof saved.username === "string" &&
        Number.isFinite(saved.expiresAt) &&
        saved.expiresAt > Date.now()
      ) {
        accessToken = saved.token;
        expiresAt = Math.min(saved.expiresAt, tokenExpiration(saved.token));
        if (expiresAt <= Date.now()) {
          this.clear();
          return false;
        }
        username = saved.username;
        return true;
      }
    } catch {}
    this.clear();
    return false;
  },
  username() {
    return username;
  },
  clear() {
    accessToken = null;
    expiresAt = 0;
    username = "";
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {}
  },
  expires() {
    return expiresAt;
  },
};
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
    public retryAfter: string | null = null,
  ) {
    super(message);
  }
}
export async function request(
  path: string,
  init: RequestInit = {},
  protectedRoute = false,
) {
  if (protectedRoute && (!accessToken || Date.now() >= expiresAt)) {
    session.clear();
    window.dispatchEvent(new Event("session-expired"));
    throw new ApiError("Sua sessão expirou. Entre novamente.", 401);
  }
  const headers = new Headers(init.headers);
  if (protectedRoute) headers.set("Authorization", `Bearer ${accessToken}`);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300_000);
  try {
    const response = await fetch(API_URL + path, {
      ...init,
      headers,
      signal: controller.signal,
      credentials: "omit",
      cache: "no-store",
    });
    if (!response.ok) {
      if (response.status === 401 && protectedRoute) {
        session.clear();
        window.dispatchEvent(new Event("session-expired"));
      }
      const messages: Record<number, string> = {
        401: protectedRoute
          ? "Sessão inválida ou expirada. Entre novamente."
          : "Usuário ou senha inválidos.",
        404: "Registro não encontrado.",
        409: "O registro já existe ou foi alterado. Revise os dados.",
        413: "A imagem excede os limites permitidos.",
        415: "Formato de imagem não aceito.",
        422: "Verifique a imagem e os dados informados.",
        429: "Limite de requisições atingido. Aguarde antes de tentar novamente.",
        503: "Serviço indisponível. Tente novamente.",
      };
      throw new ApiError(
        messages[response.status] ||
          `Falha na requisição (HTTP ${response.status}).`,
        response.status,
        response.headers.get("Retry-After"),
      );
    }
    return response.status === 204 ? null : await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      error instanceof Error && error.name === "AbortError"
        ? "O tempo de espera terminou. Tente novamente."
        : "Não foi possível acessar a API. Verifique a conexão, a URL e o CORS.",
    );
  } finally {
    clearTimeout(timeout);
  }
}
export async function login(user: string, password: string) {
  const response = await request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: user, password }),
  });
  accessToken = response.access_token;
  expiresAt = Math.min(
    Date.now() + response.expires_in * 1000,
    tokenExpiration(accessToken!),
  );
  username = user;
  try {
    sessionStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ token: accessToken, expiresAt, username }),
    );
  } catch {
    session.clear();
    throw new ApiError("Permita o armazenamento da sessão nesta aba.");
  }
}
export async function analyze(
  image: File,
  profiles: (Profile | {functional:FunctionalProfile})[],
  source: string,
  observedAt: string,
  validity: number,
): Promise<Result> {
  const form = new FormData();
  form.set("image", image);
  form.set(
    "metadata",
    JSON.stringify({
      profiles,
      observation: {
        source,
        observed_at: observedAt ? new Date(observedAt).toISOString() : null,
      },
      validity_hours: validity,
    }),
  );
  return request("/transitability", { method: "POST", body: form }, true);
}
