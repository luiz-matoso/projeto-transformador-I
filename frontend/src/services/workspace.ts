import { request } from "./api";
import type { SavedProfile } from "../features/demonstration/profiles/profiles";
import type { Result } from "../types";
export type HistoryItem = {
  id: string;
  created_at: string;
  profiles: SavedProfile[];
  status: string;
};
export type HistoryDetail = HistoryItem & {
  result: Result;
  image_url: string;
  mask_url: string | null;
  model_versions: Record<string, unknown>;
};
function clean(profile: SavedProfile): SavedProfile {
  const r = profile.requirements;
  return {
    id: profile.id,
    name: profile.name,
    ...(profile.functional ? {functional: structuredClone(profile.functional)} : {}),
    requirements: {
      minimum_passage_width: r.minimum_passage_width,
      surface_tolerance: r.surface_tolerance,
      level_change_tolerance: r.level_change_tolerance,
      accepts_partial_obstruction: r.accepts_partial_obstruction,
    },
  };
}
let profilesRequest:Promise<SavedProfile[]>|null=null;
export const workspaceApi = {
  profiles(): Promise<SavedProfile[]> {
    if(!profilesRequest)profilesRequest=request("/profiles",{},true).then(rows=>rows.map(clean)).finally(()=>{profilesRequest=null;});
    return profilesRequest;
  },
  async saveProfile(
    profile: SavedProfile,
    update = false,
  ): Promise<SavedProfile> {
    return clean(
      await request(
        "/profiles" + (update ? "/" + profile.id : ""),
        {
          method: update ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(profile.functional ? {id:profile.id,name:profile.name,functional:profile.functional} : profile),
        },
        true,
      ),
    );
  },
  deleteProfile(id: string) {
    return request("/profiles/" + id, { method: "DELETE" }, true);
  },
  history(offset = 0): Promise<HistoryItem[]> {
    return request("/analyses?offset=" + offset, {}, true);
  },
  detail(id: string): Promise<HistoryDetail> {
    return request("/analyses/" + id, {}, true);
  },
  deleteAnalysis(id: string) {
    return request("/analyses/" + id, { method: "DELETE" }, true);
  },
  saveAnalysis(
    id: string,
    image: File,
    profiles: SavedProfile[],
    result: Result,
  ) {
    const form = new FormData();
    form.set("image", image);
    form.set("metadata", JSON.stringify({ id, profiles, result }));
    return request("/analyses", { method: "POST", body: form }, true);
  },
};
