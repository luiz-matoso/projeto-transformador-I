# Pré-classificação qualitativa dos erros

Esta é uma pré-classificação visual das imagens copiadas para
`artifacts/error-analysis/`. Ela não altera nem reavalia as anotações do dataset
e deve ser confirmada por revisão humana.

## Escopo

- Imagens analisadas: **137**.
- Confiança alta: **77**.
- Confiança média: **51**.
- Confiança baixa: **9**.

## Distribuição por categoria visual

| Categoria visual | Quantidade | Percentual |
|---|---:|---:|
| possivel_anotacao_ambigua | 36 | 26.3% |
| erro_modelo_claro | 27 | 19.7% |
| objeto_pequeno | 22 | 16.1% |
| classe_visualmente_plausivel | 20 | 14.6% |
| contexto_confuso | 14 | 10.2% |
| oclusao | 14 | 10.2% |
| outro | 4 | 2.9% |

## Distribuição por label

| Label | False positives | False negatives | Total | Categoria dominante |
|---|---:|---:|---:|---:|
| construction | 10 | 10 | 20 | contexto_confuso (6) |
| height-difference | 10 | 7 | 17 | classe_visualmente_plausivel (8) |
| parked-car | 10 | 10 | 20 | possivel_anotacao_ambigua (9) |
| pole | 10 | 10 | 20 | classe_visualmente_plausivel (5) |
| trash-recycling-can | 10 | 10 | 20 | possivel_anotacao_ambigua (7) |
| tree | 10 | 10 | 20 | possivel_anotacao_ambigua (5) |
| vegetation | 10 | 10 | 20 | possivel_anotacao_ambigua (9) |

## Labels com maior incidência nas categorias solicitadas

- `objeto_pequeno`: vegetation (6).
- `oclusao`: tree (5).
- `contexto_confuso`: construction (6).
- `possivel_anotacao_ambigua`: parked-car, vegetation (9).

## Casos com confiança baixa para revisão manual

- `construction/false_positive/09_sample-0424_p-0.3740.png` — não há evidência visual clara de obra.
- `parked-car/false_negative/06_sample-0082_p-0.0525.png` — imagem sem conteúdo visual utilizável.
- `pole/false_negative/04_sample-0249_p-0.0209.png` — não há evidência visual clara de poste.
- `pole/false_negative/05_sample-0147_p-0.0221.png` — elemento vertical distante e imagem parcialmente borrada.
- `pole/false_negative/10_sample-0398_p-0.0470.png` — não há evidência visual clara de poste.
- `trash-recycling-can/false_negative/01_sample-0224_p-0.0058.png` — recipiente pequeno parcialmente encoberto por árvore e poste.
- `tree/false_negative/02_sample-0324_p-0.0136.png` — árvore aparece apenas parcialmente na borda esquerda.
- `tree/false_negative/03_sample-0361_p-0.0152.png` — copa densa sem tronco claramente distinguível.
- `tree/false_negative/04_sample-0371_p-0.0337.png` — árvores pequenas e distantes ao fundo.

## Limite da análise

As categorias descrevem somente evidências visuais nas cópias selecionadas.
`possivel_anotacao_ambigua` indica apenas que a classe parece visualmente
presente ou plausível em um erro; não afirma que a anotação original esteja
incorreta. Nenhuma decisão de treinamento foi tomada.
