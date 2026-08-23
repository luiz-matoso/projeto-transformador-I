## 1. Problema e contexto

Usuários de cadeira de rodas podem encontrar dificuldades para avaliar previamente se um trecho urbano é realmente transitável. A existência de rampas ou calçadas não garante condições adequadas de passagem, pois obstáculos, degraus, buracos, desníveis, trechos estreitos e outras barreiras podem impedir ou dificultar o deslocamento.

Além disso, as condições de um trecho podem mudar com o tempo por causa de obras, veículos, objetos ou outros bloqueios temporários. Por isso, identificar apenas elementos isolados de acessibilidade pode não ser suficiente para representar a condição real de passagem.

O projeto busca apoiar essa avaliação por meio da análise de imagens de trechos urbanos, permitindo identificar condições relevantes para a transitabilidade e classificar o local de acordo com sua possibilidade de passagem.

## 2. Stakeholders

**Usuários de cadeira de rodas:** principais usuários da solução, interessados em saber se determinado trecho apresenta condições adequadas de passagem.  
**Pessoas que contribuem com imagens:** ajudam a registrar e atualizar as condições dos trechos urbanos.  
**Órgãos responsáveis pela infraestrutura urbana:** podem utilizar as informações para identificar locais com problemas de acessibilidade.  
**Especialistas em acessibilidade:** podem auxiliar na definição e validação dos critérios de transitabilidade.  
**Equipe responsável pelo sistema:** responsável pelo desenvolvimento, treinamento e avaliação da solução.

Para o MVP, os stakeholders principais são os usuários de cadeira de rodas e especialistas em acessibilidade. Suas necessidades podem ser investigadas por meio de entrevistas, literatura e critérios técnicos relacionados a acessibilidade urbana.

## 3. Necessidades identificadas

**Avaliação prévia:** saber se determinado trecho apresenta condições adequadas de passagem antes do deslocamento.  
**Identificação de barreiras:** considerar obstáculos, degraus, buracos, desníveis e trechos estreitos.  
**Avaliação geral do trecho:** considerar o local como um todo, e não apenas elementos isolados de acessibilidade.  
**Informações atualizadas:** considerar mudanças temporárias ou permanentes nas condições do local.  
**Localização das avaliações:** associar cada análise ao trecho correspondente.  
**Atualização por novas imagens:** permitir que registros mais recentes atualizem a condição conhecida do trecho.

## 4. Escopo e não escopo

O escopo inicial do projeto será focado na análise de transitabilidade de trechos urbanos para usuários de cadeira de rodas, utilizando imagens como entrada.

**Dentro do escopo:** análise de trechos urbanos, identificação de barreiras relevantes, classificação da transitabilidade, associação da análise a uma localização e exibição dos resultados em um mapa.  
**Fora do escopo inicial:** suporte a outros perfis de mobilidade, cobertura completa de uma cidade e geração automática de rotas acessíveis.

## 5. Requisitos funcionais

**RF01:** receber imagens de trechos urbanos para análise.  
**RF02:** identificar características relevantes para a transitabilidade, como obstáculos, degraus, buracos, desníveis, rampas e limitações de passagem.  
**RF03:** classificar o trecho como transitável, parcialmente transitável ou não transitável.  
**RF04:** associar cada análise a uma localização geográfica.  
**RF05:** registrar o resultado da análise e as características identificadas.  
**RF06:** exibir em um mapa os trechos já analisados e suas respectivas classificações.  
**RF07:** permitir o envio de novas imagens de um trecho já registrado.  
**RF08:** atualizar a avaliação de um trecho com base em registros mais recentes.

## 6. Requisitos não funcionais

**RNF01:** o sistema deve retornar o resultado da análise em até 5 segundos para uma imagem.  
**RNF02:** o sistema deve registrar a versão do modelo utilizada em cada análise.  
**RNF03:** a aplicação deve funcionar em navegadores modernos de desktop e dispositivos móveis.  
**RNF04:** imagens enviadas pelos usuários não devem ser disponibilizadas publicamente sem autorização.

## 7. Regras de negócio

**RN01:** a avaliação da transitabilidade deve considerar, no escopo inicial, as condições de passagem para usuários de cadeira de rodas. Elementos presentes no trecho devem ser analisados de acordo com o impacto que causam nesse perfil de mobilidade.  
**RN02:** todo trecho analisado deve ser classificado como transitável, parcialmente transitável ou não transitável, considerando conjuntamente as características e barreiras identificadas na imagem.

## 8. Critérios de aceitação

Os critérios de aceitação foram definidos para os requisitos considerados essenciais para o MVP.

**CA-RF01:** ao receber uma imagem válida de um trecho urbano, o sistema deve conseguir processar o conteúdo e iniciar a análise.  
**CA-RF02:** o sistema deve identificar e retornar características relevantes para a transitabilidade presentes no trecho analisado.  
**CA-RF03:** ao final da análise, o sistema deve retornar exatamente uma das três classificações definidas: transitável, parcialmente transitável ou não transitável.  
**CA-RF05:** o sistema deve registrar o resultado da análise juntamente com as características identificadas no trecho.

O desempenho do modelo deve ser avaliado em um conjunto de teste separado dos dados utilizados no treinamento, utilizando acurácia, precisão, recall e F1-score por classe.

## 9. Priorização do MVP

A priorização dos requisitos foi realizada utilizando o método MoSCoW.

**Must have:** RF01, RF02, RF03 e RF05.  
**Should have:** RF04 e RF06.  
**Could have:** RF07 e RF08.  
**Won't have now:** suporte a outros perfis de mobilidade, cobertura completa de uma cidade e geração automática de rotas acessíveis.

## 10. Riscos, dúvidas e requisitos ainda abertos

**Critérios de transitabilidade:** ainda é necessário definir de forma objetiva quais condições diferenciam um trecho transitável, parcialmente transitável ou não transitável.  
**Avaliação de referência:** deve ser definido como será produzida a classificação considerada correta para comparação com o resultado do modelo.  
**Barreiras consideradas:** é necessário limitar quais tipos de obstáculos e características urbanas serão considerados inicialmente pelo sistema.  
**Condições temporárias:** ainda deve ser definido como situações como obras, veículos estacionados ou outros bloqueios temporários influenciarão a classificação do trecho.  
**Generalização do modelo:** existe o risco de o modelo apresentar desempenho diferente em locais, ângulos, condições de iluminação e tipos de calçada diferentes dos utilizados no treinamento.  
**Forma de análise:** o MVP utilizará imagens individuais. O uso de sequências de vídeo poderá ser avaliado posteriormente.
