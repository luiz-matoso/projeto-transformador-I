import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { workspaceApi } from "../../../services/workspace";
import { validateProfile, type SavedProfile } from "./profiles";
interface ProfileStore {
  profiles: SavedProfile[];
  error: string;
  loading: boolean;
  save: (profile: SavedProfile) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
}
const Context = createContext<ProfileStore | null>(null);
export const useProfiles = () => useContext(Context)!;
export function ProfilesProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<SavedProfile[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setProfiles(await workspaceApi.profiles());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);
  return (
    <Context.Provider
      value={{
        profiles,
        error,
        loading,
        refresh,
        save: async (profile) => {
          const next = validateProfile(profile);
          const saved = await workspaceApi.saveProfile(
            next,
            profiles.some((p) => p.id === next.id),
          );
          setProfiles((current) =>
            current.some((p) => p.id === saved.id)
              ? current.map((p) => (p.id === saved.id ? saved : p))
              : [...current, saved],
          );
          setError("");
        },
        remove: async (id) => {
          await workspaceApi.deleteProfile(id);
          setProfiles((p) => p.filter((v) => v.id !== id));
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
