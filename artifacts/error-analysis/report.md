# Análise de erros do MVP0

Análise executada sobre as 478 amostras de `test.csv`, usando o
`best_model.pt` atual e os thresholds salvos no próprio checkpoint.

## Resumo por label

| Label | Pos. reais | Neg. reais | TP | FP | FN | TN | Precision | Recall | F1 | Threshold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| construction | 34 | 444 | 17 | 16 | 17 | 428 | 0.5152 | 0.5000 | 0.5075 | 0.3 |
| height-difference | 13 | 465 | 6 | 10 | 7 | 455 | 0.3750 | 0.4615 | 0.4138 | 0.2 |
| parked-car | 74 | 404 | 60 | 12 | 14 | 392 | 0.8333 | 0.8108 | 0.8219 | 0.4 |
| pole | 114 | 364 | 79 | 61 | 35 | 303 | 0.5643 | 0.6930 | 0.6220 | 0.2 |
| trash-recycling-can | 92 | 386 | 59 | 18 | 33 | 368 | 0.7662 | 0.6413 | 0.6982 | 0.3 |
| tree | 31 | 447 | 15 | 26 | 16 | 421 | 0.3659 | 0.4839 | 0.4167 | 0.2 |
| vegetation | 78 | 400 | 60 | 44 | 18 | 356 | 0.5769 | 0.7692 | 0.6593 | 0.3 |

## Principais contagens

- Mais falsos negativos: pole (35), trash-recycling-can (33), vegetation (18).
- Mais falsos positivos: pole (61), vegetation (44), tree (26).
- Maior volume total de erros (FP + FN): pole (96 erros; F1=0.6220), vegetation (62 erros; F1=0.6593), trash-recycling-can (51 erros; F1=0.6982).

## Exemplos para inspeção

Foram copiados até 10 falsos positivos e até 10 falsos negativos por label.
Os falsos positivos foram priorizados pela maior probabilidade prevista; os
falsos negativos, pela menor probabilidade prevista. O arquivo `examples.csv`
liga cada exemplo ao filename original e à probabilidade produzida.

## Observações visuais verificadas

Foi inspecionado manualmente o exemplo de maior confiança de cada tipo de erro
para as três labels com maior volume total de erros:

- `pole/false_positive/01_sample-0144_p-0.9771.png`: há vários elementos
  verticais semelhantes a balizadores/postes baixos, embora a anotação de
  `pole` seja negativa.
- `pole/false_negative/01_sample-0199_p-0.0081.png`: há um elemento vertical
  estreito no primeiro plano, embora o modelo tenha produzido probabilidade
  muito baixa para `pole`.
- `vegetation/false_positive/01_sample-0363_p-0.9955.png`: a cena contém
  árvores, gramado e arbustos, embora a anotação de `vegetation` seja negativa.
- `vegetation/false_negative/01_sample-0036_p-0.0028.png`: há gramado e arbustos
  na lateral direita da cena, embora o modelo tenha produzido probabilidade
  muito baixa para `vegetation`.
- `trash-recycling-can/false_positive/01_sample-0297_p-0.9778.png`: há
  recipientes visíveis nas duas laterais da rua, embora a anotação da classe
  seja negativa.
- `trash-recycling-can/false_negative/01_sample-0224_p-0.0058.png`: o objeto
  anotado não é evidente na inspeção da cena; há objetos pequenos e parcialmente
  ocultos próximos à árvore e à calçada.

Essas observações descrevem somente o conteúdo visível desses seis exemplos.
Elas não demonstram a causa geral dos erros nem permitem concluir se existe
inconsistência de anotação, diferença de definição da classe ou outro fator.
