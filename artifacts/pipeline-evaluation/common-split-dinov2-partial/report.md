# Avaliação pareada do pipeline com split comum

29 imagens do teste congelado DINO, batch size 8, AMP, modelos em eval e
threshold multilabel 0.5. SegFormer: common-dino-split/best_segformer.pt;
DINO: v2/partial/best_dinov2_v2.pt, época 10.

O split é comum aos dois modelos. Nenhuma destas 29 imagens foi usada em
treino ou validação do novo SegFormer nem do DINO. As atribuições completas
dos splits foram verificadas como idênticas e não há panorama do teste em
treino/validação. Entretanto, este conjunto não é um holdout final completamente
cego: seus resultados já foram observados durante o desenvolvimento.

| Head | Máscara humana macro F1 | Máscara prevista macro F1 | Delta |
|---|---:|---:|---:|
| passage_width | 0.2500 | 0.1817 | -0.0683 |
| obstruction | 0.4729 | 0.2577 | -0.2153 |
| surface_condition | 0.4872 | 0.4725 | -0.0147 |
| level_change | 0.3598 | 0.3532 | -0.0066 |
| path_continuity | 0.4824 | 0.2481 | -0.2343 |
| obstacle_type | 0.2828 | 0.2444 | -0.0384 |
| surface_obstacle | 0.2987 | 0.3660 | +0.0673 |
| Aggregate | 0.3762 | 0.3034 | -0.0729 |

Micro F1: obstacle_type 0.4151 -> 0.3929 (delta -0.0222);
surface_obstacle 0.3544 -> 0.4198 (delta +0.0653).

28 decisões corretas passaram a erradas; 20 erradas passaram a corretas.
Cada head categórica conta uma decisão; cada label multilabel conta uma decisão.
Targets categóricos unknown são excluídos. Cinco imagens mantiveram todas as
decisões finais, embora suas probabilidades tenham mudado.

## Exemplos registrados de degradação

- curb_ramp/gsv-spgg-51820-CurbRamp.png: largura narrow -> adequate (GT narrow);
  pole e sign ausentes passaram de negativos corretos a falsos positivos.
- obstacle/gsv-columbus-30093-Obstacle.png: obstruction full -> partial (GT full);
  utility passou de positivo correto a falso negativo.
- obstacle/gsv-newberg-6340-Obstacle.png: largura blocked -> narrow (GT blocked);
  obstruction full -> partial (GT full).

## Exemplos sem mudanças nas decisões

- curb_ramp/gsv-walla_walla-1221-CurbRamp.png: maior mudança de probabilidade 0.0939.
- curb_ramp/gsv-cdmx-4700-CurbRamp.png: maior mudança de probabilidade 0.1086.
- curb_ramp/gsv-newberg-9692-CurbRamp.png: maior mudança de probabilidade 0.1436.

## Conclusão

A substituição da máscara humana pela prevista reduziu o macro F1 agregado em
0.0729, queda relativa de aproximadamente 19.4%. O efeito é mais forte em
obstrução e continuidade; os problemas de superfície melhoraram neste conjunto.
O resultado mostra sensibilidade relevante da classificação à região fornecida.
Não identifica uma causa visual específica para cada mudança e não permite
generalizar a magnitude da queda além deste teste pequeno e previamente observado.

metrics.json contém métricas completas, deltas e hashes SHA256 dos checkpoints.
decisions.csv contém todas as decisões; samples.csv contém as contagens por imagem.
Os painéis mostram entrada DINO com máscara humana à esquerda e prevista à direita.
A máscara prevista usa threshold 0.5 e o pós-processamento atual de pequenos
componentes; é aplicada diretamente, sem aproximação por polígonos.
O cenário humano reproduziu exatamente o aggregate macro F1 anterior.
Nenhum treinamento, ajuste de hiperparâmetros ou modificação de checkpoint ocorreu;
os hashes dos dois checkpoints foram conferidos após a execução.
