# Comparação SegFormer v1 × v2

| Métrica | V1 | V2 | Delta |
|---|---:|---:|---:|
| Foreground IoU | 0.4517 | 0.5572 | +0.1055 |
| Dice | 0.6223 | 0.7157 | +0.0934 |
| Precision | 0.6125 | 0.6460 | +0.0334 |
| Recall | 0.6324 | 0.8023 | +0.1698 |

## Seleção por validação

- Melhor epoch v2: **14**
- Validation IoU v2: **0.5845**
- Validation Dice v2: **0.7378**
- Train v1: **75** imagens
- Train v2: **162** imagens
- O test congelado foi avaliado uma única vez após a seleção do checkpoint.

## Sinal de overfitting

- **Sim, após o melhor checkpoint.** Entre as épocas 14 e 19, a train loss caiu de 0.3120 para 0.2567, enquanto a validation IoU caiu de 0.5845 para 0.5705. O early stopping impediu que essas épocas substituíssem o melhor checkpoint.
