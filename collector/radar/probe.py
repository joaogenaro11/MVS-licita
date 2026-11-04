"""Diagnóstico das fontes (executado no CI e manualmente).

Faz consultas pequenas e reais a cada endpoint usado pelo Radar e imprime:
status, total de registros, campos retornados e uma amostra. Serve para validar
o contrato da API antes/depois de mudanças e para detectar indisponibilidade.

Uso:  python -m radar probe [--days 2]
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from typing import Any

from .pncp import CONSULTA_BASE, PNCPClient, SourceError


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


def _show(title: str, fn) -> Any:
    print(f"\n=== {title}")
    try:
        payload = fn()
    except SourceError as exc:
        print(f"  ERRO: {exc} (status={exc.status}) url={exc.url}")
        return None
    except Exception as exc:  # noqa: BLE001 - diagnóstico
        print(f"  ERRO inesperado: {type(exc).__name__}: {exc}")
        return None
    if payload is None:
        print("  HTTP 204 / sem conteúdo")
        return None
    if isinstance(payload, dict):
        meta = {k: payload.get(k) for k in ("totalRegistros", "totalPaginas", "numeroPagina", "paginasRestantes", "empty")}
        print(f"  envelope: {meta}")
        rows = payload.get("data") or []
    else:
        rows = payload
    print(f"  linhas nesta página: {len(rows)}")
    if rows:
        first = rows[0]
        if isinstance(first, dict):
            print(f"  campos: {sorted(first.keys())}")
            print("  amostra: " + json.dumps(first, ensure_ascii=False)[:1500])
    return payload


def run(days: int = 2) -> int:
    c = PNCPClient(max_attempts=3)
    today = date.today()
    ini = _fmt(today - timedelta(days=days))
    fim = _fmt(today)
    p10 = {"pagina": 1, "tamanhoPagina": 10}

    pub = _show("contratacoes/publicacao (pregão eletrônico=6)", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratacoes/publicacao",
        dict(p10, dataInicial=ini, dataFinal=fim, codigoModalidadeContratacao=6)))
    _show("contratacoes/publicacao tamanhoPagina=50", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratacoes/publicacao",
        dict(pagina=1, tamanhoPagina=50, dataInicial=ini, dataFinal=fim, codigoModalidadeContratacao=6)))
    _show("contratacoes/atualizacao (6)", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratacoes/atualizacao",
        dict(p10, dataInicial=ini, dataFinal=fim, codigoModalidadeContratacao=6)))
    _show("contratacoes/proposta (6, dataFinal=+30d)", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratacoes/proposta",
        dict(p10, dataFinal=_fmt(today + timedelta(days=30)), codigoModalidadeContratacao=6)))
    _show("contratacoes/proposta sem modalidade", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratacoes/proposta",
        dict(p10, dataFinal=_fmt(today + timedelta(days=30)))))

    # Semântica do filtro de vigência das atas
    atas_hoje = _show("atas (dataInicial=dataFinal=hoje) -> semântica de vigência", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/atas", dict(p10, dataInicial=fim, dataFinal=fim)))
    if atas_hoje and isinstance(atas_hoje, dict):
        for r in (atas_hoje.get("data") or [])[:10]:
            print(f"   vigencia {r.get('vigenciaInicio')} -> {r.get('vigenciaFim')} assin={r.get('dataAssinatura')} pub={r.get('dataPublicacaoPncp')}")
    _show("atas/atualizacao", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/atas/atualizacao", dict(p10, dataInicial=ini, dataFinal=fim)))
    _show("contratos", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratos", dict(p10, dataInicial=ini, dataFinal=fim)))
    _show("contratos/atualizacao", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/contratos/atualizacao", dict(p10, dataInicial=ini, dataFinal=fim)))
    _show("pca/atualizacao", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/pca/atualizacao", dict(p10, dataInicio=ini, dataFim=fim)))
    _show("pca/ (anoPca=2026, sem classificação)", lambda: c.get_json(
        f"{CONSULTA_BASE}/v1/pca/", dict(p10, anoPca=2026)))

    # Detalhe/itens/arquivos da primeira contratação encontrada
    rows = (pub or {}).get("data") or [] if isinstance(pub, dict) else []
    if rows:
        r = rows[0]
        cnpj = (r.get("orgaoEntidade") or {}).get("cnpj")
        ano, seq = r.get("anoCompra"), r.get("sequencialCompra")
        print(f"\n--- compra de amostra: {r.get('numeroControlePNCP')} cnpj={cnpj} ano={ano} seq={seq}")
        print(f"    linkSistemaOrigem={r.get('linkSistemaOrigem')!r} linkProcessoEletronico={r.get('linkProcessoEletronico')!r}")
        _show("detalhe compra (consulta)", lambda: c.compra_detalhe(cnpj, ano, seq))
        _show("itens (api pncp)", lambda: c.get_json(
            f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens", {"pagina": 1, "tamanhoPagina": 5}))
        _show("arquivos (api pncp)", lambda: c.get_json(
            f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"))
        # Distribuição de domínios de linkSistemaOrigem
        from collections import Counter
        from urllib.parse import urlparse
        dom = Counter(urlparse(x.get("linkSistemaOrigem") or "").netloc or "(vazio)" for x in rows)
        print(f"    domínios linkSistemaOrigem (amostra): {dict(dom)}")

    if atas_hoje and isinstance(atas_hoje, dict) and atas_hoje.get("data"):
        a = atas_hoje["data"][0]
        print(f"\n--- ata de amostra: {a.get('numeroControlePNCPAta')} compra={a.get('numeroControlePNCPCompra')}")

    print("\nestatísticas do cliente:", c.stats.as_dict())
    return 0


if __name__ == "__main__":
    sys.exit(run())
