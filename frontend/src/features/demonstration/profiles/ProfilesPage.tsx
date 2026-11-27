import { useState } from "react";
import { Plus, PenLine, Trash2, SlidersHorizontal } from "lucide-react";
import {
  defaultProfiles,
  readProfiles,
  profileChoices,
  migrateLocalProfiles,
  type SavedProfile,
} from "./profiles";
import { functionalSpec } from "../../../services/data";
import type { Profile } from "../../../types";
import { workspaceApi } from "../../../services/workspace";
import { Loading, Skeleton } from "../../../components/ui/Loading";
import { Notice } from "../../../components/ui";
import { useProfiles } from "./useProfiles";
import { ProfileDialog } from "./ProfileDialog";
export function ProfilesPage() {
  const store = useProfiles();
  const [migrating, setMigrating] = useState(false),
    [deleting, setDeleting] = useState<string | null>(null);
  const [legacy, setLegacy] = useState<SavedProfile[]>(() => {
    try {
      return readProfiles(localStorage);
    } catch {
      return [];
    }
  });
  const [legacyError] = useState(() => {
    try {
      readProfiles(localStorage);
      return "";
    } catch {
      return "Perfis locais não puderam ser lidos. Os dados foram preservados.";
    }
  });
  async function migrate() {
    if (
      migrating ||
      !confirm(
        "Copiar todos os perfis locais para sua conta? Os dados locais só serão removidos após a confirmação de todos os registros.",
      )
    )
      return;
    setMigrating(true);
    setError("");
    try {
      await migrateLocalProfiles(localStorage, (profile) =>
        workspaceApi.saveProfile(profile),
      );
      await store.refresh();
      setLegacy([]);
    } catch (e) {
      setError(
        (e as Error).message +
          " Os dados locais foram preservados. Tente novamente para continuar sem duplicar.",
      );
    } finally {
      setMigrating(false);
    }
  }
  const [editing, setEditing] = useState<SavedProfile | null>(null),
    [error, setError] = useState("");
  function open(profile?: SavedProfile) {
    setError("");
    setEditing(
      profile
        ? structuredClone(profile)
        : {
            id: crypto.randomUUID(),
            name: "",
            requirements: structuredClone(defaultProfiles[0]),
          },
    );
  }
  return (
    <div className={"page profiles-page " + (!store.loading&&!store.error&&!store.profiles.length?"is-empty":"")}>
      <header className="page-heading">
        <h1>Perfis</h1>
        <button className="primary" onClick={() => open()}>
          <Plus size={16} />
          Criar perfil
        </button>
      </header>
      {legacyError && <Notice error>{legacyError}</Notice>}
      {!!legacy.length && (
        <Notice>
          {legacy.length} perfil(is) deste navegador aguardam migração.{" "}
          <button disabled={migrating || store.loading} onClick={migrate}>
            {migrating ? <Loading /> : "Migrar perfis locais"}
          </button>
        </Notice>
      )}
      {store.error && (
        <Notice error>
          {store.error}{" "}
          <button onClick={store.refresh}>Tentar novamente</button>
        </Notice>
      )}
      {error && <Notice error>{error}</Notice>}
      {store.loading ? (
        <Skeleton />
      ) : store.error ? null : store.profiles.length ? (
        <div className="profile-list">
          {store.profiles.map((profile) => (
            <article className="profile-card" key={profile.id}>
              <div className="profile-card-heading">
                <h2>{profile.name}</h2>
                <div>
                  <button
                    className="icon-button"
                    aria-label={"Editar " + profile.name}
                    onClick={() => open(profile)}
                  >
                    <PenLine size={16} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={"Excluir " + profile.name}
                    disabled={deleting === profile.id}
                    onClick={async () => {
                      if (deleting) return;
                      if (!confirm("Excluir o perfil “" + profile.name + "”?"))
                        return;
                      try {
                        setDeleting(profile.id);
                        await store.remove(profile.id);
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setDeleting(null);
                      }
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              {profile.functional ? <>
                <p className="profile-identification">{functionalSpec.wheelchair_types[profile.functional.wheelchair_type]} · Assistência: {functionalSpec.assistance[profile.functional.assistance].toLowerCase()}</p>
                <details className="profile-capabilities"><summary>Capacidades e necessidades</summary><dl>
                  {Object.entries(functionalSpec.questions).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{functionalSpec.abilities[profile.functional![key as keyof typeof profile.functional] as string]}</dd></div>)}
                  <div><dt>Necessita de rampas?</dt><dd>{profile.functional.requires_ramps?"Sim":"Não"}</dd></div>
                  <div><dt>Aceita desvios?</dt><dd>{profile.functional.accepts_detours?"Sim":"Não"}</dd></div>
                </dl><p className="caption">Manobras, rampas, inclinações e desvios não são avaliados automaticamente.</p></details>
              </> : <><p className="caption">Perfil anterior · novas respostas não informadas</p>              <dl>
                {Object.entries(profileChoices).map(([key, definition]) => (
                  <div key={key}>
                    <dt>{definition.label}</dt>
                    <dd>
                      {
                        (definition.options as Record<string, string>)[
                          profile.requirements[key as keyof Profile] as string
                        ]
                      }
                    </dd>
                  </div>
                ))}
                <div>
                  <dt>Obstrução parcial</dt>
                  <dd>
                    {profile.requirements.accepts_partial_obstruction
                      ? "Aceita"
                      : "Não aceita"}
                  </dd>
                </div>
              </dl></> }
            </article>
          ))}
        </div>
      ) : (
        <div className="empty">
          <SlidersHorizontal size={28} />
          <h2>Nenhum perfil cadastrado</h2>
          <p>Crie os perfis funcionais que deseja comparar na demonstração.</p>
        </div>
      )}
      {editing && (
        <ProfileDialog
          value={editing}
          onClose={() => setEditing(null)}
          onSave={async (p) => {
            await store.save(p);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
