# Resultados da V2 funcional

## Modelos e avaliação

A versão documentada utiliza **SegFormer-B0** para segmentar a faixa de circulação e **DINOv2 Base v2-partial** para reconhecer características do trecho. O classificador utiliza fine-tuning dos dois últimos blocos e da normalização final.

O acervo contém 200 anotações, das quais 192 têm faixa de circulação válida. Os dois modelos compartilham o split de **134 imagens de treino, 29 de validação e 29 de teste**, com isolamento por panorama. O melhor checkpoint de cada modelo foi selecionado exclusivamente na validação.

## Segmentação

Métricas de foreground do SegFormer nas 29 imagens de teste. IoU e Dice medem a sobreposição entre a máscara prevista e a anotação humana.

| Métrica | Resultado |
| --- | ---: |
| IoU | 0,5222 |
| Dice | 0,6861 |
| Precision | 0,6816 |
| Recall | 0,6907 |

## Características e pipeline integrado

O mesmo DINOv2 foi avaliado nas mesmas imagens, alternando apenas a máscara de entrada: **humana** ou **prevista pelo SegFormer**. As heads multilabel usam threshold **0,5** nesta comparação.

| Macro F1 por atributo | Máscara humana | Máscara prevista | Delta |
| --- | ---: | ---: | ---: |
| Largura de passagem | 0,2500 | 0,1817 | −0,0683 |
| Obstrução | 0,4729 | 0,2577 | −0,2153 |
| Condição do piso | 0,4872 | 0,4725 | −0,0147 |
| Desnível | 0,3598 | 0,3532 | −0,0066 |
| Continuidade | 0,4824 | 0,2481 | −0,2343 |
| Tipos de obstáculo | 0,2828 | 0,2444 | −0,0384 |
| Problemas da superfície | 0,2987 | 0,3660 | +0,0673 |
| **Agregado** | **0,3762** | **0,3034** | **−0,0729** |

O macro F1 agregado é a média dos macro F1 das sete heads; cada classe tem o mesmo peso dentro de sua head. O micro F1 reúne as decisões das labels de cada head multilabel.

| Micro F1 multilabel | Máscara humana | Máscara prevista |
| --- | ---: | ---: |
| Tipos de obstáculo | 0,4151 | 0,3929 |
| Problemas da superfície | 0,3544 | 0,4198 |

A máscara prevista reduziu o macro F1 agregado em **0,0729**. Continuidade e obstrução apresentaram as maiores quedas.

## Interpretação

- As 29 imagens ficaram fora do treino e da validação de ambos os modelos, mas seus resultados já foram observados durante o desenvolvimento: não são um holdout final completamente cego.
- O conjunto é pequeno e desbalanceado, com classes raras e sinais de overfitting no classificador.
- Os números medem segmentação e reconhecimento de características; não representam a acurácia das classificações finais de transitabilidade.
- Categorias visuais não equivalem a medidas físicas. A avaliação por perfil é experimental e não certifica acessibilidade.

[Voltar ao README](../README.md).
