"""Linha de comando do Radar TLS.

  python -m radar probe                  # diagnóstico das fontes (consultas reais pequenas)
  python -m radar update --data-dir ../data [--budget-min 60]
                                         # coleta incremental + avanço da carga histórica
  python -m radar reclassify --data-dir ../data
                                         # reaplica o classificador (após editar config/)
  python -m radar export --data-dir ../data --out ../web/public/data
                                         # gera os JSON públicos consumidos pelo site
  python -m radar sample --days 3        # coleta real limitada, imprime as melhores oportunidades
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="diagnóstico das fontes")
    p.add_argument("--days", type=int, default=2)
    p.add_argument("--pca", action="store_true", help="apenas diagnóstico do PCA")

    u = sub.add_parser("update", help="coleta incremental e histórica")
    u.add_argument("--data-dir", type=Path, required=True)
    u.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)
    u.add_argument("--budget-min", type=float, default=None, help="tempo máximo de coleta (minutos)")
    u.add_argument("--no-backfill", action="store_true")

    r = sub.add_parser("reclassify", help="reaplica classificação sobre os dados existentes")
    r.add_argument("--data-dir", type=Path, required=True)
    r.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)

    e = sub.add_parser("export", help="gera os arquivos públicos do site")
    e.add_argument("--data-dir", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)

    s = sub.add_parser("sample", help="coleta real limitada e imprime ranking (não grava)")
    s.add_argument("--days", type=int, default=3)
    s.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)
    s.add_argument("--max-pages", type=int, default=20)
    s.add_argument("--top", type=int, default=40)
    s.add_argument("--out", type=Path, default=None, help="grava a amostra em JSON (para inspeção)")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "probe":
        from .probe import run
        return run(days=args.days, only_pca=args.pca)
    if args.cmd == "update":
        from .pipeline import run_update
        return run_update(args.data_dir, args.config_dir, budget_min=args.budget_min,
                          backfill=not args.no_backfill)
    if args.cmd == "reclassify":
        from .pipeline import run_reclassify
        return run_reclassify(args.data_dir, args.config_dir)
    if args.cmd == "export":
        from .pipeline import export_site
        print(export_site(args.data_dir, args.out, args.config_dir))
        return 0
    if args.cmd == "sample":
        from .pipeline import run_sample
        return run_sample(args.config_dir, days=args.days, max_pages=args.max_pages, top=args.top, out=args.out)
    return 2


if __name__ == "__main__":
    sys.exit(main())
