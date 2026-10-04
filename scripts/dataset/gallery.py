"""Geração de galeria HTML local para revisão visual do dataset."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Sequence

from .inspection import DatasetReport, PositiveExample


def _example_card(
    example: PositiveExample,
    image_directory: Path,
    selected_label: str,
) -> str:
    image_uri = (image_directory / example.filename).resolve().as_uri()
    labels = "".join(
        f'<span class="label{" selected" if label == selected_label else ""}">'
        f"{escape(label)}</span>"
        for label in example.positive_labels
    )
    return f"""
      <article class="card">
        <img src="{escape(image_uri)}" alt="{escape(example.filename)}" loading="lazy">
        <div class="content">
          <strong>{escape(example.filename)}</strong>
          <div class="coords">
            x={escape(example.normalized_x)} · y={escape(example.normalized_y)}
          </div>
          <div class="labels">{labels}</div>
        </div>
      </article>"""


def create_gallery(
    reports: Sequence[DatasetReport],
    labels: Sequence[str],
    output_path: str | Path,
    *,
    limit: int = 8,
) -> Path:
    """Cria uma galeria HTML somente com exemplos positivos das labels pedidas."""

    if limit <= 0:
        raise ValueError("O limite de exemplos deve ser maior que zero")
    if not labels:
        raise ValueError("Informe ao menos uma label para criar a galeria")

    sections: list[str] = []
    for report in reports:
        if report.image_directory is None:
            raise ValueError(f"Diretório de imagens não definido para {report.path}")
        for label in labels:
            examples = report.positive_examples.get(label, [])[:limit]
            cards = "".join(
                _example_card(example, report.image_directory, label)
                for example in examples
            )
            if not cards:
                cards = '<p class="empty">Nenhum exemplo positivo encontrado.</p>'
            sections.append(
                f"<section><h2>{escape(report.path.name)} · {escape(label)}</h2>"
                f'<p class="summary">{len(report.positive_examples.get(label, []))} '
                f"amostras positivas; exibindo até {limit}.</p>"
                f'<div class="grid">{cards}</div></section>'
            )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Exemplos positivos do dataset</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin-bottom: 32px; }}
    section {{ margin-bottom: 48px; }}
    h2 {{ margin-bottom: 4px; }}
    .summary, .coords {{ color: #777; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 18px;
    }}
    .card {{
      border: 1px solid #9996;
      border-radius: 10px;
      overflow: hidden;
      background: #8881;
    }}
    img {{ width: 100%; aspect-ratio: 4 / 3; object-fit: cover; display: block; }}
    .content {{ padding: 12px; }}
    strong {{ overflow-wrap: anywhere; }}
    .coords {{ margin: 6px 0 10px; font-family: ui-monospace, monospace; }}
    .labels {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .label {{
      border: 1px solid #8888;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 0.8rem;
    }}
    .label.selected {{ background: #2563eb; border-color: #2563eb; color: white; }}
    .empty {{ padding: 20px; border: 1px dashed #999; }}
  </style>
</head>
<body>
  <h1>Exemplos positivos do dataset</h1>
  {''.join(sections)}
</body>
</html>
"""
    destination.write_text(document, encoding="utf-8")
    return destination.resolve()

