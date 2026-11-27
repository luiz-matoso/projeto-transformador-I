import { BookOpen, PenLine, MousePointer2, Box, Route, Map } from "lucide-react";
import { annotationSchema, label } from "../../services/data";
import { attributeGroups, contextFields, optionTone } from "./presentation";

export function Definitions() {
  return <>
    <section className="annotation-group definition-legend">
      <h2><BookOpen size={16} aria-hidden="true" />Legenda das cores</h2>
      <ul className="semantic-legend">
        <li data-tone="favorable">Condição favorável</li>
        <li data-tone="caution">Dificuldade leve ou parcial</li>
        <li data-tone="critical">Dificuldade grave ou bloqueio</li>
        <li data-tone="unknown">Desconhecido ou não aplicável</li>
      </ul>
      <p>As cores descrevem a opção observada; não substituem a avaliação de transitabilidade por perfil.</p>
    </section>
    <section className="annotation-group definition-section">
      <h2><Route size={16} aria-hidden="true" />Faixa de circulação</h2>
      <p>Delimite o corredor estrutural principal, sem contornar cada obstáculo.</p>
      <dl>
        <div><dt>Identificada</dt><dd>Faixa visível delimitada por um ou mais polígonos.</dd></div>
        <div><dt>Ausente</dt><dd>Não há faixa de circulação identificável na cena.</dd></div>
        <div><dt>Desconhecida</dt><dd>As informações visuais não permitem determinar a faixa.</dd></div>
      </dl>
    </section>
    {attributeGroups.filter(g => g.title !== "Revisão").map(group => <section className="annotation-group definition-section" key={group.title}>
      <h2><group.icon size={16} aria-hidden="true" />{group.title}</h2>
      {group.names.map(name => {
        const field = annotationSchema.fields.find(f => f.name === name)!;
        return <div className="definition-field" key={name}>
          <h3>{field.display_name}</h3>
          <p>{field.description}</p>
          <dl>{field.options.map(option => <div key={option.value}>
            <dt><span className="definition-option" data-tone={optionTone(name, option.value)}>{label(name, option.value)}</span></dt>
            <dd>{option.definition}</dd>
          </div>)}</dl>
          {field.kind === "multilabel" && <p>Nenhum relevante confirma uma lista avaliada e vazia. Desconhecida não confirma ausência. Lista revisada confirma as opções selecionadas.</p>}
        </div>;
      })}
    </section>)}
    <section className="annotation-group definition-section">
      <h2><Map size={16} aria-hidden="true" />Material e contexto</h2>
      {contextFields.map(field => <div className="definition-field" key={field.name}>
        <h3>{field.title}</h3>
        <dl>{field.options.map(option => <div key={option.value}><dt>{option.label}</dt><dd>{option.definition}</dd></div>)}</dl>
      </div>)}
    </section>
    {attributeGroups.filter(g => g.title === "Revisão").map(group => <section className="annotation-group definition-section" key={group.title}>
      <h2><group.icon size={16} aria-hidden="true" />Revisão</h2>
      {group.names.map(name => {
        const field = annotationSchema.fields.find(f => f.name === name)!;
        return <div key={name}><h3>{field.display_name}</h3><dl>{field.options.map(o => <div key={o.value}><dt>{label(name,o.value)}</dt><dd>{o.definition}</dd></div>)}</dl></div>;
      })}
      <p>Salvar guarda a edição. Finalizar e próxima confirma a revisão, registra usuário e data e avança. Identificadores históricos são preservados.</p>
    </section>)}
    <section className="annotation-group definition-section">
      <h2><PenLine size={16} aria-hidden="true" />Ferramentas de desenho</h2>
      <h3><PenLine size={14} aria-hidden="true" />Polígono</h3>
      <p>Clique para desenhar e feche no primeiro ponto. Enter fecha; Esc cancela o desenho em andamento.</p>
      <h3><MousePointer2 size={14} aria-hidden="true" />Edição</h3>
      <p>Arraste os vértices para editar. Botão direito remove um vértice. Desfazer e Refazer recuperam alterações; Restaurar recupera a geometria salva.</p>
      <h3><Box size={14} aria-hidden="true" />Obstáculos espaciais</h3>
      <p>Arraste para delimitar. Selecione a caixa para mover ou ajustar os cantos. Registre tipo e relação com a faixa: fora da faixa, invade a borda, na faixa ou desconhecida. A sobreposição 2D não comprova interferência física.</p>
    </section>
  </>;
}
