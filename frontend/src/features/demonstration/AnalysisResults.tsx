import { useState } from "react";
import { Check, AlertCircle } from "lucide-react";
import { classes, fieldName, label, number } from "../../services/data";
import { MaskView } from "../../components/MaskView";
import type { Result } from "../../types";
export function AnalysisResults({
  result,
  names,
  url,
  maskURL,
}: {
  result: Result;
  names: string[];
  url: string | null;
  maskURL?: string | null;
}) {
  const [tab, setTab] = useState("assessment");
  return (
    <section className="results" aria-live="polite">
      <h2 className="sr-only">Resultado da avaliação</h2>
      <div className="tabs" role="tablist" aria-label="Resultados da análise">
        <button
          role="tab"
          aria-selected={tab === "assessment"}
          onClick={() => setTab("assessment")}
        >
          Avaliação
        </button>
        <button
          role="tab"
          aria-selected={tab === "features"}
          onClick={() => setTab("features")}
        >
          Características e detalhes
        </button>
      </div>
      {tab === "assessment" ? (
        <div role="tabpanel">
          <div className="result-images">
            <figure>
              <figcaption>Imagem original</figcaption>
              {url && <MaskView src={url} />}
            </figure>
            <figure>
              <figcaption>Faixa de circulação prevista</figcaption>
              {url && (result.mask || maskURL) ? (
                maskURL ? (
                  <img
                    className="mask-view"
                    src={maskURL}
                    alt="Máscara prevista"
                  />
                ) : (
                  <MaskView src={url} mask={result.mask!.data} />
                )
              ) : (
                <div className="mask-unavailable">
                  A observação não é válida para executar a percepção.
                </div>
              )}
            </figure>
          </div>
          <div
            className={
              "validity " + (result.observation.is_valid ? "valid" : "invalid")
            }
          >
            {result.observation.is_valid ? (
              <Check size={17} />
            ) : (
              <AlertCircle size={17} />
            )}
            <div>
              <strong>
                {result.observation.is_valid
                  ? "Observação válida"
                  : "Observação sem validade para decisão"}
              </strong>
              <p>{result.observation.message}</p>
              <details>
                <summary>Origem e datas</summary>
                <dl>
                  <div>
                    <dt>Origem</dt>
                    <dd>{result.observation.source}</dd>
                  </div>
                  <div>
                    <dt>Observada em</dt>
                    <dd>{result.observation.observed_at || "Não informada"}</dd>
                  </div>
                  <div>
                    <dt>Vencimento</dt>
                    <dd>{result.observation.expires_at || "Não definido"}</dd>
                  </div>
                  <div>
                    <dt>Avaliada em</dt>
                    <dd>{result.observation.evaluated_at}</dd>
                  </div>
                </dl>
              </details>
            </div>
          </div>
          <div className="assessment-pair">
            {result.assessments.map((a) => (
              <article className="assessment" key={a.profile_index}>
                <p className="assessment-profile">{names[a.profile_index]}</p>
                <h3 className={"classification " + a.classification}>
                  {classes[a.classification]}
                </h3>
                <p className="severity">
                  Severidade:{" "}
                  {
                    (
                      {
                        none: "nenhuma condição de impacto confirmada",
                        moderate: "moderada",
                        critical: "crítica",
                      } as Record<string, string>
                    )[a.severity]
                  }
                </p>
                {a.unassessed_functional_needs?.length ? <div className="complementary-note">
                  Não avaliado automaticamente: {a.unassessed_functional_needs.map(k=>({tight_maneuvers:"manobras em espaços reduzidos",requires_ramps:"necessidade de rampas",inclines:"circulação em inclinações",accepts_detours:"aceitação de desvios"})[k as "tight_maneuvers"]).join(", ")}. A classificação cobre somente os requisitos suportados.
                </div> : null}
                {a.requires_review && (
                  <p className="review">Revisão necessária</p>
                )}
                {a.reasons.length ? (
                  <ul>
                    {a.reasons.map((r, i) => (
                      <li key={i}>
                        {r.message}
                        <details>
                          <summary>Regra aplicada</summary>
                          <dl>
                            <div>
                              <dt>Característica</dt>
                              <dd>{fieldName(r.feature)}</dd>
                            </div>
                            <div>
                              <dt>Valor observado</dt>
                              <dd>{JSON.stringify(r.observed)}</dd>
                            </div>
                            <div>
                              <dt>Requisito</dt>
                              <dd>{JSON.stringify(r.requirement)}</dd>
                            </div>
                            <div>
                              <dt>Código</dt>
                              <dd>{r.code}</dd>
                            </div>
                          </dl>
                        </details>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>Requisitos ativos avaliados sem incompatibilidade.</p>
                )}
                {a.unassessed_features.length > 0 && (
                  <p>
                    Não avaliadas:{" "}
                    {a.unassessed_features.map(fieldName).join(", ")}.
                  </p>
                )}
              </article>
            ))}
          </div>
          <p className="caption interpretation">
            Não transitável indica incompatibilidade confirmada. Indeterminado
            indica informação insuficiente ou inválida. A avaliação não
            substitui inspeção presencial.
          </p>
        </div>
      ) : (
        <div role="tabpanel">
          {!Object.keys(result.features).length ? (
            <p>
              A percepção não foi executada porque a observação não é
              temporalmente válida.
            </p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Característica</th>
                    <th>Predição</th>
                    <th>Confiança</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.features).map(([key, value]) => (
                    <tr key={key}>
                      <td>{fieldName(key)}</td>
                      <td>
                        {Array.isArray(value)
                          ? value.map((v) => label(key, v)).join(", ") ||
                            "Nenhuma relevante"
                          : label(key, value)}
                      </td>
                      <td>{number(result.predictions[key]?.confidence)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <details>
            <summary>Probabilidades e thresholds</summary>
            <pre>{JSON.stringify(result.predictions, null, 2)}</pre>
          </details>
          <details>
            <summary>Características não modeladas e não avaliadas</summary>
            <pre>
              {JSON.stringify(
                {
                  nao_modeladas: result.not_modeled,
                  inativas: result.inactive_features,
                  avaliacoes: result.assessments,
                },
                null,
                2,
              )}
            </pre>
          </details>
          <details>
            <summary>Validade da observação</summary>
            <pre>{JSON.stringify(result.observation, null, 2)}</pre>
          </details>
        </div>
      )}
    </section>
  );
}
