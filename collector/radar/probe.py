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


def run(days: int = 2, only_pca: bool = False) -> int:
    c = PNCPClient(max_attempts=2, timeout=40)
    today = date.today()
    ini = _fmt(today - timedelta(days=days))
    fim = _fmt(today)
    p10 = {"pagina": 1, "tamanhoPagina": 10}
    if only_pca:
        probe_pca(c, today)
        probe_app_routes(c)
        print("\nestatísticas do cliente:", c.stats.as_dict())
        return 0

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

    if isinstance(atas_hoje, dict) and atas_hoje.get("data"):
        a_ctrl = atas_hoje["data"][0].get("numeroControlePNCPAta") or ""
        try:
            cnpj_a, rest = a_ctrl.split("-1-")
            seq_c, rest2 = rest.split("/")
            ano_c, seq_a = rest2.split("-")
            base_a = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj_a}/compras/{ano_c}/{int(seq_c)}/atas/{int(seq_a)}"
            _show("ata detalhe (api pncp)", lambda: c.get_json(base_a))
            _show("ata arquivos (api pncp)", lambda: c.get_json(base_a + "/arquivos"))
        except ValueError:
            print(f"  numeroControlePNCPAta em formato inesperado: {a_ctrl!r}")

    probe_app_routes(c)
    print("\nestatísticas do cliente:", c.stats.as_dict())
    return 0


def probe_app_routes(c: PNCPClient) -> None:
    """Confirma a estrutura real dos links do portal PNCP (/app/editais, /app/atas,
    /app/contratos, /app/pca) lendo as rotas declaradas no bundle da aplicação."""
    import re
    print("\n=== rotas do portal https://pncp.gov.br/app/")
    try:
        import requests
        sess = requests.Session()
        r = sess.get("https://pncp.gov.br/app/editais", timeout=40, headers={"Accept": "text/html"})
        print(f"  HTTP {r.status_code}, {len(r.text)} bytes")
        scripts = re.findall(r'src="([^"]+\.js)"', r.text)
        found: set[str] = set()
        for s in scripts:
            url = s if s.startswith("http") else "https://pncp.gov.br/app/" + s.lstrip("/")
            js = sess.get(url, timeout=60).text
            for m in re.finditer(r'path:\s*["\']([^"\']*(?:editais|atas|contratos|pca|contratacoes)[^"\']*)["\']', js):
                found.add(m.group(1))
        for p in sorted(found):
            print(f"  rota: {p}")
        if not found:
            print(f"  nenhuma rota encontrada nos scripts: {scripts[:8]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ERRO: {type(exc).__name__}: {exc}")


def probe_pca(c: PNCPClient, today: date, pages: int = 60) -> None:
    """Descobre os códigos de classificação (CATMAT/CATSER) dos itens de PCA aderentes ao
    TLS, para consultar /v1/pca/ apenas nessas classes (muito menos requisições)."""
    from collections import Counter
    from pathlib import Path
    from .classifier import Portfolio, classify
    pf = Portfolio.load(Path(__file__).resolve().parents[2] / "config", private="")
    # janela de 1 dia e páginas pequenas: janelas maiores excedem o tempo de resposta do PNCP
    ini = fim = _fmt(today - timedelta(days=1))
    c.timeout = 120
    for size in (10, 50):
        _show(f"pca/atualizacao tamanhoPagina={size}", lambda: c.get_json(
            f"{CONSULTA_BASE}/v1/pca/atualizacao", dict(pagina=1, tamanhoPagina=size, dataInicio=ini, dataFim=fim)))
    rel: Counter = Counter()
    allc: Counter = Counter()
    exemplos: dict = {}
    n_items = 0
    for page in range(1, pages + 1):
        try:
            payload = c.get_json(f"{CONSULTA_BASE}/v1/pca/atualizacao",
                                 dict(pagina=page * 97, tamanhoPagina=10, dataInicio=ini, dataFim=fim))
        except SourceError as exc:
            print(f"  página {page * 97}: ERRO {exc}")
            continue
        for pca in (payload or {}).get("data") or []:
            for it in pca.get("itens") or []:
                n_items += 1
                key = (it.get("classificacaoSuperiorCodigo"), it.get("classificacaoSuperiorNome"), it.get("categoriaItemPcaNome"))
                allc[key] += 1
                if classify(pf, [it.get("descricaoItem") or ""])["score"] >= 40:
                    rel[key] += 1
                    exemplos.setdefault(key, (it.get("descricaoItem") or "")[:140])
        print(f"  amostra página {page * 97}: itens acumulados={n_items}", flush=True)
    print(f"\n  itens analisados: {n_items}; classes com itens aderentes (score>=40):")
    for k, v in rel.most_common(40):
        print(f"     {v:4d}/{allc[k]:5d}  codigo={k[0]!r} nome={k[1]!r} categoria={k[2]!r}  ex: {exemplos[k]!r}")
    print("\n  classes de TIC por nome (todas):")
    for k, v in allc.most_common():
        nome = (k[1] or "").upper()
        if any(w in nome for w in ("INFORM", "PROCESSAMENTO", "TECNOLOGIA", "COMUNICA", "REDE", "TIC", "COMPUTA", "SOFTWARE", "DADOS")):
            print(f"     {v:5d}  codigo={k[0]!r} nome={k[1]!r} categoria={k[2]!r}")
    if rel:
        code = rel.most_common(1)[0][0][0]
        _show(f"pca/ anoPca=2026 codigoClassificacaoSuperior={code}", lambda: c.get_json(
            f"{CONSULTA_BASE}/v1/pca/", dict(pagina=1, tamanhoPagina=50, anoPca=2026, codigoClassificacaoSuperior=code)))
        _show(f"pca/ anoPca=2027 codigoClassificacaoSuperior={code}", lambda: c.get_json(
            f"{CONSULTA_BASE}/v1/pca/", dict(pagina=1, tamanhoPagina=50, anoPca=2027, codigoClassificacaoSuperior=code)))

if __name__ == "__main__":
    sys.exit(run())
