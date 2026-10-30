# Análise do dataset DINOv2 v1

- Anotações totais: **200**
- Utilizáveis (`circulation_path_status=annotated`): **192**
- Excluídas por `circulation_path_status`: **8**
- Split: **134 train / 29 validation / 29 test**
- Unidade de isolamento: **panorama**
- Classes com menos de 10 exemplos são marcadas como raras; menos de 5, como insuficientes para avaliação sólida.

## `passage_width` (categórica)

Unknown mascarado na loss: **0**

| Classe | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| wide | 12 | 9 | 2 | 1 | ok |
| adequate | 47 | 34 | 6 | 7 | ok |
| narrow | 86 | 60 | 13 | 13 | ok |
| very_narrow | 23 | 14 | 6 | 3 | ok |
| blocked | 24 | 17 | 2 | 5 | ok |

## `obstruction` (categórica)

Unknown mascarado na loss: **0**

| Classe | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| none | 46 | 37 | 6 | 3 | ok |
| partial | 109 | 70 | 19 | 20 | ok |
| full | 37 | 27 | 4 | 6 | ok |

## `surface_condition` (categórica)

Unknown mascarado na loss: **0**

| Classe | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| regular | 70 | 52 | 10 | 8 | ok |
| minor_problem | 90 | 59 | 16 | 15 | ok |
| major_problem | 32 | 23 | 3 | 6 | ok |

## `level_change` (categórica)

Unknown mascarado na loss: **2**

| Classe | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| none | 141 | 103 | 20 | 18 | ok |
| minor | 27 | 18 | 4 | 5 | ok |
| step | 22 | 13 | 4 | 5 | ok |

## `path_continuity` (categórica)

Unknown mascarado na loss: **1**

| Classe | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| continuous | 122 | 84 | 20 | 18 | ok |
| restricted | 32 | 22 | 5 | 5 | ok |
| interrupted | 37 | 28 | 4 | 5 | ok |

## `obstacle_type` (multilabel)

Listas vazias (nenhuma classe positiva): **49**

| Label | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| vehicle | 8 | 4 | 3 | 1 | rara |
| bike_scooter | 7 | 5 | 1 | 1 | rara |
| pole | 45 | 33 | 6 | 6 | ok |
| sign | 28 | 16 | 8 | 4 | ok |
| tree | 19 | 14 | 3 | 2 | ok |
| vegetation | 48 | 34 | 7 | 7 | ok |
| trash_container | 9 | 4 | 3 | 2 | rara |
| construction | 18 | 14 | 2 | 2 | ok |
| stairs | 15 | 7 | 3 | 5 | ok |
| litter_debris | 16 | 11 | 3 | 2 | ok |
| utility | 24 | 16 | 3 | 5 | ok |
| street_furniture | 7 | 3 | 1 | 3 | rara |
| other | 7 | 4 | 1 | 2 | rara |

## `surface_obstacle` (multilabel)

Listas vazias (nenhuma classe positiva): **71**

| Label | Total | Train | Validation | Test | Situação |
|---|---:|---:|---:|---:|---|
| cracks | 58 | 38 | 9 | 11 | ok |
| bumpy | 66 | 44 | 10 | 12 | ok |
| uneven_slanted | 41 | 32 | 3 | 6 | ok |
| height_difference | 19 | 13 | 1 | 5 | ok |
| very_broken | 15 | 11 | 2 | 2 | ok |
| grass | 57 | 38 | 11 | 8 | ok |
| sand_gravel | 19 | 11 | 5 | 3 | ok |
| brick_cobblestone | 7 | 4 | 2 | 1 | rara |
| pooled_water | 1 | 1 | 0 | 0 | insuficiente |
| rail_track | 2 | 1 | 0 | 1 | insuficiente |
| utility_panel | 0 | 0 | 0 | 0 | insuficiente |
| debris | 2 | 1 | 0 | 1 | insuficiente |
| other | 1 | 1 | 0 | 0 | insuficiente |

## Limitações do split

A estratificação é aproximada e considera simultaneamente categorias, multilabels e subset, sem quebrar panoramas. Classes com 1–2 exemplos não podem aparecer de forma representativa nos três splits; métricas dessas classes devem ser interpretadas apenas como evidência exploratória.
