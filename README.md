# Transitabilidade Urbana com Visão Computacional

Projeto proposto para a disciplina **Projeto Transformador I**, do curso de Ciência da Computação da PUCPR.

A ideia é desenvolver uma solução capaz de avaliar se um trecho urbano é realmente transitável para pessoas com diferentes perfis de mobilidade. A presença de rampas, calçadas ou outros elementos de acessibilidade não garante, por si só, que o local ofereça condições adequadas de passagem.

Obstáculos, buracos, degraus, desníveis, trechos estreitos, obras, veículos e outros bloqueios podem dificultar ou impedir o deslocamento. Por isso, a proposta é analisar as condições do trecho como um todo, em vez de apenas identificar elementos isolados de acessibilidade.

## Proposta

O sistema deverá utilizar imagens de trechos urbanos para identificar características relevantes para a mobilidade e, a partir delas, avaliar a transitabilidade do local.

A proposta considera que diferentes perfis de mobilidade possuem necessidades diferentes. Um mesmo trecho pode ser adequado para uma pessoa e apresentar dificuldades para outra. No futuro, a solução poderá considerar diferentes perfis e aplicar critérios específicos para cada um deles.

## MVP

O escopo inicial será focado em **usuários de cadeira de rodas**, permitindo reduzir a complexidade do problema e validar a proposta antes de considerar outros perfis de mobilidade.

A partir da análise de uma imagem, o sistema deverá considerar características como obstáculos, degraus, buracos, desníveis, rampas e limitações de passagem para classificar o trecho como:

- **Transitável**
- **Parcialmente transitável**
- **Não transitável**

A intenção é avaliar a possibilidade real de passagem, e não apenas indicar se determinado elemento de acessibilidade está presente ou ausente.

## Mapeamento colaborativo

As avaliações poderão ser associadas a localizações geográficas, permitindo construir um mapeamento das condições de transitabilidade dos trechos urbanos.

Usuários poderão contribuir com novas imagens de locais já mapeados, permitindo que as informações sejam atualizadas conforme as condições do ambiente mudem ao longo do tempo.

Esse modelo colaborativo pode ajudar a ampliar gradualmente a quantidade de locais avaliados sem depender exclusivamente de uma coleta centralizada de dados.

## Impacto

A principal aplicação da solução é auxiliar pessoas com mobilidade reduzida a conhecer previamente as condições de um trecho e reduzir a incerteza durante seus deslocamentos.

As informações geradas também podem ter utilidade para a **gestão pública**, permitindo identificar regiões com maior concentração de barreiras, acompanhar mudanças nas condições de acessibilidade e auxiliar na priorização de pontos que necessitam de intervenção.

Além disso, um histórico de avaliações pode fornecer uma visão mais ampla sobre as condições de acessibilidade urbana e sua evolução ao longo do tempo.

## Visão computacional

A visão computacional será utilizada para analisar as imagens e identificar características do ambiente que influenciam a passagem de usuários de cadeira de rodas.

Essas características serão utilizadas como base para a avaliação da transitabilidade do trecho, conectando a identificação visual de barreiras a uma decisão mais próxima da necessidade real do usuário.

## Validação

A proposta será validada comparando as classificações produzidas pelo sistema com avaliações de referência dos mesmos trechos.

O desempenho poderá ser analisado utilizando métricas como:

- acurácia;
- precisão;
- recall;
- F1-score;
- matriz de confusão.

## Estado atual

O projeto está em fase inicial de definição. O foco atual está na delimitação do MVP, definição dos critérios de transitabilidade, seleção das barreiras consideradas e escolha dos dados que serão utilizados para treinamento e avaliação.
