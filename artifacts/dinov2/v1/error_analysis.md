# Análise de erros DINOv2 v1

## Desempenho por head no test

- `surface_condition`: macro F1 **0.4469**
- `path_continuity`: macro F1 **0.3435**
- `passage_width`: macro F1 **0.2632**
- `level_change`: macro F1 **0.2500**
- `surface_obstacle`: macro F1 **0.2281**
- `obstacle_type`: macro F1 **0.2215**
- `obstruction`: macro F1 **0.1880**

- Heads relativamente mais fortes: `surface_condition`, `path_continuity`.
- Heads relativamente mais fracas: `obstacle_type`, `obstruction`.

## Confusões categóricas mais frequentes

- `passage_width`: `narrow` → `adequate` (5 caso(s))
- `obstruction`: `partial` → `none` (8 caso(s))
- `surface_condition`: `regular` → `minor_problem` (7 caso(s))
- `level_change`: `step` → `none` (4 caso(s))
- `path_continuity`: `interrupted` → `continuous` (4 caso(s))

## Classes sem amostras suficientes

- surface_obstacle/pooled_water (1)
- surface_obstacle/rail_track (2)
- surface_obstacle/utility_panel (0)
- surface_obstacle/debris (2)
- surface_obstacle/other (1)

## Overfitting

- Há sinal após a época 2: train loss continuou caindo enquanto a métrica agregada de validação terminou menor.

## Limitação principal

Com apenas 192 imagens utilizáveis e classes multilabel com 1–2 positivos, confusões e F1 zero podem refletir falta de suporte, não somente incapacidade visual do backbone.
