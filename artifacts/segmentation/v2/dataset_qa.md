# QA do dataset de segmentação v2

- Anotações totais: **200**
- Máscaras válidas: **192**
- `unknown` excluídas: **8**
- Split v1 usado como fonte congelada: `artifacts/segmentation/splits.csv`
- Train: **162**
- Validation preservado: **15**
- Test preservado: **15**
- Panoramas em mais de um split: **0**

## Registros válidos por subset

| Subset | Quantidade |
|---|---:|
| Obstacle | 79 |
| CurbRamp | 50 |
| SurfaceProblem | 63 |

## Decisão

Dataset liberado. Validation/test do v1 foram preservados e nenhuma linha `unknown` entrou no split.
