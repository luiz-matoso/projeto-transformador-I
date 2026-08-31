# Transitabilidade Urbana com Visão Computacional

Projeto proposto para a disciplina **Projeto Transformador I**, do curso de Ciência da Computação da PUCPR.

A proposta é desenvolver uma solução de apoio à mobilidade urbana capaz de avaliar se um trecho é realmente transitável para pessoas com diferentes perfis de mobilidade. A existência de uma calçada, rampa ou rota disponível não significa, por si só, que o deslocamento seja viável.

Obstáculos, buracos, degraus, desníveis, trechos estreitos, obras, veículos e outras condições podem dificultar ou impedir a passagem. O projeto busca transformar essas características do ambiente em informação útil para planejamento de deslocamentos.

## Proposta

O sistema utilizará imagens de trechos urbanos para identificar características relevantes para a mobilidade e, a partir delas, avaliar a transitabilidade do local.

Inicialmente, o foco será em usuários de cadeira de rodas. A partir da análise de uma imagem, o sistema deverá considerar características como obstáculos, degraus, buracos e problemas de superfície, desníveis, rampas e limitações de largura ou passagem para classificar o trecho como:

- **Transitável**
- **Parcialmente transitável**
- **Não transitável**

O objetivo não é apenas reconhecer elementos isolados, mas utilizar as características detectadas para estimar a possibilidade real de passagem.

Essas avaliações poderão ser associadas ao mapa da cidade e utilizadas posteriormente na construção e comparação de rotas. Com uma quantidade suficiente de trechos avaliados, o sistema poderá considerar não apenas distância ou tempo, mas também as condições reais dos caminhos disponíveis.

A proposta também considera que diferentes perfis de mobilidade possuem necessidades diferentes. Um mesmo trecho pode ser adequado para uma pessoa e apresentar dificuldades para outra. Por isso, após a validação inicial com usuários de cadeira de rodas, o sistema poderá evoluir para aplicar critérios específicos a outros perfis de mobilidade.

Em uma evolução futura, a plataforma também poderá integrar serviços de mobilidade assistiva, como pontos de retirada ou aluguel de cadeiras de rodas elétricas. A ideia seria permitir que uma rota combinasse diferentes formas de deslocamento, de maneira semelhante a aplicativos de mobilidade que integram transporte público, caminhada e serviços sob demanda.

Nesse cenário, a classificação das condições das calçadas continua sendo a base do sistema, porque ela permite determinar onde cada trecho é efetivamente transitável e quais alternativas podem ser consideradas durante o percurso.

## Mapeamento e atualização dos dados

As avaliações poderão ser associadas a localizações geográficas, permitindo construir gradualmente um mapa das condições de transitabilidade dos trechos urbanos.

Usuários poderão contribuir com novas imagens de locais já cadastrados ou ainda não avaliados. O sistema poderá processar essas imagens e atualizar as informações conforme as condições do ambiente mudem ao longo do tempo.

Esse modelo permite ampliar progressivamente a cobertura do mapa sem depender exclusivamente de uma coleta centralizada. Também possibilita manter um histórico das condições dos trechos e identificar mudanças relevantes no ambiente urbano.

As informações geradas podem ser utilizadas tanto pelos próprios usuários quanto por órgãos de gestão urbana, por exemplo para identificar regiões com maior concentração de barreiras ou acompanhar pontos que apresentem problemas recorrentes de acessibilidade.

## Validação e evolução

A proposta será validada comparando as classificações produzidas pelo sistema com avaliações de referência dos mesmos trechos.

O desempenho poderá ser analisado utilizando métricas como:

- acurácia;
- precisão;
- recall;
- F1-score;
- matriz de confusão.

Os componentes de visão computacional também poderão ser avaliados individualmente de acordo com as métricas adequadas para cada tarefa.

Após a validação do MVP, algumas evoluções possíveis incluem:

- geração de rotas considerando a transitabilidade dos trechos;
- personalização das rotas para diferentes perfis de mobilidade;
- integração com transporte público e outros serviços de mobilidade;
- integração com pontos de aluguel ou compartilhamento de cadeiras de rodas elétricas;
- uso do histórico para identificar mudanças nas condições das calçadas;
- geração de informações agregadas para apoio à gestão urbana.

## Estado atual

O projeto está em fase de definição e validação inicial. O foco atual está na delimitação do MVP, seleção das barreiras consideradas, definição dos critérios de transitabilidade, escolha dos datasets e estudo das abordagens de visão computacional que poderão ser utilizadas.
