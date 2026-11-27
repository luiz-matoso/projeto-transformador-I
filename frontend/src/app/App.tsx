import { useEffect, useState } from "react";
import {
  House,
  Database,
  PenLine,
  SlidersHorizontal,
  ScanLine,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { session } from "../services/api";
import { DatasetProvider } from "../features/dataset/LocalDataset";
import { DatasetPage } from "../features/dataset/DatasetPage";
import { AnnotationPage } from "../features/annotation/AnnotationPage";
import {
  DemoPage,
  type PendingAnalysis,
} from "../features/demonstration/DemoPage";
import { HomePage } from "../features/home/HomePage";
import { Login } from "../features/auth/Login";
import { ProfilesPage } from "../features/demonstration/profiles/ProfilesPage";
import { ProfilesProvider } from "../features/demonstration/profiles/useProfiles";
const base = import.meta.env.BASE_URL.replace(/\/$/, "");
const canonicalRoute = (route: string) =>
  ({ perfis: "demonstracao/perfis", demonstracao: "demonstracao/analisar" } as Record<string, string>)[route] ?? route;
const path = () => canonicalRoute(
  location.pathname.slice(base.length).replace(/^\/|\/$/g, "") || "overview",
);
const navigation = [
  { key: "overview", label: "Início", icon: House },
  { key: "dataset", label: "Dataset", icon: Database },
  { key: "anotacao", label: "Anotação", icon: PenLine },
  { key: "demonstracao/perfis", label: "Perfis", icon: SlidersHorizontal },
  { key: "demonstracao/analisar", label: "Analisar trecho", icon: ScanLine },
];
export function App() {
  const [logged, setLogged] = useState(() => session.restore()),
    [route, setRoute] = useState(path),
    [initialKey, setInitialKey] = useState<string | null>(null),
    [dirty, setDirty] = useState(false),
    [pending, setPending] = useState<PendingAnalysis | null>(null),
    [expired, setExpired] = useState(false),
    [mobile, setMobile] = useState(false);
  useEffect(() => {
    const current = path();
    if (["perfis", "demonstracao"].includes(location.pathname.slice(base.length).replace(/^\/|\/$/g, "")))
      history.replaceState({}, "", base + "/" + current);
  }, []);
  useEffect(() => {
    const expire = () => {
      session.clear();
      setLogged(false);
      setExpired(true);
    };
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, []);
  useEffect(() => {
    if (!logged) return;
    const timer = setTimeout(
      () => window.dispatchEvent(new Event("session-expired")),
      Math.max(0, session.expires() - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [logged]);
  useEffect(() => {
    const pop = () => {
      if (dirty && !confirm("Descartar alterações não salvas?")) {
        history.pushState(
          {},
          "",
          base + "/" + (route === "overview" ? "" : route),
        );
        return;
      }
      setDirty(false);
      setPending(null);
      setRoute(path());
    };
    const unload = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("popstate", pop);
    window.addEventListener("beforeunload", unload);
    return () => {
      window.removeEventListener("popstate", pop);
      window.removeEventListener("beforeunload", unload);
    };
  }, [dirty, route]);
  function navigate(page: string, key?: string) {
    page = canonicalRoute(page);
    if (page === route && !key) return;
    if (dirty && !confirm("Descartar alterações não salvas?")) return;
    setDirty(false);
    setPending(null);
    setInitialKey(key ?? null);
    setRoute(page);
    history.pushState({}, "", base + "/" + (page === "overview" ? "" : page));
    setMobile(false);
    window.scrollTo(0, 0);
  }
  if (!logged)
    return (
      <Login
        expired={expired}
        onLogin={() => {
          if (pending && pending.owner !== session.username()) setPending(null);
          setLogged(true);
          setExpired(false);
          if (route === "login") navigate("overview");
        }}
      />
    );
  return (
    <ProfilesProvider>
      <DatasetProvider>
        <div className="workspace">
          <a className="skip-link" href="#main-content">
            Ir para conteúdo
          </a>
          {mobile && (
            <button
              className="nav-scrim"
              aria-label="Fechar navegação"
              onClick={() => setMobile(false)}
            />
          )}
          <aside className={"sidebar " + (mobile ? "open" : "")}>
            <a
              className="brand"
              href={base + "/"}
              onClick={(e) => {
                e.preventDefault();
                navigate("overview");
              }}
            >
              Permear Workspace
            </a>
            <nav aria-label="Navegação principal">
              {navigation.map((item) => (
                <div key={item.key}>
                  {item.key === "demonstracao/perfis" && (
                    <div className="nav-group">
                      <ScanLine size={17} />
                      Demonstração
                    </div>
                  )}
                  <a
                    className={
                      (route === item.key ? "active " : "") +
                      (item.key.startsWith("demonstracao/") ? "nav-child" : "")
                    }
                    aria-current={route === item.key ? "page" : undefined}
                    href={
                      base + "/" + (item.key === "overview" ? "" : item.key)
                    }
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(item.key);
                    }}
                  >
                    <item.icon size={17} />
                    {item.label}
                  </a>
                </div>
              ))}
            </nav>
            <footer className="sidebar-footer">
              <a
                href="https://github.com/luiz-matoso/projeto-transformador-I"
                target="_blank"
                rel="noreferrer"
              >
                <svg
                  width="17"
                  height="17"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                  fill="currentColor"
                >
                  <path d="M12 .7a11.3 11.3 0 0 0-3.6 22c.6.1.8-.2.8-.5v-2.1c-3.3.7-4-1.4-4-1.4-.5-1.3-1.3-1.6-1.3-1.6-1.1-.8.1-.8.1-.8 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-6a4.7 4.7 0 0 1 1.3-3.2c-.2-.3-.6-1.6.1-3.2 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.7 4.2 18.7 4.5 18.7 4.5c.7 1.6.3 2.9.1 3.2a4.7 4.7 0 0 1 1.3 3.2c0 4.7-2.8 5.7-5.5 6 .4.4.8 1.1.8 2.2v3.1c0 .3.2.6.8.5A11.3 11.3 0 0 0 12 .7Z" />
                </svg>
                GitHub do Projeto
              </a>
              <span>Usuário: {session.username()}</span>
              <button
                className="logout-button"
                onClick={() => {
                  if (
                    dirty &&
                    !confirm("Sair e descartar alterações não salvas?")
                  )
                    return;
                  session.clear();
                  setPending(null);
                  setDirty(false);
                  setLogged(false);
                }}
              >
                <LogOut size={17} />
                Sair
              </button>
            </footer>
          </aside>
          <div
            className={
              "workspace-body" +
              (route === "anotacao" ? " annotation-route" : "")
            }
          >
            <div className="mobile-topbar">
              <button
                className="icon-button"
                aria-label={mobile ? "Fechar navegação" : "Abrir navegação"}
                onClick={() => setMobile(!mobile)}
              >
                {mobile ? <X size={19} /> : <Menu size={19} />}
              </button>
              <span>Permear Workspace</span>
            </div>
            <main id="main-content">
              {route === "overview" ? (
                <HomePage navigate={navigate} />
              ) : route === "dataset" ? (
                <DatasetPage navigate={navigate} />
              ) : route === "anotacao" ? (
                <AnnotationPage
                  key={initialKey || "editor"}
                  initialKey={initialKey}
                  onDirty={setDirty}
                  navigate={navigate}
                />
              ) : route === "demonstracao/perfis" ? (
                <ProfilesPage />
              ) : route === "demonstracao/analisar" ? (
                <DemoPage
                  navigate={navigate}
                  onDirty={setDirty}
                  pending={pending}
                  setPending={setPending}
                />
              ) : (
                <div className="empty">
                  <h1>Página não encontrada</h1>
                  <button onClick={() => navigate("overview")}>
                    Voltar ao início
                  </button>
                </div>
              )}
            </main>
          </div>
        </div>
      </DatasetProvider>
    </ProfilesProvider>
  );
}
