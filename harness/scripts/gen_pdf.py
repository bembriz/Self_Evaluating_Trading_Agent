#!/usr/bin/env python3
"""Convierte un reporte Markdown a PDF (PRD §75: PDF al solicitar cierre de fase).

Dependencias (dev): markdown, weasyprint — requieren Dependency Proposal autorizada
(ver skill infra-control). Sin ellas, este script aborta con instrucciones.

Uso: gen_pdf.py docs/phases/phase-00-report.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CSS_STYLES = """
@page { size: A4; margin: 2cm; }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 10pt; line-height: 1.45; }
h1 { font-size: 16pt; border-bottom: 2px solid #333; padding-bottom: 4px; }
h2 { font-size: 13pt; margin-top: 18px; border-bottom: 1px solid #999; }
pre { background: #f5f5f5; border: 1px solid #ddd; padding: 8px;
      font-size: 8.5pt; white-space: pre-wrap; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.5pt; background: #f5f5f5; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border: 1px solid #999; padding: 4px 6px; text-align: left; font-size: 9pt; }
th { background: #eee; }
blockquote { color: #555; border-left: 3px solid #bbb; padding-left: 10px; }
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gen-pdf", description=__doc__)
    parser.add_argument("entrada", help="ruta del .md")
    parser.add_argument("-o", "--salida", default=None)
    args = parser.parse_args(argv)

    try:
        import markdown
        from weasyprint import CSS, HTML
    except ImportError as exc:
        print(
            "ERROR: faltan dependencias para PDF.\n"
            f"Detalle: {exc}\n\n"
            "Este script requiere los dev-dependencies 'markdown' y 'weasyprint'.\n"
            "Su instalación está sujeta a la política de dependencias del proyecto:\n"
            "1) Genera/usa el Dependency Proposal correspondiente (skill infra-control).\n"
            "2) Tras tu autorización: uv add --dev markdown weasyprint\n"
            "3) Reintenta este comando.",
            file=sys.stderr,
        )
        return 65

    entrada = Path(args.entrada)
    if not entrada.exists():
        print(f"No existe {entrada}", file=sys.stderr)
        return 66
    texto = entrada.read_text(encoding="utf-8")
    html = markdown.markdown(texto, extensions=["tables", "fenced_code"])
    documento = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"</head><body>{html}</body></html>"
    )
    salida = Path(args.salida) if args.salida else entrada.with_suffix(".pdf")
    HTML(string=documento).write_pdf(salida, stylesheets=[CSS(string=CSS_STYLES)])
    print(f"PDF generado: {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
