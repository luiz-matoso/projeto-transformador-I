import {test,expect} from "@playwright/test";
const original={id:"00000000-0000-4000-8000-000000000001",name:"Perfil anterior",requirements:{minimum_passage_width:"adequate",surface_tolerance:"minor_problems",level_change_tolerance:"minor",accepts_partial_obstruction:true}};
async function setup(page:any,legacy=false){
 const rows:any[]=legacy?[structuredClone(original)]:[];const writes:any[]=[];
 await page.addInitScript(()=>{const expiresAt=Date.now()+3600000;sessionStorage.setItem("permear.session.v1",JSON.stringify({token:"e30."+btoa(JSON.stringify({exp:Math.floor(expiresAt/1000)}))+".test-only",username:"functional-test",expiresAt}));});
 await page.route("**/api/**",(r:any)=>r.fulfill({json:[]}));
 await page.route("**/api/profiles**",async(r:any)=>{const method=r.request().method();if(method==="GET")return r.fulfill({json:rows});
  const body=r.request().postDataJSON();writes.push(body);const saved={...body,requirements:body.requirements??{...original.requirements,minimum_passage_width:"narrow"}};const i=rows.findIndex(p=>p.id===body.id);if(i>=0)rows[i]=saved;else rows.push(saved);return r.fulfill({json:saved});});
 await page.goto("/demonstracao/perfis");return{rows,writes};
}
async function choose(page:any,question:string,answer:string){await page.getByRole("radiogroup",{name:question,exact:true}).getByText(answer,{exact:true}).click();}
test("functional profile: create and edit all answers without inferring capacities from the chair",async({page})=>{
 const {rows,writes}=await setup(page);await page.getByRole("button",{name:"Criar perfil",exact:true}).click();await page.getByLabel("Nome do perfil",{exact:true}).fill("Perfil funcional");
 await expect(page.getByRole("radiogroup",{name:"Tipo de cadeira de rodas"}).getByRole("radio",{checked:true})).toHaveCount(0);
 await choose(page,"Tipo de cadeira de rodas","Motorizada");await choose(page,"Necessidade de assistência","Constante");await page.getByRole("button",{name:"Próximo",exact:true}).click();
 await expect(page.getByRole("radio",{checked:true})).toHaveCount(0);
 for(const[q,a]of [["Consegue circular por espaços estreitos?","Sem dificuldade"],["Consegue circular sobre pisos irregulares?","Com dificuldade"],["Consegue superar pequenos desníveis?","Com dificuldade"],["Consegue transpor degraus?","Não consegue"],["Consegue realizar manobras em espaços reduzidos?","Com dificuldade"],["Consegue contornar obstáculos durante o percurso?","Sem dificuldade"]])await choose(page,q,a);
 await page.getByRole("button",{name:"Próximo",exact:true}).click();
 await choose(page,"Necessita de rampas para mudanças de nível?","Sim");await choose(page,"Consegue circular por superfícies inclinadas?","Não consegue");await choose(page,"Aceita realizar desvios durante o percurso?","Sim");await expect(page.getByRole("button",{name:"Salvar perfil",exact:true})).toBeInViewport();await page.getByRole("button",{name:"Salvar perfil",exact:true}).click();await expect(page.getByRole("heading",{name:"Perfil funcional",exact:true})).toBeVisible();
 expect(writes[0]).not.toHaveProperty("requirements");expect(writes[0].functional).toMatchObject({wheelchair_type:"powered",assistance:"constant",narrow_spaces:"without_difficulty",uneven_surfaces:"with_difficulty",requires_ramps:true,accepts_detours:true});expect(Object.keys(writes[0].functional)).toHaveLength(12);
 await page.getByRole("button",{name:"Editar Perfil funcional",exact:true}).click();await page.getByLabel("Nome do perfil",{exact:true}).fill("Perfil editado");await page.getByRole("button",{name:"Capacidades",exact:true}).click();await expect(page.getByRole("radiogroup",{name:"Consegue circular por espaços estreitos?"}).getByRole("radio",{name:"Sem dificuldade",exact:true})).toBeChecked();await choose(page,"Consegue circular sobre pisos irregulares?","Não consegue");await page.getByRole("button",{name:"Complementares",exact:true}).click();await page.getByRole("button",{name:"Salvar perfil",exact:true}).click();await expect(page.getByRole("heading",{name:"Perfil editado",exact:true})).toBeVisible();expect(rows[0].functional.uneven_surfaces).toBe("unable");
});
test("functional profile: previous profile keeps old requirements and does not invent answers",async({page})=>{
 const {rows,writes}=await setup(page,true);await page.getByRole("button",{name:"Editar Perfil anterior",exact:true}).click();await expect(page.getByRole("radio",{checked:true})).toHaveCount(0);await page.getByLabel("Nome do perfil",{exact:true}).fill("Nome preservado");await page.getByRole("button",{name:"Complementares",exact:true}).click();await page.getByRole("button",{name:"Salvar perfil",exact:true}).click();await expect(page.getByRole("heading",{name:"Nome preservado",exact:true})).toBeVisible();expect(writes[0]).not.toHaveProperty("functional");expect(rows[0].requirements).toEqual(original.requirements);
});
