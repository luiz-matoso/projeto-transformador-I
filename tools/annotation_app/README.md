# Ferramenta local de anotação

Painel Streamlit para registrar características visuais de transitabilidade sem
alterar imagens ou datasets de origem. A ferramenta não depende de uma estrutura
específica do Project Sidewalk: qualquer diretório local com imagens suportadas
pode ser selecionado, incluindo um diretório contendo apenas o subset `Obstacle`.

## Instalação

Requer Python 3.10 ou superior. Na raiz do projeto:

```bash
python -m pip install -e .
```

Isso instala as dependências existentes, `PyYAML`, `Streamlit` e o editor
`streamlit-drawable-canvas`.

## Execução

Na raiz do projeto:

```bash
python -m streamlit run tools/annotation_app/app.py
```

No painel:

1. informe qualquer diretório de imagens, absoluto ou relativo à raiz do projeto;
2. escolha se subdiretórios devem ser incluídos;
3. informe o caminho do CSV de anotações;
4. clique em **Carregar diretório e CSV**;
5. classifique o caminho de circulação e, quando identificado, desenhe o
   polígono fechando-o no primeiro ponto ou gere uma sugestão SegFormer;
6. responda pelas pills em português e use **Salvar** ou **Salvar e próxima**.

Para continuar o piloto assistido já gerado, use:

```text
Diretório de imagens: data/annotation-pilot/images
Incluir subdiretórios: sim
CSV de anotações: annotations/transitability_annotations.csv
```

Ao localizar `pilot_manifest.csv` ao lado da pasta `images`, o painel apresenta
subset, split, tags positivas e coordenadas normalizadas originais. Esses dados
são apenas referência do Project Sidewalk: não preenchem nem substituem nenhuma
resposta humana. As 27 imagens previamente anotadas continuam ligadas às linhas
existentes; novas imagens são salvas com o caminho do subset para evitar
colisões de filename.

## Fluxo de anotação

- A imagem, o filename, o status e a navegação permanecem fixos à esquerda em
  telas desktop enquanto o formulário rola à direita.
- As propriedades aparecem na ordem do schema e são agrupadas em passagem,
  superfície, acesso, rota e anotação.
- Todos os campos usam controles rápidos; os dois campos multilabel aceitam
  várias pills ou a escolha explícita **Nenhum relevante**. A interface rejeita
  a combinação de “nenhum” com qualquer item.
- O botão **Salvar e próxima** é a ação principal. A barra de ações fica fixa no
  topo da coluna do formulário e informa campos preenchidos e pendentes em
  tempo real. Somente o painel direito é atualizado a cada escolha; imagem,
  posição e rolagem permanecem estáveis.
- Uma linha existente abre primeiro em leitura. **Editar anotação** habilita os
  valores preenchidos e **Cancelar edição** descarta as mudanças locais.
- O ícone `ⓘ` ao lado de cada propriedade abre as definições sem alongar o
  formulário. As guidelines completas continuam disponíveis na barra lateral.
- Combinações possivelmente incoerentes aparecem como advertências revisáveis.
  Elas não bloqueiam o salvamento e ficam centralizadas em
  `tools/annotation_app/coherence.py`. Atualmente são verificadas somente as
  combinações solicitadas envolvendo obstrução, largura bloqueada, continuidade,
  acesso por rampa e condição de superfície.

## Geração reproduzível do piloto

Os ZIPs são lidos diretamente e apenas as imagens selecionadas são extraídas:

```bash
python -m scripts.dataset.build_annotation_pilot \
  --obstacle data/obstacles \
  --surface-problem data/SurfaceProblem.zip \
  --curb-ramp data/CurbRamp.zip \
  --annotations annotations/transitability_annotations.csv \
  --output data/annotation-pilot \
  --size 200 \
  --seed 42
```

O destino precisa ainda não existir, evitando sobrescrita acidental. A seleção
inclui primeiro as anotações humanas e depois favorece tags raras, combinações,
cidades e splits ainda pouco representados, com penalidade para repetição de
panorama. O resultado contém `pilot_manifest.csv`, `pilot_summary.md` e imagens
separadas por subset. O balanceamento usa apenas labels originais e não presume
a distribuição das 11 propriedades humanas de transitabilidade.

## Caminho de circulação

`circulation_path` delimita a região estrutural contínua pela qual uma pessoa
tentaria se deslocar na cena. Ele não representa um desvio pessoal, não contorna
cada obstáculo e não substitui os campos semânticos de largura, obstrução,
superfície, acesso ou continuidade.

Antes de preencher os demais campos, escolha um estado:

- **Identificada**: a região é reconhecível e deve ser marcada com um polígono;
- **Ausente**: não existe caminho de circulação relevante visível;
- **Não é possível determinar**: a imagem não permite decidir com segurança.

No modo **Identificada**, clique nos limites da região e finalize clicando no
primeiro vértice. A barra do editor permite selecionar e editar o polígono,
desfazer, refazer e limpar. **Restaurar polígono salvo** descarta a edição local
do desenho e recarrega a geometria persistida.

O formato oficial salvo é uma lista de polígonos com coordenadas normalizadas
entre `0` e `1`, acompanhada por `image_width` e `image_height` da imagem
original. O JSON interno do componente de desenho não é persistido.

Em imagens pendentes, **Gerar sugestão SegFormer** executa sob demanda o
checkpoint `artifacts/segmentation/best_segformer.pt`; nunca há inferência
automática ao navegar. A máscara binária (threshold `0.5`) tem componentes com
área inferior ao maior valor entre 64 pixels e 0,05% da imagem removidos. Os
demais componentes são preservados, convertidos em contornos externos e
simplificados moderadamente com Douglas–Peucker (`0.003` do perímetro). Todos
entram no editor existente como polygons normalizados e editáveis.

**Restaurar sugestão** recupera a previsão original e **Limpar** esvazia apenas
o rascunho. Uma sugestão nunca salva nem marca uma imagem como anotada: somente
**Salvar** ou **Salvar e próxima**, após revisão humana, persistem ground truth.
O modelo e o image processor são cacheados pelo Streamlit, CUDA é usada quando
disponível e CPU funciona como fallback. Falhas de checkpoint ou inferência
não bloqueiam o desenho manual.

Os controles nativos mantêm ordem de tabulação e foco de teclado previsíveis.
Atalhos globais (`Ctrl+Enter`, setas e teclas numéricas) não foram adicionados:
o Streamlit não oferece uma API nativa estável para esses eventos, e injetar
JavaScript acoplado ao DOM reduziria a confiabilidade da ferramenta.

Não é necessário possuir os subsets `SurfaceProblem`, `CurbRamp` ou
`Crosswalk`. Eles podem ser selecionados futuramente quando existirem localmente.

## Persistência e continuação

O destino padrão é `annotations/transitability_annotations.csv`. Cada salvamento:

- valida todos os valores contra o schema;
- preserva as demais anotações;
- escreve um arquivo temporário no mesmo diretório;
- sincroniza e substitui o CSV com `os.replace`;
- nunca move, edita ou exclui a imagem original.

Para continuar uma sessão interrompida, selecione o mesmo diretório de imagens e
o mesmo CSV. O painel recarrega as linhas existentes e permite filtrar imagens
anotadas, não anotadas ou com confiança baixa. Editar uma linha existente exige
confirmação explícita antes do salvamento.

O botão **Exportar CSV atual** disponibiliza uma cópia do arquivo persistido.

## Fonte de verdade

- Schema: `annotations/annotation-schema.yaml`
- Guidelines: `annotations/annotation-guidelines.md`
- CSV inicial: `annotations/transitability_annotations.csv`

A interface obtém nomes, tipos, opções, definições, obrigatoriedade, `unknown`,
`not_applicable` e indicação de target diretamente do schema. Alterações futuras
devem ser versionadas em `schema_version`.

CSV v1 e v2 são carregados de forma compatível. A migração atômica para v3
ocorre somente no próximo salvamento: valores, geometria, comentário e timestamp
existentes são preservados e recebem origem `manual`. No caso de v1, as dimensões
originais são lidas e o caminho de circulação é inicializado como **Não é
possível determinar**, sem fabricar polígonos.

## Formato do CSV

Colunas, na ordem estável:

```text
filename,
passage_width,
obstruction,
obstacle_type,
surface_condition,
surface_obstacle,
level_change,
ramp_condition,
curb_access,
detour,
path_continuity,
slope,
annotation_confidence,
circulation_path_status,
circulation_path,
image_width,
image_height,
circulation_path_origin,
comment,
annotation_timestamp,
schema_version
```

- `filename` é o caminho relativo POSIX dentro do diretório selecionado e deve
  ser único no CSV.
- Campos single-label armazenam um valor textual do schema.
- `obstacle_type` e `surface_obstacle` armazenam JSON arrays compactos. Os itens
  são ordenados conforme o schema; conjunto vazio é `[]`.
- `annotation_timestamp` usa ISO 8601 em UTC.
- `circulation_path_status` aceita `annotated`, `absent` ou `unknown`.
- `circulation_path` armazena JSON compacto com coordenadas normalizadas. Ele é
  obrigatório quando o status é `annotated` e deve ser vazio nos demais casos.
- `image_width` e `image_height` registram dimensões positivas da imagem
  original, nunca do canvas redimensionado.
- `circulation_path_origin` registra `manual`, `segformer_v1_accepted` ou
  `segformer_v1_corrected`. A origem só é persistida junto com o save humano.
- `schema_version` é `3` nesta versão.
- `annotation_confidence` é metadado humano e não é output do modelo.

O painel rejeita cabeçalhos incompatíveis, versões divergentes, filenames
duplicados e valores que não pertencem ao schema.
