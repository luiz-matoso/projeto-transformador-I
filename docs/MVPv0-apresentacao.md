---
marp: true
theme: default
size: 16:9
paginate: true
html: true
title: Transitabilidade urbana — MVPv0
description: Apresentação parcial do Projeto Transformador I
style: |
  :root {
    --ink: #102a43;
    --muted: #5d6b78;
    --paper: #f7f8f5;
    --white: #ffffff;
    --cyan: #00a6b2;
    --cyan-soft: #d9f2f3;
    --line: #cfd8dc;
    --high: #d65345;
    --moderate: #d18b1f;
    --low: #17866f;
  }

  section {
    width: 1280px;
    height: 720px;
    padding: 58px 72px 52px;
    background: var(--paper);
    color: var(--ink);
    font-family: 'Aptos', 'Segoe UI', sans-serif;
    font-size: 25px;
    line-height: 1.3;
  }

  section::after {
    right: 34px;
    bottom: 24px;
    color: #7c8993;
    font-size: 14px;
    font-weight: 600;
  }

  h1, h2, h3, p { margin: 0; }

  h1 {
    max-width: 630px;
    font-size: 62px;
    line-height: 0.98;
    letter-spacing: -3.2px;
    font-weight: 800;
    word-break: normal;
    overflow-wrap: normal;
  }

  h2 {
    margin-bottom: 34px;
    font-size: 40px;
    line-height: 1.05;
    letter-spacing: -1.5px;
    font-weight: 750;
  }

  h3 {
    font-size: 21px;
    font-weight: 700;
    color: var(--cyan);
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }

  strong { font-weight: 750; }
  small { font-size: 16px; color: var(--muted); }

  .eyebrow {
    margin-bottom: 18px;
    color: var(--cyan);
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
  }

  .rule {
    width: 58px;
    height: 5px;
    margin: 25px 0;
    background: var(--cyan);
  }

  .cover {
    display: flex;
    height: 100%;
    flex-direction: column;
    justify-content: center;
  }

  .cover .subtitle {
    max-width: 485px;
    margin-top: 24px;
    color: var(--muted);
    font-size: 23px;
  }

  .cover .meta {
    position: absolute;
    left: 72px;
    bottom: 52px;
    color: var(--muted);
    font-size: 15px;
    font-weight: 600;
  }

  .problem-copy {
    width: 100%;
    margin-left: 0;
    padding: 96px 18px 0 52px;
  }

  .problem-copy .lead {
    max-width: 600px;
    font-size: 35px;
    line-height: 1.12;
    font-weight: 700;
    letter-spacing: -1px;
  }

  .problem-copy .support {
    max-width: 560px;
    margin-top: 28px;
    color: var(--muted);
    font-size: 21px;
  }

  .pipeline {
    position: relative;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 28px;
    margin-top: 82px;
    align-items: start;
  }

  .pipeline::before {
    content: '';
    position: absolute;
    z-index: 0;
    top: 26px;
    left: 36px;
    right: 36px;
    height: 2px;
    background: var(--line);
  }

  .stage {
    position: relative;
    z-index: 1;
  }

  .stage-number {
    display: flex;
    width: 54px;
    height: 54px;
    align-items: center;
    justify-content: center;
    background: var(--ink);
    color: var(--white);
    border-radius: 50%;
    font-size: 18px;
    font-weight: 750;
  }

  .stage:nth-child(5) .stage-number { background: var(--cyan); }

  .stage h3 {
    margin-top: 28px;
    min-height: 25px;
    color: var(--ink);
    font-size: 19px;
    letter-spacing: 0;
    text-transform: none;
  }

  .stage p {
    margin-top: 9px;
    color: var(--muted);
    font-size: 16px;
    line-height: 1.35;
  }

  .evidence {
    display: grid;
    grid-template-columns: 46% 54%;
    height: 505px;
  }

  .evidence-left {
    padding: 18px 64px 0 0;
    border-right: 1px solid var(--line);
  }

  .split {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    margin: 30px 0 42px;
  }

  .split b {
    display: block;
    font-size: 34px;
    line-height: 1;
    font-weight: 700;
  }

  .split span {
    color: var(--muted);
    font-size: 16px;
    font-weight: 500;
  }

  .evidence-line {
    margin-top: 14px;
    color: var(--muted);
    font-size: 18px;
  }

  .evidence-right {
    display: flex;
    padding: 18px 0 0 68px;
    flex-direction: column;
  }

  .metric-label {
    color: var(--cyan);
    font-size: 21px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }

  .metric-comparison {
    display: grid;
    grid-template-columns: 150px 42px 1fr;
    margin-top: 42px;
    align-items: end;
  }

  .metric-block span { display: block; }

  .metric-value {
    line-height: 0.9;
    font-weight: 800;
    letter-spacing: -2px;
  }

  .metric-old .metric-value {
    color: var(--ink);
    font-size: 40px;
  }

  .metric-new .metric-value {
    color: var(--cyan);
    font-size: 74px;
    letter-spacing: -4px;
  }

  .metric-caption {
    margin-top: 15px;
    color: var(--muted);
    font-size: 15px;
    font-weight: 500;
  }

  .metric-arrow {
    padding-bottom: 23px;
    color: var(--line);
    font-size: 29px;
    font-weight: 700;
  }

  .evidence-proof {
    display: grid;
    gap: 10px;
    margin-top: 48px;
    padding-top: 18px;
    border-top: 1px solid var(--line);
    color: var(--muted);
    font-size: 17px;
    font-weight: 600;
  }

  .demo-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 28px;
  }

  .demo-item {
    display: grid;
    grid-template-rows: 275px 54px auto;
    align-items: start;
  }

  .demo-item img {
    display: block;
    width: 100%;
    height: 275px;
    object-fit: cover;
  }

  .demo-item:nth-child(1) img { object-position: left center; }
  .demo-item:nth-child(2) img { object-position: center center; }
  .demo-item:nth-child(3) img { object-position: center center; }

  .demo-class {
    margin-top: 19px;
    font-size: 25px;
    line-height: 1.05;
    font-weight: 800;
    align-self: start;
  }

  .demo-meta {
    margin-top: 8px;
    color: var(--muted);
    font-size: 16px;
  }

  .demo-item:nth-child(1) .demo-class { color: var(--low); }
  .demo-item:nth-child(2) .demo-class { color: var(--moderate); }
  .demo-item:nth-child(3) .demo-class { color: var(--high); }

  .impact-list { margin-top: 8px; }

  .heuristic-intro {
    margin: -18px 0 20px;
    color: var(--muted);
    font-size: 18px;
  }

  .impact-row {
    position: relative;
    display: grid;
    grid-template-columns: 155px 1fr 380px;
    min-height: 112px;
    padding-left: 22px;
    align-items: center;
    border-top: 1px solid var(--line);
  }

  .impact-row::before {
    content: '';
    position: absolute;
    left: 0;
    width: 4px;
    height: 46px;
    background: var(--line);
  }

  .impact-row.high::before { background: var(--high); }
  .impact-row.moderate::before { background: var(--moderate); }
  .impact-row.low::before { background: var(--low); }

  .impact-row:last-child { border-bottom: 1px solid var(--line); }

  .impact-level {
    color: var(--ink);
    font-size: 18px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }

  .impact-features {
    color: var(--muted);
    font-size: 20px;
  }

  .impact-result {
    font-size: 20px;
    font-weight: 800;
    white-space: nowrap;
  }

  .impact-row.high .impact-result { color: var(--high); }
  .impact-row.moderate .impact-result { color: var(--moderate); }
  .impact-row.low .impact-result { color: var(--low); }

  .heuristic-note {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 44px;
    margin-top: 22px;
    color: var(--muted);
    font-size: 17px;
  }

  .heuristic-note span {
    padding-top: 15px;
    border-top: 1px solid var(--line);
  }

  .heuristic-note strong { color: var(--ink); }

  .closing {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 76px;
    height: 490px;
  }

  .closing-list {
    margin: 22px 0 0;
    padding: 0;
    list-style: none;
  }

  .closing-list li {
    padding: 13px 0;
    border-top: 1px solid var(--line);
    color: var(--muted);
    font-size: 19px;
  }

  .closing-list li:last-child { border-bottom: 1px solid var(--line); }

  .next-step {
    position: absolute;
    left: 72px;
    right: 72px;
    bottom: 50px;
    padding-top: 20px;
    border-top: 5px solid var(--cyan);
    font-size: 25px;
    font-weight: 700;
  }

  .no-page::after { display: none; }
---

<!--
Fontes e direção visual:
- Referências visuais anexadas pelo usuário.
- https://slidestack.com/templates/category/technology
- https://plusai.com/templates/editorial
- Aula06_ProjetoTransformador_I.pdf, páginas 18–23: roteiro, demonstração e checklist.
As fotografias são imagens reais do dataset Project Sidewalk — Obstacles.
Nenhum asset visual externo foi usado.
-->

<!-- _class: no-page -->
<!-- _backgroundColor: #f7f8f5 -->

![bg right:52% cover](../../s/data/obstacles/crops/gsv-pittsburgh-16082-Obstacle.png)

<div class="cover">
  <div class="eyebrow">Projeto Transformador I · MVPv0</div>
  <h1>Transitabilidade<br>urbana</h1>
  <div class="rule"></div>
  <p class="subtitle">Avaliação de trechos por imagem para pessoas usuárias de cadeira de rodas</p>
  <p class="meta">Imagem · características · transitabilidade explicada</p>
</div>

---

<!-- _class: no-page -->

![bg left:42% cover](../../s/data/obstacles/crops/gsv-chicago-2844-Obstacle.png)

<div class="problem-copy">
  <div class="eyebrow">Problema e usuário</div>
  <p class="lead">Uma pessoa precisa saber<br>se o trecho urbano oferece<br>condições de passagem.</p>
  <p class="support">Uma imagem pode revelar barreiras que um mapa convencional não descreve.</p>
</div>

---

## Fluxo do MVPv0

<div class="pipeline">
  <div class="stage">
    <div class="stage-number">01</div>
    <h3>Imagem</h3>
    <p>Trecho urbano enviado ao pipeline.</p>
  </div>
  <div class="stage">
    <div class="stage-number">02</div>
    <h3>Análise visual</h3>
    <p>Pré-processamento e ResNet18 multilabel.</p>
  </div>
  <div class="stage">
    <div class="stage-number">03</div>
    <h3>Detecção</h3>
    <p>Probabilidades e threshold específico por label.</p>
  </div>
  <div class="stage">
    <div class="stage-number">04</div>
    <h3>Regra</h3>
    <p>Maior impacto entre as características detectadas.</p>
  </div>
  <div class="stage">
    <div class="stage-number">05</div>
    <h3>Resultado</h3>
    <p>Classe de transitabilidade e justificativa.</p>
  </div>
</div>

---

## Evidência técnica

<div class="evidence">
  <div class="evidence-left">
    <h3>Project Sidewalk — Obstacles</h3>
    <div class="split">
      <div><b>1.563</b><span>treino</span></div>
      <div><b>391</b><span>validação</span></div>
      <div><b>478</b><span>teste</span></div>
    </div>
    <p class="evidence-line"><strong>ResNet18</strong> pré-treinada no ImageNet</p>
    <p class="evidence-line">Fine-tuning multilabel · 7 características</p>
    <p class="evidence-line">Thresholds escolhidos somente na validação</p>
  </div>
  <div class="evidence-right">
    <p class="metric-label">Macro F1 no teste</p>
    <div class="metric-comparison">
      <div class="metric-block metric-old">
        <span class="metric-value">0.5604</span>
        <span class="metric-caption">threshold fixo 0.5</span>
      </div>
      <div class="metric-arrow">→</div>
      <div class="metric-block metric-new">
        <span class="metric-value">0.5914</span>
        <span class="metric-caption">thresholds calibrados</span>
      </div>
    </div>
    <div class="evidence-proof">
      <span>25 testes automatizados aprovados</span>
      <span>Entrada inválida → erro controlado</span>
    </div>
  </div>
</div>

---

## Três imagens, três resultados

<div class="demo-grid">
  <div class="demo-item">
    <img src="../../s/data/obstacles/crops/gsv-pittsburgh-15968-Obstacle.png" alt="Trecho com vegetação">
    <p class="demo-class">Transitável</p>
    <p class="demo-meta">vegetation · probabilidade 0.45</p>
  </div>
  <div class="demo-item">
    <img src="../../s/data/obstacles/crops/gsv-pittsburgh-2078-Obstacle.png" alt="Veículo estacionado">
    <p class="demo-class">Parcialmente transitável</p>
    <p class="demo-meta">parked-car · probabilidade 0.99</p>
  </div>
  <div class="demo-item">
    <img src="../../s/data/obstacles/crops/gsv-pittsburgh-7753-Obstacle.png" alt="Trecho em obra">
    <p class="demo-class">Não transitável</p>
    <p class="demo-meta">construction · probabilidade 0.94</p>
  </div>
</div>

---

## Heurística de transitabilidade

<p class="heuristic-intro">Regra demonstrativa do MVPv0. Ainda não é um critério definitivo de acessibilidade.</p>

<div class="impact-list">
  <div class="impact-row high">
    <div class="impact-level">Alto</div>
    <div class="impact-features">construction · height-difference</div>
    <div class="impact-result">→ NÃO TRANSITÁVEL</div>
  </div>
  <div class="impact-row moderate">
    <div class="impact-level">Moderado</div>
    <div class="impact-features">parked-car · pole · trash-recycling-can</div>
    <div class="impact-result">→ PARCIALMENTE TRANSITÁVEL</div>
  </div>
  <div class="impact-row low">
    <div class="impact-level">Baixo</div>
    <div class="impact-features">tree · vegetation</div>
    <div class="impact-result">→ TRANSITÁVEL</div>
  </div>
</div>

<div class="heuristic-note">
  <span><strong>Múltiplas características →</strong> prevalece o maior impacto.</span>
  <span><strong>Nenhuma detecção →</strong> Transitável.</span>
</div>

---

## Limites e próximo passo

<div class="closing">
  <div class="closing-column">
    <h3>O que já funciona</h3>
    <ul class="closing-list">
      <li>Inferência em imagem individual</li>
      <li>Threshold por característica</li>
      <li>Classe final + justificativa</li>
      <li>Entrada inválida → erro controlado</li>
    </ul>
  </div>
  <div class="closing-column">
    <h3>O que ainda falta medir</h3>
    <ul class="closing-list">
      <li>Largura livre para passagem</li>
      <li>Dimensão do obstáculo e do desnível</li>
      <li>Possibilidade de contornar a barreira</li>
      <li>Intensidade da vegetação</li>
    </ul>
  </div>
</div>

<p class="next-step">Próximo passo: incorporar critérios físicos para tornar a decisão mais objetiva.</p>
