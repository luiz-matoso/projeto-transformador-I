# Piloto de anotação

- Total: **200** imagens
- Já anotadas: **27**
- Pendentes: **173**
- Seed: **42**

## Composição por subset

| Subset | Imagens | Train | Test |
|---|---:|---:|---:|
| Obstacle | 80 | 55 | 25 |
| SurfaceProblem | 70 | 38 | 32 |
| CurbRamp | 50 | 26 | 24 |

## Frequência das tags originais

### Obstacle

- `construction`: 10
- `fire-hydrant`: 6
- `garage-entrance`: 6
- `height-difference`: 8
- `litter-garbage`: 8
- `mailbox`: 1
- `narrow`: 38
- `outdoor-dining-area`: 2
- `parked-bike`: 5
- `parked-car`: 6
- `parked-scooter-motorcycle`: 4
- `pole`: 23
- `seating`: 1
- `sign`: 7
- `stairs`: 6
- `street-vendor`: 2
- `trash-recycling-can`: 7
- `tree`: 7
- `vegetation`: 13
- Sem positivos selecionados: `uneven-slanted`

### SurfaceProblem

- `brick-cobblestone`: 13
- `bumpy`: 31
- `construction`: 11
- `cracks`: 29
- `grass`: 20
- `height-difference`: 16
- `narrow-sidewalk`: 16
- `rail-tram-track`: 3
- `sand-gravel`: 17
- `uncovered-manhole`: 6
- `uneven-slanted`: 24
- `utility-panel`: 17
- `very-broken`: 21

### CurbRamp

- `missing-tactile-warning`: 33
- `narrow`: 20
- `not-enough-landing-space`: 24
- `not-level-with-street`: 17
- `points-into-traffic`: 17
- `pooled-water`: 17
- `steep`: 13
- `surface-problem`: 20
- `tactile-warning`: 6
- Sem positivos selecionados: `parallel-lines`

## Critérios de seleção

As 27 anotações humanas foram preservadas e incluídas primeiro. O restante foi selecionado de forma determinística, favorecendo tags raras, combinações de tags ainda não cobertas, diversidade de cidade e de split, e penalizando repetição de panorama e de combinação.

## Limitações

O balanceamento usa somente metadados originais do Project Sidewalk. Ele não estima nem balanceia as 11 propriedades próprias de transitabilidade antes da anotação humana. Tags ausentes ou sem positivos nos CSVs não podem ser representadas.
