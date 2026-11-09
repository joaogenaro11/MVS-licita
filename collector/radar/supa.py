"""Acesso ao Supabase pelo coletor (somente no GitHub Actions, com a chave de serviço).

O Supabase guarda o que NÃO pode ir para o repositório público:
  * public.radar_ofertas  — base de ofertas TLS (JSON privado), id = 'atual';
  * public.radar_export   — dados classificados exibidos no site (lidos só após login).

Variáveis de ambiente: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY (secret do repositório).
A chave nunca é impressa nem gravada.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

PARTE_MAX_BYTES = 1_500_000  # cada linha de radar_export guarda ~1,5 MB de JSON


class SupabaseError(RuntimeError):
    pass


def _cfg() -> tuple[str, dict[str, str]]:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise SupabaseError("SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY não definidas")
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # chave legada (JWT): o gateway também exige Authorization
        headers["Authorization"] = f"Bearer {key}"
    return url, headers


def _check(r: requests.Response, what: str) -> None:
    if r.status_code >= 300:
        raise SupabaseError(f"{what}: HTTP {r.status_code} {r.text[:300]}")


def fetch_ofertas() -> dict[str, Any] | None:
    url, h = _cfg()
    r = requests.get(f"{url}/rest/v1/radar_ofertas", params={"id": "eq.atual", "select": "data"}, headers=h, timeout=60)
    _check(r, "leitura da base de ofertas")
    rows = r.json()
    return rows[0]["data"] if rows else None


def _partes(items: list[dict]) -> list[list[dict]]:
    partes: list[list[dict]] = [[]]
    tam = 0
    for it in items:
        n = len(json.dumps(it, ensure_ascii=False, separators=(",", ":")).encode())
        if partes[-1] and tam + n > PARTE_MAX_BYTES:
            partes.append([])
            tam = 0
        partes[-1].append(it)
        tam += n
    return partes


def publicar_export(export_dir: Path) -> dict[str, int]:
    """Envia opportunities.json, atas.json e meta.json para public.radar_export.
    Grava todas as partes novas e só então apaga as partes excedentes da versão anterior."""
    url, h = _cfg()
    d = Path(export_dir)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    gerado = meta.get("gerado_em")
    resumo: dict[str, int] = {}
    for nome, arq in (("oportunidades", "opportunities.json"), ("atas", "atas.json")):
        items = json.loads((d / arq).read_text(encoding="utf-8")).get("items") or []
        partes = _partes(items)
        rows = [{"nome": nome, "parte": i, "gerado_em": gerado, "data": {"items": p}} for i, p in enumerate(partes)]
        for row in rows:  # uma requisição por parte (limita o tamanho de cada envio)
            r = requests.post(f"{url}/rest/v1/radar_export", params={"on_conflict": "nome,parte"},
                              headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                              data=json.dumps([row], ensure_ascii=False).encode(), timeout=180)
            _check(r, f"envio de {nome} parte {row['parte']}")
        r = requests.delete(f"{url}/rest/v1/radar_export", params={"nome": f"eq.{nome}", "parte": f"gte.{len(rows)}"},
                            headers={**h, "Prefer": "return=minimal"}, timeout=60)
        _check(r, f"limpeza de {nome}")
        resumo[nome] = len(items)
    r = requests.post(f"{url}/rest/v1/radar_export", params={"on_conflict": "nome,parte"},
                      headers={**h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                      data=json.dumps([{"nome": "meta", "parte": 0, "gerado_em": gerado, "data": meta}], ensure_ascii=False).encode(),
                      timeout=60)
    _check(r, "envio de meta")
    return resumo
