import { useEffect, useRef, useState, type FormEvent } from "react";
import { X, Accessibility, MoveHorizontal, ListChecks } from "lucide-react";
import { validateFunctional, type SavedProfile } from "./profiles";
import type { FunctionalProfile } from "../../../types";
import { functionalSpec } from "../../../services/data";
import { ChoiceGroup } from "../../annotation/ChoiceGroup";
import { Loading } from "../../../components/ui/Loading";
import { Notice } from "../../../components/ui";

export function ProfileDialog({value,onClose,onSave}:{value:SavedProfile;onClose:()=>void;onSave:(p:SavedProfile)=>Promise<void>}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [name,setName]=useState(value.name),[answers,setAnswers]=useState<Partial<FunctionalProfile>>(value.functional ?? {});
  const [step,setStep]=useState(0),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  useEffect(()=>{dialog.current?.showModal();},[]);
  const ability=(key:keyof FunctionalProfile)=> <div className="profile-question" key={key}>
    <span>{functionalSpec.questions[key]}{key==="tight_maneuvers" && <small>Complementar · não avaliado automaticamente</small>}</span>
    <ChoiceGroup label={functionalSpec.questions[key]} value={String(answers[key] ?? "")} options={Object.entries(functionalSpec.abilities).map(([value,label])=>({value,label,tone:value==="unable"?"critical":value==="with_difficulty"?"caution":"favorable"}))} onChange={v=>setAnswers(a=>({...a,[key]:v}))}/>
  </div>;
  function choices(key:"wheelchair_type"|"assistance"|"requires_ramps"|"accepts_detours",label:string,options:Record<string,string>) {
    return <div className="profile-question" key={key}><span>{label}</span><ChoiceGroup label={label} value={String(answers[key] ?? "")} options={Object.entries(options).map(([value,label])=>({value,label}))} onChange={v=>setAnswers(a=>({...a,[key]:key==="requires_ramps"||key==="accepts_detours"?v==="true":v}))}/></div>;
  }
  async function submit(e:FormEvent){
    e.preventDefault();if(busy)return;setError("");
    if(!name.trim()){setStep(0);setError("Informe o nome do perfil.");return;}
    try{
      const legacyNameOnly=!!value.name&&!value.functional&&Object.keys(answers).length===0;
      const functional=legacyNameOnly?undefined:validateFunctional({schema_version:1,...answers});
      setBusy(true);await onSave({...value,name,...(functional?{functional}:{})});
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <dialog ref={dialog} className="profile-dialog functional-profile-dialog" aria-labelledby="profile-dialog-title" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
    <form onSubmit={submit}>
      <div className="dialog-heading"><h2 id="profile-dialog-title">{value.name?"Editar perfil":"Criar perfil"}</h2><button type="button" className="icon-button" disabled={busy} aria-label="Fechar formulário" onClick={onClose}><X size={18}/></button></div>
      <div className="profile-steps" aria-label="Etapas do perfil">
        {[{label:"Identificação",icon:Accessibility},{label:"Capacidades",icon:MoveHorizontal},{label:"Complementares",icon:ListChecks}].map((item,i)=><button key={item.label} type="button" disabled={busy} aria-pressed={step===i} onClick={()=>setStep(i)}><item.icon size={15}/>{item.label}</button>)}
      </div>
      <div className="profile-dialog-body">
        <fieldset disabled={busy}>
          <section hidden={step!==0} aria-label="Identificação">
            <label>Nome do perfil<input maxLength={80} autoFocus value={name} onChange={e=>setName(e.target.value)}/></label>
            {choices("wheelchair_type","Tipo de cadeira de rodas",functionalSpec.wheelchair_types)}
            {choices("assistance","Necessidade de assistência",functionalSpec.assistance)}
            {!!value.name&&!value.functional&&<Notice>Perfil anterior: novas respostas não informadas. Seus requisitos permanecem preservados até completar o questionário.</Notice>}
          </section>
          <section hidden={step!==1} aria-label="Capacidades de mobilidade">
            {(["narrow_spaces","uneven_surfaces","small_level_changes","steps","tight_maneuvers","obstacle_avoidance"] as const).map(ability)}
          </section>
          <section hidden={step!==2} aria-label="Necessidades complementares">
            <p className="complementary-note">Não avaliadas automaticamente pelos modelos atuais.</p>
            {choices("requires_ramps","Necessita de rampas para mudanças de nível?",{true:"Sim",false:"Não"})}
            {ability("inclines")}
            {choices("accepts_detours","Aceita realizar desvios durante o percurso?",{true:"Sim",false:"Não"})}
            <details className="profile-mapping"><summary>Como as respostas são utilizadas</summary>
              <p>Largura: sem dificuldade → passagem estreita; com dificuldade → adequada; não consegue → ampla. Piso: sem dificuldade → tolera problemas graves; com dificuldade → leves; não consegue → somente regular. São aproximações qualitativas experimentais.</p>
              <p>{String(functionalSpec.mapping.level_change_tolerance)}.</p><p>{String(functionalSpec.mapping.accepts_partial_obstruction)}.</p>
              {functionalSpec.notes.map(n=><p key={n}>{n}</p>)}
            </details>
          </section>
        </fieldset>
      </div>
      {error&&<Notice error>{error}</Notice>}
      <div className="dialog-actions"><button type="button" disabled={busy} onClick={()=>step?setStep(step-1):onClose()}>{step?"Anterior":"Cancelar"}</button>{step<2?<button className="primary" type="button" disabled={busy} onClick={()=>setStep(step+1)}>Próximo</button>:<button className="primary" type="submit" disabled={busy}>{busy?<Loading/>:"Salvar perfil"}</button>}</div>
    </form>
  </dialog>;
}
