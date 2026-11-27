import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { annotationSchema } from "../src/services/data";
import { attributeGroups, contextFields, optionTone } from "../src/features/annotation/presentation";
import { Definitions } from "../src/features/annotation/Definitions";
import { ChoiceGroup } from "../src/features/annotation/ChoiceGroup";

describe("Apresentação da anotação v4", () => {
  it("mantém todos os atributos uma única vez e os valores de contexto do schema", () => {
    const fields = attributeGroups.flatMap(g => g.names);
    expect([...fields].sort()).toEqual(annotationSchema.fields.map(f => f.name).sort());
    expect(new Set(fields).size).toBe(fields.length);
    expect(contextFields[0].options.map(o => o.value)).toEqual(annotationSchema.surface_material_values);
    expect(contextFields[1].options.map(o => o.value).sort()).toEqual([...annotationSchema.route_scope_values].sort());
  });
  it("distingue condições favoráveis, parciais, críticas e desconhecidas sem colorir objetos arbitrariamente", () => {
    expect(optionTone("passage_width", "adequate")).toBe("favorable");
    expect(optionTone("obstruction", "partial")).toBe("caution");
    expect(optionTone("obstruction", "full")).toBe("critical");
    expect(optionTone("ramp_condition", "not_applicable")).toBe("unknown");
    expect(optionTone("level_change", "unknown")).toBe("unknown");
    expect(optionTone("obstacle_type", "tree")).toBe("plain");
    expect(optionTone("surface_material", "hard_surface")).toBe("plain");
  });
  it("mostra definições da taxonomia sem elementos expansíveis", () => {
    const html = renderToStaticMarkup(<Definitions />);
    expect(html).not.toContain("<details");
    for (const field of annotationSchema.fields) {
      expect(html).toContain(field.display_name);
    }
    expect(html).toContain("Legenda das cores");
    expect(html).toContain("Ferramentas de desenho");
  });
  it("mantém seleção acessível e indica o estado além da cor", () => {
    const html = renderToStaticMarkup(<ChoiceGroup field="obstruction" label="Obstrução" value="partial" options={[{value:"partial",label:"Parcial"}]} onChange={() => {}} />);
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('data-tone="caution"');
    expect(html).toContain('checked=""');
    expect(html).toContain("selected");
  });
});
