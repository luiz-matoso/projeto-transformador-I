import { matchesStatus, statusLabel } from "../annotation/v4";
import { useRef, useState } from "react";
import { FolderOpen, Upload, Download, ArrowUpRight } from "lucide-react";
import { useDataset } from "./LocalDataset";
import { data, fieldName, label } from "../../services/data";
import { Loading } from "../../components/ui/Loading";
import { useFileURL } from "../../components/ui";
export function DatasetPage({
  navigate,
}: {
  navigate: (p: string, key?: string) => void;
}) {
  const d = useDataset();
  const input = useRef<HTMLInputElement>(null),
    csvInput = useRef<HTMLInputElement>(null),
    files = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState("all"),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [selected, setSelected] = useState<string | null>(null),
    [distribution, setDistribution] = useState("passage_width");
  const filtered = d.images.filter(
    (i) =>
      (!query || i.key.toLowerCase().includes(query.toLowerCase())) &&
      matchesStatus(d.rowFor(i.key), filter),
  );
  const annotated = d.images.filter(
    (i) => d.rowFor(i.key)?.workflow_status === "finalized",
  ).length;
  const row = selected ? d.rowFor(selected) : null;
  return (
    <div
      className={"page dataset-page " + (!d.images.length ? "is-empty" : "")}
    >
      <header className="page-heading">
        <div>
          <h1>Dataset</h1>
        </div>
      </header>
      {d.canResume && (
        <button className="primary" onClick={d.resume}>
          Retomar pasta anterior
        </button>
      )}
      <div className="dataset-actions">
        {" "}
        <details className="file-options dataset-open">
          <summary>Abrir dataset</summary>
          <div>
            {"showDirectoryPicker" in window && (
              <button disabled={d.loading} onClick={d.openDirectory}>
                {d.loading ? <Loading /> : "Abrir pasta local"}
              </button>
            )}
            <button disabled={d.loading} onClick={() => input.current?.click()}>
              Importar pasta
            </button>
            <button disabled={d.loading} onClick={() => files.current?.click()}>
              Importar imagens
            </button>
          </div>
        </details>
        {d.images.length > 0 && (
          <>
            <button
              disabled={d.loading}
              onClick={() =>
                "showOpenFilePicker" in window
                  ? d.openCSV()
                  : csvInput.current?.click()
              }
            >
              Abrir CSV
            </button>
            <button
              onClick={d.exportAll}
              disabled={!Object.keys(d.rows).length}
            >
              <Download size={16} />
              Exportar CSV
            </button>
          </>
        )}
      </div>
      <input
        ref={input}
        type="file"
        multiple
        {...{ webkitdirectory: "" }}
        hidden
        onChange={(e) => {
          if (e.target.files) d.importFiles(Array.from(e.target.files));
        }}
        aria-label="Importar pasta local"
      />
      <input
        ref={files}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files) d.importFiles(Array.from(e.target.files));
        }}
      />
      <input
        ref={csvInput}
        type="file"
        accept=".csv"
        hidden
        onChange={(e) => {
          if (e.target.files?.[0]) d.importCSV(e.target.files[0]);
        }}
        aria-label="Importar CSV"
      />
      {d.error && (
        <div role="alert" className="alert error">
          {d.error}
        </div>
      )}
      {d.notice && <div className="alert">{d.notice}</div>}
      {d.loading && <Loading />}
      {!!d.images.length && (
        <>
          <div className="dataset-summary">
            <strong>{d.name}</strong>
            <span>
              {
                d.images.filter(
                  (i) => d.rowFor(i.key)?.workflow_status === "pending_review",
                ).length
              }{" "}
              a revisar ·{" "}
              {
                d.images.filter(
                  (i) =>
                    d.rowFor(i.key)?.workflow_status === "pending_annotation",
                ).length
              }{" "}
              a anotar · {d.images.length}{" "}
              {d.images.length === 1 ? "imagem" : "imagens"} · {annotated}{" "}
              {annotated === 1 ? "finalizada" : "finalizadas"} ·{" "}
              {d.images.length - annotated} pendentes
            </span>
          </div>
          <div className="filterbar">
            <input
              placeholder="Filtrar por nome do arquivo"
              aria-label="Filtrar imagens"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
            <select
              aria-label="Status das imagens"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="all">Todas</option>
              <option value="finalized">Finalizadas</option>
              <option value="pending_review">Pendente de revisão</option>
              <option value="pending_annotation">Pendente de anotação</option>
              <option value="pending">Pendentes</option>
              <option value="low">Confiança baixa</option>
            </select>
            <span>
              {filtered.length}{" "}
              {filtered.length === 1 ? "resultado" : "resultados"}
            </span>
          </div>
        </>
      )}
      {!d.images.length ? (
        <div className="empty">
          <FolderOpen size={28} />
          <h2>Abra um dataset para começar</h2>
          <p>Selecione uma pasta ou imagens no menu Abrir dataset.</p>
        </div>
      ) : (
        <div className="image-grid">
          {filtered.slice(page * 24, (page + 1) * 24).map((i) => (
            <ImageTile
              key={i.key}
              file={i.file}
              name={i.key}
              annotated={d.rowFor(i.key)?.workflow_status === "finalized"}
              status={statusLabel(d.rowFor(i.key))}
              onClick={() => setSelected(i.key)}
              onEdit={() => navigate("anotacao", i.key)}
            />
          ))}
        </div>
      )}
      {filtered.length > 24 && (
        <div className="pagination">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </button>
          <span>
            Página {page + 1} de {Math.ceil(filtered.length / 24)}
          </span>
          <button
            disabled={(page + 1) * 24 >= filtered.length}
            onClick={() => setPage((p) => p + 1)}
          >
            Próxima
          </button>
        </div>
      )}
      {!!d.images.length && (
        <>
          <details>
            <summary>
              Distribuição das anotações carregadas (
              {Object.keys(d.rows).length} linhas do CSV)
            </summary>
            <label>
              Atributo
              <select
                value={distribution}
                onChange={(e) => setDistribution(e.target.value)}
              >
                {data.schema.fields.map((f) => (
                  <option key={f.name} value={f.name}>
                    {f.display_name}
                  </option>
                ))}
              </select>
            </label>
            <table>
              <thead>
                <tr>
                  <th>Valor</th>
                  <th>Ocorrências</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(
                  Object.values(d.rows).reduce<Record<string, number>>(
                    (counts, r) => {
                      const field = data.schema.fields.find(
                        (f) => f.name === distribution,
                      )!;
                      const values =
                        field.kind === "multilabel"
                          ? JSON.parse(r[distribution] || "[]")
                          : [r[distribution]];
                      for (const value of values)
                        counts[value] = (counts[value] || 0) + 1;
                      return counts;
                    },
                    {},
                  ),
                ).map(([value, count]) => (
                  <tr key={value}>
                    <td>{label(distribution, value)}</td>
                    <td>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          <details className="dataset-records">
            <summary>Piloto do repositório</summary>
            <div className="metric-lines">
              <div>
                <span>Imagens</span>
                <strong>{data.dataset.total}</strong>
              </div>
              <div>
                <span>Faixas anotadas</span>
                <strong>{data.dataset.statuses.annotated}</strong>
              </div>
              <div>
                <span>Faixa indeterminada</span>
                <strong>{data.dataset.statuses.unknown}</strong>
              </div>
            </div>
            <div className="composition-list">
              {Object.entries(data.dataset.subsets).map(([subset, total]) => (
                <div key={subset}>
                  <span>
                    {(
                      {
                        Obstacle: "Obstáculos",
                        SurfaceProblem: "Problemas de superfície",
                        CurbRamp: "Rampas e meio-fio",
                      } as Record<string, string>
                    )[subset] || subset}
                  </span>
                  <strong>{total}</strong>
                </div>
              ))}
            </div>
            <p className="caption">
              Snapshot das anotações do repositório, independente da pasta
              aberta.
            </p>
          </details>
        </>
      )}
      {selected && (
        <dialog open className="detail-dialog">
          <button onClick={() => setSelected(null)}>Fechar</button>
          <h2>{selected}</h2>
          {row ? (
            <dl>
              {Object.entries(row).map(([k, v]) => (
                <div key={k}>
                  <dt>{fieldName(k)}</dt>
                  <dd>
                    {k === "circulation_path"
                      ? `${JSON.parse(v || "[]").length} polígono(s)`
                      : label(k, v)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>Imagem ainda não anotada.</p>
          )}
          <button onClick={() => navigate("anotacao", selected)}>
            Abrir no editor <ArrowUpRight size={16} />
          </button>
        </dialog>
      )}
    </div>
  );
}
function ImageTile({
  file,
  name,
  annotated,
  status,
  onClick,
  onEdit,
}: {
  file: File;
  name: string;
  annotated: boolean;
  status: string;
  onClick: () => void;
  onEdit: () => void;
}) {
  const src = useFileURL(file);
  return (
    <article className="image-tile">
      <button className="image-button" onClick={onClick}>
        {src && <img src={src} alt={name} loading="lazy" />}
      </button>
      <p title={name}>{name.split("/").pop()}</p>
      <div>
        <span className={annotated ? "status-dot saved" : "status-dot"}>
          {status}
        </span>
        <button className="text-button" onClick={onEdit}>
          Anotar <ArrowUpRight size={14} />
        </button>
      </div>
    </article>
  );
}
