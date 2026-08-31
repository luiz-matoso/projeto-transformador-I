## Trabalhos científicos

### [Improving wheelchair route planning through instrumentation and navigation systems](https://pmc.ncbi.nlm.nih.gov/articles/PMC8883793/)

Džafić, Candiotti e Cooper, 2020. Publicado no IEEE EMBC.

O trabalho apresenta o **eNav**, uma proposta de planejamento de rotas para usuários de cadeiras de rodas elétricas. O sistema considera acessibilidade, características do percurso, distância, conforto e consumo de bateria durante a escolha da rota.

Pode servir como referência para uma etapa futura em que as informações sobre as condições dos trechos sejam utilizadas na seleção de rotas mais adequadas.

[IEEE Xplore](https://ieeexplore.ieee.org/document/9176481) · [PubMed Central](https://pmc.ncbi.nlm.nih.gov/articles/PMC8883793/)

### [Accessibility for Whom? Perceptions of Sidewalk Barriers Across Disability Groups and Implications for Designing Personalized Maps](https://arxiv.org/html/2502.19888v1)

Li et al., 2025. Publicado na **CHI 2025**.

O trabalho investiga como diferentes usuários de dispositivos de mobilidade percebem barreiras encontradas em calçadas. Foram considerados usuários de cadeira de rodas manual, cadeira motorizada, scooter, bengala e andador.

O estudo é relevante principalmente para uma futura evolução da classificação de transitabilidade, considerando diferenças entre perfis de mobilidade.

[arXiv](https://arxiv.org/html/2502.19888v1) · [Makeability Lab](https://makeabilitylab.cs.washington.edu/) · [GitHub](https://github.com/makeabilitylab/accessibility-for-whom)

## Produtos e serviços atuais

### [Framkom](https://www.framkom.no/)

Aplicação de planejamento de rotas voltada também para usuários de cadeiras de rodas. Considera características como inclinação, superfície, distância e tipo de mobilidade, incluindo cadeira manual e elétrica.

É uma referência de produto que utiliza características físicas do percurso para auxiliar na escolha de uma rota.

[Site oficial](https://www.framkom.no/)

### [Wheelmap](https://wheelmap.org/)

Mapa colaborativo voltado à acessibilidade para usuários de cadeira de rodas. Os locais são classificados conforme seu nível de acessibilidade e os dados são baseados no OpenStreetMap.

É uma referência de produto para apresentação e atualização colaborativa de informações de acessibilidade em mapa.

[Site oficial](https://wheelmap.org/) · [Wheelmap](https://news.wheelmap.org/en/about-wheelmap/)

## Projetos técnicos e datasets

### [Project Sidewalk](https://projectsidewalk.org/)

Projeto da University of Washington voltado ao mapeamento e avaliação de acessibilidade das calçadas. Combina crowdsourcing, visão computacional e imagens urbanas para identificar características como obstáculos, problemas de superfície, rampas e ausência de calçada.

É uma das principais referências técnicas para coleta, organização e análise de características de acessibilidade urbana.

[Project Sidewalk](https://projectsidewalk.org/) · [Makeability Lab](https://makeabilitylab.cs.washington.edu/project/sidewalk/) · [GitHub](https://github.com/ProjectSidewalk/SidewalkWebpage)

### [RampNet Dataset](https://huggingface.co/datasets/projectsidewalk/rampnet-dataset)

Dataset do Project Sidewalk voltado à detecção de **curb ramps** em imagens urbanas. Possui aproximadamente **214 mil panoramas** e cerca de **850 mil anotações de rampas**, incluindo suas posições nas imagens e no espaço geográfico.

Principais colunas:

| Coluna                        | Descrição                                         |
| ----------------------------- | ------------------------------------------------- |
| `image`                       | Imagem panorâmica utilizada pelo modelo           |
| `pano_id`                     | Identificador único do panorama                   |
| `record_creation_time`        | Data de criação do registro                       |
| `curb_ramp_points_normalized` | Posições normalizadas das rampas dentro da imagem |
| `pano_coord`                  | Latitude e longitude do panorama                  |
| `curb_ramp_coords`            | Coordenadas geográficas das rampas anotadas       |
| `pano_azimuth`                | Orientação do panorama                            |

Pode ser utilizado para treinamento ou avaliação de um componente específico responsável pela identificação de rampas de acesso.

[Hugging Face](https://huggingface.co/datasets/projectsidewalk/rampnet-dataset) · [GitHub](https://github.com/ProjectSidewalk/RampNet)

### [Sidewalk Tagger AI](https://github.com/ProjectSidewalk/sidewalk-tagger-ai)

Projeto de visão computacional do Project Sidewalk voltado à classificação detalhada das condições encontradas nas calçadas.

Entre as características trabalhadas estão obstáculos, problemas de superfície, passagens estreitas, postes, veículos estacionados, rachaduras e irregularidades.

Principais dados associados às amostras:

| Campo        | Descrição                                       |
| ------------ | ----------------------------------------------- |
| `image`      | Recorte da imagem da calçada                    |
| `image_name` | Identificador ou nome da imagem                 |
| `x`          | Posição horizontal normalizada da anotação      |
| `y`          | Posição vertical normalizada da anotação        |
| `labels`     | Conjunto de características associadas à imagem |

Pode ser utilizado como referência e fonte de dados para classificação de condições que influenciam a transitabilidade de um trecho.

[GitHub](https://github.com/ProjectSidewalk/sidewalk-tagger-ai) · [Hugging Face](https://huggingface.co/datasets/projectsidewalk/sidewalk-tagger-ai-validated)

## Dados interessantes para etapas futuras

### [Accessibility for Whom? Dataset](https://github.com/makeabilitylab/accessibility-for-whom/tree/main)

O estudo disponibiliza as imagens utilizadas no experimento e as respostas de participantes com diferentes dispositivos de mobilidade sobre a dificuldade de atravessar cada situação.

Os principais dados incluem imagens das barreiras, identificação do cenário, características da barreira e avaliações realizadas pelos participantes.

Pode ser utilizado futuramente para evoluir de uma classificação genérica de transitabilidade para uma classificação personalizada conforme o perfil de mobilidade, por exemplo, diferenciando cadeira manual e cadeira motorizada.

[GitHub](https://github.com/makeabilitylab/accessibility-for-whom/tree/main) · [arXiv](https://arxiv.org/html/2502.19888v1) · [Makeability Lab](https://makeabilitylab.cs.washington.edu/)
