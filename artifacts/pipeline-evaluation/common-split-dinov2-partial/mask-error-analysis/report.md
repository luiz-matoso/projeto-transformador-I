# Qualidade da máscara e erros de classificação

Análise pareada das 29 imagens do teste comum. Máscaras previstas regeneradas
com o mesmo checkpoint, threshold 0.5 e pós-processamento usados na avaliação.
IoU e Dice medidos na resolução original, após remoção de pequenos componentes.
Decisões DINO reutilizadas da avaliação registrada: nenhuma nova classificação,
calibração ou treinamento. Hashes dos dois checkpoints conferidos antes e depois.

Nenhuma imagem entrou em treino/validação de nenhum dos dois modelos. O teste
não é completamente cego: seus resultados já foram observados no desenvolvimento.

## Tabela por imagem

Os nomes abaixo são stems únicos; os caminhos completos e as mudanças por head
estão em per_image.csv e changed_decisions.csv. C→E: correta para errada;
E→C: errada para correta. Mudanças também incluem errada para outra errada.

| Imagem | IoU | Dice | Mudanças | C→E | E→C |
|---|---:|---:|---:|---:|---:|
| gsv-newberg-6340-Obstacle | .088 | .161 | 5 | 2 | 2 |
| gsv-newberg-16136-SurfaceProblem | .148 | .258 | 4 | 2 | 2 |
| gsv-amsterdam-18384-CurbRamp | .194 | .325 | 3 | 1 | 2 |
| gsv-newberg-11826-Obstacle | .234 | .379 | 2 | 1 | 0 |
| gsv-cdmx-4241-SurfaceProblem | .269 | .424 | 3 | 1 | 1 |
| gsv-cdmx-39540-Obstacle | .306 | .468 | 1 | 1 | 0 |
| gsv-oradell-12004-Obstacle | .332 | .499 | 0 | 0 | 0 |
| gsv-spgg-47172-Obstacle | .386 | .557 | 4 | 2 | 2 |
| gsv-oradell-4552-SurfaceProblem | .418 | .589 | 2 | 2 | 0 |
| gsv-cdmx-4700-CurbRamp | .418 | .589 | 0 | 0 | 0 |
| gsv-newberg-9692-CurbRamp | .494 | .661 | 0 | 0 | 0 |
| gsv-spgg-51820-CurbRamp | .494 | .662 | 5 | 3 | 2 |
| gsv-cdmx-6762-CurbRamp | .561 | .719 | 1 | 1 | 0 |
| gsv-columbus-33073-Obstacle | .566 | .723 | 2 | 1 | 1 |
| gsv-amsterdam-1131-SurfaceProblem | .570 | .726 | 1 | 0 | 1 |
| gsv-columbus-30093-Obstacle | .603 | .752 | 2 | 2 | 0 |
| gsv-pittsburgh-14504-CurbRamp | .618 | .764 | 1 | 0 | 1 |
| gsv-oradell-6731-CurbRamp | .620 | .765 | 2 | 1 | 0 |
| gsv-oradell-3813-Obstacle | .641 | .781 | 2 | 1 | 1 |
| gsv-spgg-105549-Obstacle | .649 | .787 | 3 | 1 | 0 |
| gsv-chicago-16919-SurfaceProblem | .680 | .809 | 2 | 0 | 2 |
| gsv-walla_walla-1221-CurbRamp | .680 | .809 | 0 | 0 | 0 |
| gsv-spgg-2770-SurfaceProblem | .686 | .813 | 2 | 1 | 1 |
| gsv-cdmx-694-Obstacle | .700 | .824 | 2 | 1 | 1 |
| gsv-amsterdam-676-Obstacle | .746 | .854 | 1 | 1 | 0 |
| gsv-spgg-23525-Obstacle | .763 | .866 | 2 | 0 | 1 |
| gsv-spgg-37185-Obstacle | .822 | .902 | 2 | 2 | 0 |
| gsv-oradell-1819-SurfaceProblem | .880 | .936 | 0 | 0 | 0 |
| gsv-cdmx-3418-SurfaceProblem | .883 | .938 | 1 | 1 | 0 |

Média por imagem: IoU 0.5327; Dice 0.6670. Estes números não são a métrica
global do treino: aqui há média por imagem na resolução original e pós-processamento,
enquanto a avaliação do treino agrega pixels na resolução de 512x512.

## Associação

| Variável | Pearson com IoU | Spearman com IoU | Pearson com Dice |
|---|---:|---:|---:|
| Número de decisões modificadas | -0.442 | -0.344 | -0.472 |
| Correta → errada | -0.289 | -0.284 | -0.304 |
| Saldo de erros (C→E menos E→C) | +0.070 | +0.058 | +0.076 |

IoU e Dice possuem a mesma ordenação para máscaras binárias (Dice=2IoU/(1+IoU));
suas correlações de Spearman são iguais e não representam evidências independentes.
Nos dez menores IoUs houve 12 C→E e 9 E→C; nos dez maiores, 7 C→E e 5 E→C.
As correlações são descritivas de 29 casos, sem inferência causal ou teste de significância.
O saldo de decisões não equivale à variação de macro F1: classes raras e heads
têm pesos diferentes no cálculo agregado.

## Heads especialmente afetadas

| Head | C→E | E→C | Errada→errada | Spearman IoU vs C→E |
|---|---:|---:|---:|---:|
| passage_width | 3 | 2 | 0 | -0.311 |
| obstruction | 6 | 1 | 3 | -0.041 |
| path_continuity | 3 | 0 | 1 | -0.027 |

Obstrução e continuidade pioram sem relação monotônica evidente com IoU.
Largura mostra uma relação negativa mais perceptível, ainda limitada pelo n pequeno.

## Casos discordantes e inspeção visual

- gsv-spgg-37185-Obstacle: IoU .822 / Dice .902; continuidade restricted→continuous
  incorretamente e construction negativo→falso positivo. O painel foi inspecionado:
  a região principal coincide, mas a previsão tem contornos arredondados e uma
  extensão central. Não é possível atribuir causalmente as mudanças a essa extensão.
- gsv-cdmx-3418-SurfaceProblem: IoU .883 / Dice .938; obstruction partial→none
  incorretamente. Inspeção confirma região globalmente semelhante, com bordas e
  extremidades diferentes. Alta sobreposição não assegura estabilidade da head.
- gsv-oradell-12004-Obstacle: IoU .332 / Dice .499; nenhuma decisão mudou.
  Inspeção confirma previsão mais larga e irregular que o polígono humano estreito.
  A estabilidade não significa que todas as classificações estavam corretas.
- Não houve imagem com IoU >= .75 e muitas mudanças simultâneas: no máximo duas.
  Há, sim, decisões semanticamente importantes que degradaram mesmo com IoU alto.

## Respostas e conclusão

1. A qualidade da máscara acompanha parcialmente a instabilidade: menor IoU/Dice
   tende a produzir mais mudanças. A relação com novos erros é fraca, e a relação
   com o saldo líquido é praticamente nula neste teste.
2. Obstrução e continuidade são sensíveis mesmo com boa sobreposição global.
   IoU alto não prova alteração semanticamente pequena: uma borda pode revelar
   ou atenuar conteúdo relevante. A análise não localizou causalmente esses pixels.
3. Os dados não permitem escolher um único gargalo. Há falhas grandes do SegFormer
   e fragilidade da classificação diante da troca de máscara; melhorar somente
   a IoU não garante recuperar o macro F1. O DINO já tinha macro F1 .3762 com
   máscaras humanas, portanto também há limitação de classificação anterior à troca.
4. Treinar com máscaras imperfeitas/perturbadas faz sentido como hipótese de
   experimento futuro de robustez, não como melhora demonstrada. Perturbações
   devem manter o significado dos targets. Máscaras previstas para imagens de
   treino idealmente devem ser geradas fora da amostra, por isolamento de panorama,
   para evitar simular apenas erros artificialmente pequenos de um segmentador
   avaliado nas próprias imagens de treino. Validação decide; este teste não deve
   orientar intensidade de perturbação ou escolher hiperparâmetros.

Nenhum treinamento ou alteração de checkpoint foi realizado.
