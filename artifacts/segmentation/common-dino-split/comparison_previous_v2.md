# SegFormer: teste comum ao DINO

O teste é comum aos dois modelos, mas não é um holdout final completamente cego: seus resultados já foram observados durante o desenvolvimento.

Os testes e os tamanhos de treino são diferentes; os deltas abaixo não isolam ganho ou perda de modelo.

| Métrica | V2 anterior (15 teste) | Split comum (29 teste) | Delta |
|---|---:|---:|---:|
| foreground_iou | 0.5572 | 0.5222 | -0.0350 |
| dice | 0.7157 | 0.6861 | -0.0295 |
| precision | 0.6460 | 0.6816 | +0.0357 |
| recall | 0.8023 | 0.6907 | -0.1116 |

Melhor época: 14. Train anterior: 162; comum: 134.
Teste avaliado uma vez, após restaurar o checkpoint escolhido pela validação.