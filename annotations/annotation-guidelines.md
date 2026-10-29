# Manual de anotação de características de transitabilidade

Versão do schema: **2**

Este manual orienta a anotação visual de uma imagem isolada. A unidade analisada
é a **faixa principal de circulação** estruturalmente destinada a atravessar a
cena. Ela não representa o caminho particular de uma pessoa nem deve desviar
artificialmente de obstáculos. Registre apenas o que está visível; não suponha condições
fora do enquadramento. As referências métricas de largura servem para organizar
o julgamento visual e não representam uma medição física obtida da imagem.

## Procedimento comum

1. Defina `circulation_path_status` e, quando identificada, desenhe a
   `circulation_path` sobre a imagem.
2. Observe a continuidade dessa faixa do primeiro plano ao trecho mais distante
   que ainda possa ser avaliado.
3. Considere objetos somente quando invadem, reduzem ou interrompem essa faixa.
4. Preencha todas as propriedades. Em campos multilabel, confirme explicitamente
   o conjunto vazio quando nenhum item relevante estiver visível.
5. Use `unknown` quando perspectiva, distância, recorte, desfoque ou oclusão
   impedirem a distinção exigida pelo campo.
6. Registre `annotation_confidence` por último, considerando o conjunto inteiro
   da anotação.

## `circulation_path`: faixa principal de circulação

`circulation_path` é uma lista de polígonos que representa o corredor que
estruturalmente deveria permanecer disponível à circulação. Ela não é a calçada
inteira, a rua, canteiros, faixa de mobiliário/serviço, estacionamento, áreas
laterais ou uma rota pessoal escolhida para desviar de barreiras.

O polígono **não contorna obstáculos internos**. Se um poste ou veículo invade o
corredor, desenhe a faixa como ela existiria estruturalmente, cobrindo também a
região ocupada pelo objeto. Depois registre o objeto em `obstacle_type` e seu
efeito em `obstruction`, `passage_width` e demais campos aplicáveis. Um objeto em
canteiro ou faixa lateral permanece fora do polígono e não vira obstáculo apenas
por aparecer na fotografia.

### Status espacial

- `annotated`: há faixa principal identificável; ao menos um polígono fechado é
  obrigatório.
- `absent`: a cena evidencia que não existe faixa principal contínua
  identificável/utilizável; a geometria deve ficar vazia.
- `unknown`: perspectiva, recorte ou oclusão impedem determinar a faixa com
  segurança; a geometria deve ficar vazia.

Não use `absent` quando a faixa pode existir, mas a imagem não permite avaliá-la;
nesse caso use `unknown`. Quando a faixa é desenhável com incerteza, mantenha
`annotated` e reduza `annotation_confidence` para `medium` ou `low`.

### Como desenhar

1. Selecione **Identificada**.
2. Clique nos vértices do corredor sobre a imagem e feche o polígono clicando no
   primeiro vértice.
3. Use o modo de edição da barra do canvas para mover/ajustar o polígono.
4. Use desfazer/refazer ou limpar na própria barra. **Restaurar polígono salvo**
   descarta o rascunho e reprojeta a última geometria persistida.
5. Confirme visualmente que piso, bordas e obstáculos continuam visíveis sob o
   overlay semitransparente.

As coordenadas são persistidas normalizadas (`x` e `y` entre 0 e 1) em relação à
imagem original, acompanhadas de `image_width` e `image_height`. O tamanho do
canvas não altera a geometria oficial.

### Exemplos espaciais obrigatórios

- **Caso A — carro normalmente na rua:** desenhe a calçada; não inclua `vehicle`
  em `obstacle_type`; use `obstruction: none`.
- **Caso B — carro parcialmente sobre o corredor:** a faixa continua cobrindo o
  corredor estrutural, inclusive a invasão; inclua `vehicle` e use `partial` ou
  `full` conforme a passagem restante.
- **Caso C — árvore em canteiro lateral:** a árvore fica fora da
  `circulation_path`; não marque `tree`.
- **Caso D — tronco ocupando o corredor:** mantenha o tronco dentro do polígono,
  marque `tree` e avalie `obstruction` e `passage_width`.
- **Caso E — poste em faixa lateral de mobiliário:** deixe-o fora do polígono e
  não o trate como obstáculo relevante.
- **Caso F — poste no centro da passagem:** mantenha-o dentro do polígono e
  marque `pole`.
- **Caso G — vegetação somente em jardim/canteiro:** deixe-a fora do polígono e
  não marque `vegetation`.
- **Caso H — vegetação invadindo o corredor:** mantenha a faixa estrutural e
  marque `vegetation` pela porção que a invade.

### Relação com as propriedades existentes

- `passage_width` é a largura **livre aparente** da `circulation_path`, não a
  largura total da calçada nem áreas de serviço/canteiros. Obstáculos internos
  podem reduzir a largura livre. Não estime centímetros exatos sem calibração.
- `obstruction`, `obstacle_type`, `detour` e `path_continuity` dependem
  diretamente da região desenhada e de suas transições.
- `path_continuity: continuous` mantém a faixa através da cena; `restricted`
  indica estreitamento, desvio ou comprometimento; `interrupted` indica ausência
  de continuidade; `unknown` indica imagem insuficiente.
- `detour: available` exige alternativa visível na própria imagem que contorne a
  interferência e retorne ao corredor. Nunca invente trecho fora do enquadramento.
- `surface_condition` e `surface_obstacle` avaliam prioritariamente o piso dentro
  do polígono. Um buraco na rua fora da rota não contamina a calçada.
- `level_change`, `ramp_condition` e `curb_access` consideram mudanças e
  transições relevantes conectadas à faixa.
- `slope` continua visual/aparente e nunca deve ser convertida em porcentagem sem
  calibração.

## 1. `passage_width`

**Objetivo.** Classificar a menor largura livre aparente ao longo da passagem
contínua visível. Não medir pixels nem converter perspectiva em metros.

**Valores.**

- `wide`: largura visual equivalente a cerca de 1,50 m ou mais; duas cadeiras ou
  uma cadeira com ampla folga aparentariam caber lado a lado.
- `adequate`: cerca de 1,20 m a 1,49 m; uma cadeira aparenta passar com margem
  lateral clara.
- `narrow`: abaixo de cerca de 1,20 m, mas ainda há faixa visual compatível com
  uma cadeira comum.
- `very_narrow`: existe uma fresta contínua, porém sua largura aparente é menor
  que a de uma cadeira comum.
- `blocked`: não existe faixa contínua livre atravessando o ponto crítico.
- `unknown`: o ponto mais estreito não pode ser visto ou a perspectiva impede
  comparar a abertura com elementos da cena.

**Não considerar.** Não reduza a largura por causa de árvore, veículo ou poste
fora da faixa de circulação. Não use a largura total da rua quando a rota é a
calçada. Não classifique inclinação como largura.

**Exemplos conceituais.** Calçada ampla sem invasões é `wide`; poste deixando
uma faixa lateral ainda utilizável pode ser `narrow`; muro e veículo sem espaço
entre eles resultam em `blocked`.

**Confusões.** `passage_width` descreve o espaço livre resultante;
`obstruction` descreve se algo invade esse espaço. Uma calçada construída já
estreita pode ser `narrow` com `obstruction: none`.

## 2. `obstruction`

**Objetivo.** Registrar quanto objetos físicos invadem a faixa útil.

**Valores.**

- `none`: nenhum objeto relevante ocupa a faixa.
- `partial`: um objeto ocupa parte da faixa, mas sobra passagem lateral aparente.
- `full`: um objeto atravessa toda a largura útil ou fecha a única continuação.
- `unknown`: não é possível ver as laterais ou a profundidade necessárias para
  saber se resta passagem.

**Não considerar.** Piso quebrado sem objeto sobreposto pertence a
`surface_condition` e `surface_obstacle`. Uma calçada estreita por construção,
sem objeto invasor, não é obstrução.

**Exemplos conceituais.** Lixeira ocupando metade da calçada é `partial`; tapume
fechando toda a calçada é `full`; carro estacionado apenas na rua é `none`.

**Confusões.** `obstruction: full` descreve o bloqueio no ponto observado.
`path_continuity: interrupted` descreve o efeito desse bloqueio sobre a rota
através da cena. Frequentemente coexistem, mas avalie cada pergunta separadamente.

## 3. `obstacle_type` (multilabel)

**Objetivo.** Identificar todos os tipos de objeto que efetivamente interferem
na faixa de circulação. O conjunto vazio significa nenhum objeto relevante.

**Valores.**

- `vehicle`: carro, moto, caminhão ou outro veículo invadindo a passagem.
- `bike_scooter`: bicicleta ou patinete ocupando a faixa.
- `pole`: poste ou elemento vertical fixo dentro da faixa útil.
- `sign`: placa, cavalete ou suporte de sinalização dentro da faixa.
- `tree`: tronco, raiz elevada ou parte de árvore interferindo na passagem.
- `vegetation`: galhos, arbustos, folhas ou vegetação rasteira invadindo a faixa.
- `trash_container`: lixeira, contêiner ou recipiente de resíduos na faixa.
- `construction`: tapume, barreira, equipamento ou área de obra sobre a rota.
- `stairs`: escada ou degraus que constituem a continuação da rota.
- `litter_debris`: lixo solto, caixas, sacos ou entulho sobre a passagem.
- `utility`: hidrante, caixa, equipamento ou instalação de serviço na faixa.
- `street_furniture`: banco, mesa, floreira, paraciclo ou mobiliário semelhante.
- `other`: objeto relevante que não cabe nas categorias anteriores.

**Não considerar.** Não marque objetos apenas por estarem presentes na imagem.
Árvore do outro lado da rua, carro corretamente estacionado sem invadir a
calçada e lixeira dentro de propriedade privada ficam desmarcados.

**Exemplos conceituais.** Poste no centro da calçada marca `pole`; vegetação
avançando lateralmente sobre a calçada marca `vegetation`; bicicleta encostada
fora da faixa não marca `bike_scooter`.

**Confusões.** Um cavalete de obra pode exigir `sign` e `construction` quando
ambos descrevem objetos relevantes. Use `litter_debris` para material solto
sobre a rota e `surface_obstacle: debris` para registrar o efeito desse material
na superfície. Se nenhum tipo puder ser confirmado, mantenha o conjunto vazio e
use `obstruction: unknown` quando o grau de bloqueio também não puder ser visto.

## 4. `surface_condition`

**Objetivo.** Resumir a condição predominante do piso dentro da faixa útil.

**Valores.**

- `regular`: superfície firme, contínua e sem irregularidade relevante visível.
- `minor_problem`: problema localizado; a maior parte da faixa permanece regular.
- `major_problem`: irregularidade ocupa porção relevante da faixa ou compromete
  claramente sua utilização.
- `unknown`: piso encoberto, distante, escuro ou recortado demais para avaliação.

**Não considerar.** Não use a aparência da pista se a rota é a calçada. Não
classifique objetos sobre o piso como condição estrutural sem evidência do piso.

**Exemplos conceituais.** Uma rachadura isolada é `minor_problem`; calçada
extensamente quebrada é `major_problem`; pavimento contínuo é `regular`.

**Confusões.** Este campo resume gravidade e extensão. `surface_obstacle` lista
os tipos observados. É válido combinar `minor_problem` com `cracks` ou
`major_problem` com `very_broken` e `height_difference`.

## 5. `surface_obstacle` (multilabel)

**Objetivo.** Registrar os tipos específicos de problema da superfície. O
conjunto vazio confirma que nenhum tipo relevante foi identificado.

**Valores.**

- `cracks`: rachaduras ou fissuras relevantes.
- `bumpy`: saliências repetidas ou textura que aparenta produzir trepidação.
- `uneven_slanted`: superfície lateralmente desnivelada ou irregularmente inclinada.
- `height_difference`: ressalto localizado entre partes da superfície.
- `very_broken`: piso fragmentado ou extensamente rompido.
- `grass`: grama ocupando a faixa de passagem.
- `sand_gravel`: areia, cascalho ou agregado solto.
- `brick_cobblestone`: tijolo, paralelepípedo ou peças segmentadas irregulares.
- `pooled_water`: água acumulada sobre a passagem.
- `rail_track`: trilho cruzando ou acompanhando a rota.
- `utility_panel`: tampa ou painel de utilidade embutido e relevante.
- `debris`: detritos ou material solto na superfície.
- `other`: problema observável não coberto acima.

**Não considerar.** Não marque gramado decorativo ao lado da calçada. Não marque
uma tampa nivelada e sem interferência como `utility_panel`. Sombras e manchas
de cor não são rachaduras.

**Exemplos conceituais.** Placas quebradas e deslocadas podem marcar `very_broken`
e `height_difference`; faixa de cascalho na rota marca `sand_gravel`; poça fora
da faixa não marca `pooled_water`.

**Confusões.** Use `level_change` para a intensidade da transição vertical da
rota e `surface_obstacle: height_difference` para identificar o tipo de problema
local do piso. Se o piso não puder ser avaliado, deixe este conjunto vazio e use
`surface_condition: unknown`.

## 6. `level_change`

**Objetivo.** Classificar a mudança vertical relevante encontrada ao seguir a rota.

**Valores.**

- `none`: rota sem ressalto ou degrau perceptível relevante.
- `minor`: pequeno ressalto visível, sem aparência de degrau completo.
- `step`: degrau, meio-fio elevado ou transição vertical claramente significativa.
- `unknown`: a base da transição ou sua altura aparente não pode ser observada.

**Não considerar.** Não estime milímetros. Inclinação contínua pertence a
`slope`; textura áspera sem mudança vertical localizada pertence à superfície.

**Exemplos conceituais.** Junta levemente elevada é `minor`; meio-fio sem
rebaixamento na rota é `step`; acesso nivelado é `none`.

**Confusões.** `level_change` descreve a mudança vertical. `curb_access` descreve
como ocorre a transição calçada-via. Um meio-fio pode ser `step` e
`raised_no_ramp`; uma rampa pode ter `level_change: none` no trajeto utilizável.

## 7. `ramp_condition`

**Objetivo.** Avaliar a solução de rampa ou rebaixamento quando a rota exige
vencer uma transição de nível.

**Valores.**

- `not_applicable`: não há transição relevante que exija rampa na cena.
- `clear`: rampa visível, contínua e sem objeto ocupando sua faixa.
- `problematic`: rampa existe, mas o piso, geometria aparente ou conexão apresenta
  problema observável.
- `blocked`: rampa existe e um objeto impede seu uso.
- `missing_required`: a rota encontra transição relevante sem solução acessível aparente.
- `unknown`: existe situação relevante, mas recorte ou perspectiva impede avaliar a rampa.

**Não considerar.** Não classifique entrada inclinada de garagem como rampa de
pedestres sem conexão com a rota. Não suponha rampa fora da imagem.

**Exemplos conceituais.** Rebaixamento livre é `clear`; veículo sobre o
rebaixamento é `blocked`; meio-fio na travessia sem rebaixamento visível é
`missing_required`.

**Confusões.** `curb_access: ramp` registra que a forma de acesso é uma rampa;
`ramp_condition` registra se ela está livre, problemática ou bloqueada. Quando
não há transição calçada-via, ambos tendem a `not_applicable`.

## 8. `curb_access`

**Objetivo.** Descrever a forma de acesso entre calçada e via quando essa
transição aparece na rota avaliada.

**Valores.**

- `not_applicable`: a rota visível não cruza nem alcança uma transição calçada-via.
- `level`: encontro praticamente nivelado entre as superfícies.
- `ramp`: rebaixamento ou rampa conecta as superfícies.
- `raised_no_ramp`: meio-fio elevado sem rebaixamento aparente na rota.
- `blocked`: acesso existe, mas está ocupado por objeto físico.
- `unknown`: a transição relevante está recortada, encoberta ou distante demais.

**Não considerar.** Não avalie qualquer meio-fio da imagem; use apenas o que faz
parte da rota. Não marque `ramp` apenas por haver uma entrada de veículos próxima.

**Exemplos conceituais.** Esquina com rebaixamento marca `ramp`; travessia que
termina em meio-fio alto marca `raised_no_ramp`; trecho no meio do quarteirão sem
travessia relevante marca `not_applicable`.

**Confusões.** `level_change` responde se há mudança vertical; `curb_access`
responde qual conexão existe. `ramp_condition` avalia a qualidade funcional da
solução observada.

## 9. `detour`

**Objetivo.** Registrar se a própria imagem mostra uma alternativa contínua para
contornar uma barreira e retornar à rota.

**Valores.**

- `not_needed`: a rota principal permanece utilizável sem desvio.
- `available`: há alternativa visível, contínua e reconectada depois da barreira.
- `unavailable`: a barreira exige desvio e nenhuma alternativa utilizável aparece.
- `unknown`: a imagem não mostra extensão suficiente para confirmar reconexão.

**Não considerar.** Não invente cruzamento, entrada ou calçada fora da imagem.
Não trate sair para a via como alternativa segura se a continuidade e o retorno
não forem visíveis.

**Exemplos conceituais.** Objeto contornável pela faixa lateral e com retorno
visível é `available`; tapume até o muro sem faixa lateral é `unavailable`.

**Confusões.** `path_continuity: restricted` pode coexistir com
`detour: available`. Se a rota principal continua sem necessidade de sair dela,
use `detour: not_needed`, mesmo que haja estreitamento.

## 10. `path_continuity`

**Objetivo.** Avaliar se uma faixa de circulação pode ser seguida visualmente ao
longo de toda a cena.

**Valores.**

- `continuous`: faixa conectada e utilizável atravessa a cena.
- `restricted`: a faixa continua, mas estreita, desvia ou sofre comprometimento parcial.
- `interrupted`: a faixa termina ou é bloqueada sem continuação aparente.
- `unknown`: o enquadramento não mostra origem, ponto crítico ou continuação suficiente.

**Não considerar.** Não use a continuidade da rua se a rota analisada é a
calçada. Uma mudança de material sem quebra física não interrompe automaticamente.

**Exemplos conceituais.** Calçada livre é `continuous`; poste obrigando passagem
lateral estreita é `restricted`; escada como única continuação é `interrupted`.

**Confusões.** `obstruction` mede a ocupação por objetos; `path_continuity` mede
o resultado espacial ao atravessar a cena. Uma calçada que termina sem objeto
pode ser `interrupted` com `obstruction: none`.

## 11. `slope`

**Objetivo.** Classificar a inclinação longitudinal aparente do trecho.

**Valores.**

- `flat_gentle`: nenhuma inclinação relevante é perceptível.
- `inclined`: subida ou descida perceptível, sem aparência extrema.
- `steep`: inclinação claramente acentuada em relação às fachadas, postes ou horizonte.
- `unknown`: perspectiva, lente ou ausência de referência impede o julgamento.

**Não considerar.** Não estime porcentagem. Não confunda inclinação lateral
irregular do piso com declive longitudinal; a primeira pertence a
`surface_obstacle: uneven_slanted`.

**Exemplos conceituais.** Rua com subida perceptível é `inclined`; trecho com
forte desnível ao longo de curta distância é `steep`; imagem frontal sem
referência confiável pode ser `unknown`.

**Confusões.** `level_change` trata ressalto ou degrau localizado. `slope` trata
variação contínua ao longo do trajeto.

## 12. `annotation_confidence`

**Objetivo.** Registrar a confiabilidade da anotação humana como metadado. Este
campo nunca é target do modelo.

**Valores.**

- `high`: todos os julgamentos principais têm evidência direta e nítida.
- `medium`: ao menos um julgamento depende de perspectiva, distância, oclusão
  parcial ou limite visual entre duas opções.
- `low`: propriedades centrais dependem de suposição ou a cena fornece pouca
  evidência; o caso deve ser revisado.

**Não considerar.** Não use confiança para expressar severidade da barreira nem
para discordar do schema. Não escolha `high` apenas porque a imagem tem alta resolução.

**Exemplos conceituais.** Vista lateral clara da faixa é `high`; ponto estreito
distante é `medium`; rota quase toda fora do enquadramento é `low`.

**Confusões.** Quando um campo oferece `unknown`, use `unknown` nesse campo e
avalie a confiança global separadamente. Uma anotação pode conter um `unknown`
justificado e ainda ter confiança `medium`; vários campos essenciais invisíveis
normalmente levam a `low`.

## Verificação antes de salvar

- A faixa analisada é a rota de circulação, não qualquer região da imagem.
- Objetos multilabel interferem de fato na passagem.
- Conjuntos vazios foram confirmados deliberadamente.
- `unknown` foi usado somente quando a evidência visual é insuficiente.
- `not_applicable` foi usado somente quando a situação não existe na cena.
- O comentário, quando usado, descreve evidência ou dúvida observável.
