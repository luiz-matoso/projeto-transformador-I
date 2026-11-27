import { useEffect, useState, type FormEvent } from "react";
import { Upload, ArrowLeft, ScanLine } from "lucide-react";
import { workspaceApi, type HistoryDetail } from "../../services/workspace";
import { AnalysisResults } from "./AnalysisResults";
import { History } from "./history/History";
import { Loading } from "../../components/ui/Loading";
import type { SavedProfile } from "./profiles/profiles";
import { analyze, ApiError, session } from "../../services/api";
import type { Result } from "../../types/index";
import { MaskView } from "../../components/MaskView";
import { useFileURL, Notice } from "../../components/ui";
import { useProfiles } from "./profiles/useProfiles";
export type PendingAnalysis = {
  id: string;
  owner: string;
  file: File;
  profiles: SavedProfile[];
  result: Result;
};
export function DemoPage({
  navigate,
  onDirty,
  pending,
  setPending,
}: {
  navigate: (page: string) => void;
  onDirty: (v: boolean) => void;
  pending: PendingAnalysis | null;
  setPending: (value: PendingAnalysis | null) => void;
}) {
  const {
    profiles,
    loading: profilesLoading,
    error: profileError,
  } = useProfiles();
  const [section, setSection] = useState("new"),
    [historical, setHistorical] = useState<HistoryDetail | null>(null);
  const [saving, setSaving] = useState(false),
    [saveError, setSaveError] = useState(
      pending ? "O resultado aguarda salvamento." : "",
    );
  async function persist(value: NonNullable<typeof pending>) {
    if (saving) return;
    setSaving(true);
    setSaveError("");
    try {
      await workspaceApi.saveAnalysis(
        value.id,
        value.file,
        value.profiles,
        value.result,
      );
      setPending(null);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  useEffect(() => {
    if (profiles.length) {
      setFirst((v) => v || profiles[0].id);
      setSecond((v) => v || profiles[1]?.id || profiles[0].id);
    }
  }, [profiles]);
  const [file, setFile] = useState<File | null>(pending?.file ?? null),
    [first, setFirst] = useState(
      pending?.profiles[0]?.id || profiles[0]?.id || "",
    ),
    [second, setSecond] = useState(
      pending?.profiles[1]?.id || profiles[1]?.id || profiles[0]?.id || "",
    ),
    [source, setSource] = useState(pending?.result.observation.source || ""),
    [date, setDate] = useState(() => {
      const date = new Date(pending?.result.observation.observed_at || "");
      return Number.isFinite(date.getTime())
        ? new Date(date.getTime() - date.getTimezoneOffset() * 60000)
            .toISOString()
            .slice(0, 16)
        : "";
    }),
    [validity, setValidity] = useState(
      pending ? pending.result.observation.validity_seconds / 3600 : 24,
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [result, setResult] = useState<Result | null>(pending?.result ?? null),
    [names, setNames] = useState<string[]>(
      pending?.profiles.map((p) => p.name) ?? [],
    ),
    [editing, setEditing] = useState(!pending);
  useEffect(() => {
    onDirty(busy || !!pending);
  }, [busy, pending, onDirty]);
  const url = useFileURL(file);
  useEffect(() => {
    if (editing) setResult(null);
  }, [file, first, second, source, date, validity, editing]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || saving || pending) return;
    const selected = [
      profiles.find((p) => p.id === first),
      profiles.find((p) => p.id === second),
    ];
    if (!file || selected.some((p) => !p)) return;
    setError("");
    setBusy(true);
    setResult(null);
    try {
      const response = await analyze(
        file,
        selected.map((p) => p!.functional ? {functional:p!.functional} : p!.requirements),
        source,
        date,
        validity,
      );
      setNames(selected.map((p) => p!.name));
      setResult(response);
      setEditing(false);
      window.scrollTo(0, 0);
      const save = {
        id: crypto.randomUUID(),
        owner: session.username(),
        file,
        profiles: structuredClone(selected as SavedProfile[]),
        result: response,
      };
      setPending(save);
      await persist(save);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha na análise.");
      if (e instanceof ApiError && e.retryAfter)
        setError((v) => v + ` Aguarde ${e.retryAfter} segundo(s).`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={"page demo-page " + (!editing ? "showing-results" : !profilesLoading&&!profiles.length?"is-empty":"")}>
      <header className="page-heading">
        <h1>Analisar trecho</h1>
        {!editing && section === "new" && !pending && (
          <button onClick={() => setEditing(true)}>
            <ArrowLeft size={16} />
            Editar análise
          </button>
        )}
      </header>
      <div className="tabs" role="tablist" aria-label="Demonstração">
        <button
          role="tab"
          aria-selected={section === "new"}
          onClick={() => {
            setSection("new");
            setHistorical(null);
          }}
        >
          Análise
        </button>
        <button
          role="tab"
          aria-selected={section === "history"}
          onClick={() => setSection("history")}
        >
          Histórico
        </button>
      </div>
      {pending && (
        <Notice error={!!saveError}>
          {saveError
            ? "Resultado ainda não salvo. " + saveError
            : "Salvando resultado…"}{" "}
          {saveError && (
            <button disabled={saving} onClick={() => persist(pending)}>
              {saving ? <Loading /> : "Tentar salvar novamente"}
            </button>
          )}
        </Notice>
      )}
      {section === "history" ? (
        historical ? (
          <>
            <button onClick={() => setHistorical(null)}>
              Voltar ao histórico
            </button>
            <p className="caption">
              Avaliação registrada em{" "}
              {new Date(historical.created_at).toLocaleString("pt-BR")}.
              Abertura sem nova inferência.
            </p>
            <AnalysisResults
              result={historical.result}
              names={historical.profiles.map((p) => p.name)}
              url={historical.image_url}
              maskURL={historical.mask_url}
            />
            <details>
              <summary>Modelos utilizados</summary>
              <pre>{JSON.stringify(historical.model_versions, null, 2)}</pre>
            </details>
          </>
        ) : (
          <History onOpen={setHistorical} />
        )
      ) : editing ? (
        <>
          {profilesLoading ? (
            <Loading />
          ) : profileError ? (
            <Notice error>{profileError}</Notice>
          ) : !profiles.length ? (
            <div className="empty">
              <h2>Crie um perfil para analisar</h2>
              <button className="primary" onClick={() => navigate("demonstracao/perfis")}>
                Gerenciar perfis
              </button>
            </div>
          ) : (
            <form className="demo-form" onSubmit={submit}>
              <fieldset disabled={busy}>
                <div className="demo-input-layout">
                  <section className="image-input">
                    <label
                      className={"upload-area " + (file ? "has-file" : "")}
                    >
                      <input
                        aria-label="Fotografia do trecho"
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                      />
                      <Upload size={24} />
                      <strong>
                        {file ? file.name : "Selecionar fotografia"}
                      </strong>
                      <span>PNG, JPEG ou WebP · até 8 MiB</span>
                    </label>
                    {url && <MaskView src={url} />}
                  </section>
                  <div className="observation-form">
                    <div className="profile-selects">
                      {[
                        ["Perfil 1", first, setFirst],
                        ["Perfil 2", second, setSecond],
                      ].map(([title, value, set], index) => (
                        <label key={index}>
                          {title as string}
                          <select
                            aria-label={title as string}
                            value={value as string}
                            onChange={(e) =>
                              (set as (v: string) => void)(e.target.value)
                            }
                            required
                          >
                            <option value="" disabled>
                              Selecionar perfil
                            </option>
                            {profiles.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                    <label>
                      Origem da observação
                      <input
                        value={source}
                        maxLength={200}
                        required
                        onChange={(e) => setSource(e.target.value)}
                        placeholder="Ex.: vistoria local"
                      />
                    </label>
                    <div className="observation-dates">
                      <label>
                        Data e hora da observação
                        <input
                          type="datetime-local"
                          value={date}
                          onChange={(e) => setDate(e.target.value)}
                        />
                      </label>
                      <label>
                        Validade (horas)
                        <input
                          type="number"
                          min="0.01"
                          max="8760"
                          step="any"
                          value={validity}
                          onChange={(e) => setValidity(Number(e.target.value))}
                          required
                        />
                      </label>
                    </div>
                    <p className="caption">
                      Informe a data de captura, não a data de upload. Sem data
                      válida, a avaliação será indeterminada.
                    </p>

                    <button
                      className="primary analyze-button"
                      type="submit"
                      disabled={!file || busy || file.size > 8 * 1024 * 1024}
                    >
                      {busy ? (
                        <Loading />
                      ) : (
                        <>
                          <ScanLine size={16} />
                          Analisar
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </fieldset>
              {file && file.size > 8 * 1024 * 1024 && (
                <Notice error>A imagem excede 8 MiB.</Notice>
              )}
              {error && <Notice error>{error}</Notice>}
            </form>
          )}
        </>
      ) : (
        result && <AnalysisResults result={result} names={names} url={url} />
      )}
    </div>
  );
}
