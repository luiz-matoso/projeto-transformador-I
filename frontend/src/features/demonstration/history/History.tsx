import { useEffect, useState } from "react";
import {
  workspaceApi,
  type HistoryItem,
  type HistoryDetail,
} from "../../../services/workspace";
import { Loading, Skeleton } from "../../../components/ui/Loading";
import { Notice } from "../../../components/ui";
export function History({
  onOpen,
}: {
  onOpen: (value: HistoryDetail) => void;
}) {
  const [items, setItems] = useState<HistoryItem[]>([]),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [offset, setOffset] = useState(0);
  async function load() {
    setLoading(true);
    setError("");
    try {
      setItems(await workspaceApi.history(offset));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, [offset]);
  async function action(item: HistoryItem, remove = false) {
    if (busy) return;
    if (remove && !confirm("Excluir a análise e seus arquivos?")) return;
    setBusy(item.id);
    setError("");
    try {
      if (remove) {
        await workspaceApi.deleteAnalysis(item.id);
        await load();
      } else onOpen(await workspaceApi.detail(item.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <section aria-label="Histórico de análises">
      {error && (
        <Notice error>
          {error}
          <button onClick={load}>Tentar novamente</button>
        </Notice>
      )}
      {loading ? (
        <Skeleton />
      ) : items.length ? (
        <div className="history-list">
          {items.map((item) => (
            <article key={item.id} className="history-row">
              <div>
                <h2>{item.profiles.map((p) => p.name).join(" · ")}</h2>
                <p className="caption">
                  {new Date(item.created_at).toLocaleString("pt-BR")}
                  {item.status === "deleting" ? " · Exclusão pendente" : ""}
                </p>
              </div>
              <div className="inline-actions">
                <button
                  disabled={!!busy || item.status === "deleting"}
                  onClick={() => action(item)}
                >
                  {busy === item.id ? <Loading /> : "Abrir"}
                </button>
                <button disabled={!!busy} onClick={() => action(item, true)}>
                  Excluir
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        !error && (
          <div className="empty">
            <h2>Nenhuma análise salva</h2>
          </div>
        )
      )}
      {(offset>0||items.length===20) && (
      <div className="pagination">
        <button
          disabled={loading || offset === 0}
          onClick={() => setOffset((v) => Math.max(0, v - 20))}
        >
          Anterior
        </button>
        <button
          disabled={loading || items.length < 20}
          onClick={() => setOffset((v) => v + 20)}
        >
          Próxima
        </button>
      </div>
      )}
    </section>
  );
}
