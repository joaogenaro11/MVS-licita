"""Bases comerciais PRIVADAS (ficam no Supabase, tabela radar_bases; nunca no repositório):

* atestados  — atestados de capacidade técnica, declarações e cartas de fabricante. Para cada
  oportunidade: nível "atende" (o atestado cobre o objeto) ou "proximo" (mesma categoria, não 100%).
  Cada regra é uma lista de grupos de termos; casa quando cada grupo tem ao menos um termo no MESMO
  texto (objeto, item, PCA), por palavra inteira e sem acento — o mesmo casamento da base de ofertas.
* territorios — carteira de clientes por vendedor (TLS BSB Seller / Renewal Seller). A oportunidade
  recebe o território da conta cujo nome casa com o órgão (ou a unidade compradora), na mesma UF
  quando há homônimos. Contas com CNPJ entram na varredura por órgão.

O resultado vai dentro de `classificacao` (privada: não vai para a branch pública `data`).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .ofertas import Termo, _achados, norm

ROOT = Path(__file__).resolve().parents[2]
NIVEIS = ("atende", "proximo")


def _carregar(nome: str, env_json: str, env_file: str) -> tuple[dict | None, str]:
    raw = os.environ.get(env_json, "").strip()
    if raw:
        return json.loads(raw), f"env:{env_json}"
    fp = os.environ.get(env_file, "").strip()
    if fp:
        return json.loads(Path(fp).read_text(encoding="utf-8")), fp
    local = ROOT / "config" / f"{nome}.json"
    if local.exists():
        return json.loads(local.read_text(encoding="utf-8")), str(local)
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        from .supa import fetch_base
        d = fetch_base(nome)
        if d:
            return d, f"supabase:radar_bases/{nome}"
    return None, ""


# ------------------------------------------------------------------ atestados
Regra = list[list[Termo]]


def _regras(raw: Iterable[Iterable[Iterable[str]]] | None) -> list[Regra]:
    out = []
    for regra in raw or []:
        grupos = [[Termo(t) for t in grupo if isinstance(t, str) and norm(t)] for grupo in regra]
        if grupos and all(grupos):
            out.append(grupos)
    return out


def _casa(regra: Regra, texto_norm: str) -> list[str] | None:
    achados: list[str] = []
    for grupo in regra:
        a = _achados(grupo, texto_norm)
        if not a:
            return None
        achados += a
    return achados


@dataclass
class Atestado:
    id: str
    titulo: str
    tipo: str
    emissor: str
    titular: str
    escopo: str
    data: str
    atende: list[Regra]
    proximo: list[Regra]


@dataclass
class BaseAtestados:
    versao: str
    atestados: list[Atestado]
    fonte: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any], fonte: str = "") -> "BaseAtestados":
        lista = []
        for i, a in enumerate(d.get("atestados") or []):
            if not a.get("id"):
                raise ValueError(f"atestado #{i} sem id")
            lista.append(Atestado(id=a["id"], titulo=a.get("titulo") or a["id"], tipo=a.get("tipo") or "",
                                  emissor=a.get("emissor") or "", titular=a.get("titular") or "",
                                  escopo=a.get("escopo") or "", data=a.get("data") or "",
                                  atende=_regras(a.get("atende")), proximo=_regras(a.get("proximo"))))
        return cls(versao=str(d.get("versao") or ""), atestados=lista, fonte=fonte)

    @classmethod
    def load(cls) -> "BaseAtestados | None":
        d, fonte = _carregar("atestados", "RADAR_ATESTADOS_JSON", "RADAR_ATESTADOS_FILE")
        return cls.from_dict(d, fonte) if d else None

    def avaliar(self, textos: Iterable[str | None]) -> dict[str, Any]:
        """Melhor nível por atestado, avaliando cada texto isoladamente."""
        normais = [n for n in (norm(t) for t in textos if t) if n]
        lista = []
        for a in self.atestados:
            melhor, termos = None, []
            for tx in normais:
                for nivel, regras in (("atende", a.atende), ("proximo", a.proximo)):
                    if melhor == "atende" or (melhor == "proximo" and nivel == "proximo"):
                        continue
                    for regra in regras:
                        achou = _casa(regra, tx)
                        if achou:
                            if melhor != nivel:
                                termos = []
                            melhor = nivel
                            termos += achou
                            break
            if melhor:
                lista.append({"id": a.id, "titulo": a.titulo, "tipo": a.tipo, "emissor": a.emissor,
                              "titular": a.titular, "nivel": melhor, "termos": list(dict.fromkeys(termos))[:8]})
        lista.sort(key=lambda x: (NIVEIS.index(x["nivel"]), x["titulo"]))
        nivel = lista[0]["nivel"] if lista else None
        return {"nivel": nivel, "lista": lista, "versao": self.versao}


# ---------------------------------------------------------------- territórios
def chave(nome: str | None) -> str:
    """Nome sem acento, sem espaços nem pontuação (a planilha corta nomes e quebra palavras)."""
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


# nomes genéricos demais para identificar uma conta
GENERICOS = {chave(x) for x in ("UNIAO FEDERAL", "UNIO FEDERAL", "PRESIDENCIA DA REPUBLICA", "GOVERNO FEDERAL",
                                 "ESTADO", "MUNICIPIO", "PREFEITURA MUNICIPAL")}
MIN_PREFIXO = 22   # nomes da planilha cortados: casa por prefixo só a partir deste tamanho


@dataclass
class BaseTerritorios:
    versao: str
    contas: list[dict[str, Any]]
    fonte: str = ""
    _idx: dict[str, list[dict]] = field(default_factory=dict)
    _pref: dict[str, list[dict]] = field(default_factory=dict)
    _cnpj: dict[str, list[dict]] = field(default_factory=dict)

    def __post_init__(self):
        for c in self.contas:
            for cnpj in c.get("cnpjs") or []:
                self._cnpj.setdefault(cnpj, []).append(c)
            for nome in c.get("nomes") or []:
                k = chave(nome)
                if len(k) < 6 or k in GENERICOS:
                    continue
                self._idx.setdefault(k, []).append(c)
                if len(k) >= MIN_PREFIXO:
                    self._pref.setdefault(k[:MIN_PREFIXO], []).append((k, c))

    @classmethod
    def from_dict(cls, d: dict[str, Any], fonte: str = "") -> "BaseTerritorios":
        return cls(versao=str(d.get("versao") or ""), contas=list(d.get("contas") or []), fonte=fonte)

    @classmethod
    def load(cls) -> "BaseTerritorios | None":
        d, fonte = _carregar("territorios", "RADAR_TERRITORIOS_JSON", "RADAR_TERRITORIOS_FILE")
        return cls.from_dict(d, fonte) if d else None

    def cnpjs(self) -> list[dict[str, str]]:
        vistos, out = set(), []
        for c in self.contas:
            for cnpj in c.get("cnpjs") or []:
                if cnpj not in vistos:
                    vistos.add(cnpj)
                    out.append({"cnpj": cnpj, "nome": (c.get("nomes") or [cnpj])[0], "grupo": "Carteira (territórios)"})
        return out

    def _candidatos(self, nome: str | None) -> list[dict]:
        k = chave(nome)
        if len(k) < 6 or k in GENERICOS:
            return []
        if k in self._idx:
            return self._idx[k]
        if len(k) >= MIN_PREFIXO:   # nome da planilha cortado: o do órgão começa com ele
            return [c for kk, c in self._pref.get(k[:MIN_PREFIXO], []) if k.startswith(kk) or kk.startswith(k)]
        return []

    def territorio(self, rec: dict) -> dict[str, Any] | None:
        orgao, unidade = rec.get("orgao") or {}, rec.get("unidade") or {}
        uf = unidade.get("uf")
        cnpj = orgao.get("cnpj")
        cands: list[dict] = []
        if cnpj:
            cands = list(self._cnpj.get(cnpj, []))
        for nome in (orgao.get("nome"), unidade.get("nome")):
            if cands:
                break
            cands = self._candidatos(nome)
        if not cands:
            return None
        mesma_uf = [c for c in cands if c.get("uf") == uf] if uf else []
        usar = mesma_uf or cands
        donos = {(c.get("bsb"), c.get("renovacao")) for c in usar}
        if len(donos) > 1 and not mesma_uf:
            return None   # homônimos em UFs diferentes, sem conta na UF do órgão: não arrisca
        # mais de uma conta na mesma UF: fica com a mais frequente
        cont: dict[tuple, int] = {}
        for c in usar:
            cont[(c.get("bsb"), c.get("renovacao"))] = cont.get((c.get("bsb"), c.get("renovacao")), 0) + 1
        bsb, ren = max(cont, key=cont.get)
        conta = next(c for c in usar if (c.get("bsb"), c.get("renovacao")) == (bsb, ren))
        return {"bsb": bsb, "renovacao": ren, "conta": (conta.get("nomes") or [""])[0], "uf": conta.get("uf"),
                "via": "cnpj" if cnpj and cnpj in (conta.get("cnpjs") or []) else "nome"}
