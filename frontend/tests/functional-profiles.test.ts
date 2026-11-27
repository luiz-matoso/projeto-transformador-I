import {describe,it,expect,vi} from "vitest";
import {validateFunctional,validateProfile,defaultProfiles} from "../src/features/demonstration/profiles/profiles";
import {workspaceApi} from "../src/services/workspace";
import {request} from "../src/services/api";
vi.mock("../src/services/api",()=>({request:vi.fn()}));
const answers={schema_version:1,wheelchair_type:"manual",assistance:"partial",narrow_spaces:"without_difficulty",uneven_surfaces:"with_difficulty",small_level_changes:"with_difficulty",steps:"unable",tight_maneuvers:"with_difficulty",obstacle_avoidance:"without_difficulty",requires_ramps:true,inclines:"unable",accepts_detours:true};
describe("Perfis funcionais de cadeira de rodas",()=>{
 it("não inventa respostas em perfis anteriores",()=>{const p=validateProfile({id:"one",name:"Old",requirements:defaultProfiles[0]});expect(p.functional).toBeUndefined();});
 it("exige todas as respostas e preserva as complementares",()=>{expect(validateFunctional(answers)).toEqual(answers);expect(()=>validateFunctional({...answers,assistance:undefined})).toThrow();expect(()=>validateFunctional({...answers,requires_ramps:"true"})).toThrow();expect(()=>validateFunctional({...answers,small_level_changes:"unable",steps:"without_difficulty"})).toThrow();});
 it("envia respostas para tradução do backend sem requisitos presumidos",async()=>{vi.mocked(request).mockResolvedValueOnce({id:"one",name:"New",functional:answers,requirements:defaultProfiles[0]});await workspaceApi.saveProfile({id:"one",name:"New",functional:validateFunctional(answers),requirements:defaultProfiles[0]});const body=JSON.parse((vi.mocked(request).mock.calls.at(-1)![1] as RequestInit).body as string);expect(body.functional).toEqual(answers);expect(body).not.toHaveProperty("requirements");});
 it("mantém novas respostas ao receber perfis da persistência",async()=>{vi.mocked(request).mockResolvedValueOnce([{id:"two",name:"Read",functional:answers,requirements:defaultProfiles[1]}]);expect((await workspaceApi.profiles())[0].functional).toEqual(answers);});
});
