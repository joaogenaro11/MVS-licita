"""Avaliação OPCIONAL (local): regras vs. similaridade semântica com embeddings open-source.

Não faz parte do pipeline automático. Requer:  pip install sentence-transformers

Uso:
  python collector/tools/avaliar_embeddings.py rotulos.csv [--modelo intfloat/multilingual-e5-small]

rotulos.csv: colunas `texto,relevante` (1 = oportunidade relevante para TLS, 0 = não).
Imprime precisão/recall/F1 do classificador por regras (score >= limiar) e do re-ranqueamento
semântico (similaridade com descrições das ofertas >= limiar ajustado no próprio conjunto).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "collector"))

from radar.classifier import Portfolio, classify  # noqa: E402


def prf(pred: list[bool], gold: list[bool]) -> tuple[float, float, float]:
    tp = sum(p and g for p, g in zip(pred, gold))
    fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--modelo", default="intfloat/multilingual-e5-small")
    ap.add_argument("--limiar-regras", type=int, default=40)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    textos = [r["texto"] for r in rows]
    gold = [r["relevante"].strip() in ("1", "true", "sim") for r in rows]
    pf = Portfolio.load(ROOT / "config")
    regras = [classify(pf, [t])["score"] >= args.limiar_regras for t in textos]
    print(f"n={len(rows)} relevantes={sum(gold)}")
    print("regras      P=%.2f R=%.2f F1=%.2f" % prf(regras, gold))

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers não instalado; avaliação semântica ignorada.")
        return 0
    model = SentenceTransformer(args.modelo)
    protos = [f"query: {o['label']}: {o.get('description', '')} " + ", ".join(o.get("strong", [])[:25])
              for o in pf.raw["offers"].values()]
    pe = model.encode(protos, normalize_embeddings=True)
    te = model.encode([f"query: {t}" for t in textos], normalize_embeddings=True, batch_size=64, show_progress_bar=True)
    sims = (te @ pe.T).max(axis=1)
    best = max(((prf([s >= th for s in sims], gold)[2], th) for th in [x / 100 for x in range(60, 95)]))
    th = best[1]
    sem = [s >= th for s in sims]
    print("semântico   P=%.2f R=%.2f F1=%.2f (limiar %.2f ajustado no próprio conjunto — otimista)" % (*prf(sem, gold), th))
    uniao = [a or b for a, b in zip(regras, sem)]
    print("regras+sem  P=%.2f R=%.2f F1=%.2f" % prf(uniao, gold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
