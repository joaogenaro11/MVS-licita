"""Classificador de ofertas TLS a partir da base de ofertas em JSON (`ofertas_tls_radar.json`).

A base de ofertas é PRIVADA: não fica no repositório público. Ela é lida, nesta ordem, de:
  1. variável de ambiente RADAR_OFERTAS_JSON (conteúdo JSON);
  2. variável de ambiente RADAR_OFERTAS_FILE (caminho do arquivo);
  3. config/ofertas_tls_radar.json (ignorado pelo git; uso local);
  4. Supabase (tabela public.radar_ofertas, id='atual'), quando SUPABASE_URL e
     SUPABASE_SERVICE_ROLE_KEY estão definidas (execução no GitHub Actions).

O JSON é a ÚNICA fonte de palavras-chave. Este módulo implementa exatamente o bloco
`regras_de_match` do arquivo:
  * normalização: minúsculas, sem acento, casamento por PALAVRA INTEIRA;
  * oferta casa se (a) aparece um termo de busca.termos_exatos, ou (b) aparece uma
    busca.marcas E um busca.termos_servico da oferta no MESMO texto (objeto, item, PCA).
    Ofertas sem termos_servico próprios só casam por (a). Termo de busca.excluir no mesmo
    texto impede o casamento da oferta naquele texto;
  * pontuação: termo exato = 3; marca + serviço = 2; x1,5 se prioridade "alta";
    soma das ofertas casadas;
  * exclusoes_globais: não descartam; pontuação pela metade + selo "possível falso positivo";
  * portfólio: logo / mvs (podem coexistir) / transversal;
  * disponibilidade: oferta com disponivel_brasil = "nao" gera o selo de oferta indisponível.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
LOCAL_FILE = ROOT / "config" / "ofertas_tls_radar.json"

PESO_EXATO = 3.0
PESO_MARCA_SERVICO = 2.0
MULT_ALTA = 1.5
FATOR_EXCLUSAO_GLOBAL = 0.5

SELO_FALSO_POSITIVO = "possível falso positivo"
SELO_INDISPONIVEL = "oferta indisponível no Brasil: ver alternativa"

PORTFOLIO_KEY = {"Logo IBM": "logo", "MVS": "mvs", "Transversal": "transversal"}


class OfertasError(RuntimeError):
    pass


# --------------------------------------------------------------------------- texto
def norm(text: str | None) -> str:
    """Minúsculas, sem acento; qualquer caractere não alfanumérico vira espaço."""
    out = []
    for ch in unicodedata.normalize("NFKD", text or ""):
        if unicodedata.combining(ch):
            continue
        ch = ch.lower()
        out.append(ch if ch.isalnum() else " ")
    return " ".join("".join(out).split())


class Termo:
    """Termo do JSON compilado para casamento por palavra inteira."""

    __slots__ = ("original", "n", "rx")

    def __init__(self, original: str):
        self.original = original
        self.n = norm(original)
        self.rx = re.compile(r"(?<![a-z0-9])" + re.escape(self.n) + r"(?![a-z0-9])") if self.n else None

    def em(self, texto_norm: str) -> bool:
        return bool(self.rx and self.rx.search(texto_norm))


def _termos(lista: Iterable[str] | None) -> list[Termo]:
    vistos, out = set(), []
    for t in lista or []:
        if not isinstance(t, str):
            continue
        tt = Termo(t)
        if tt.n and tt.n not in vistos:
            vistos.add(tt.n)
            out.append(tt)
    return out


def _achados(termos: list[Termo], texto_norm: str) -> list[str]:
    return [t.original for t in termos if t.em(texto_norm)]


# --------------------------------------------------------------------------- base
@dataclass
class Oferta:
    id: str
    nome_pt: str
    portfolio: str  # "Logo IBM" | "MVS" | "Transversal"
    prioridade: str
    disponivel_brasil: str
    regras: list[str]
    exatos: list[Termo]
    marcas: list[Termo]
    servicos: list[Termo]
    excluir: list[Termo]

    @property
    def portfolio_key(self) -> str:
        return PORTFOLIO_KEY.get(self.portfolio, "transversal")

    @property
    def alternativa(self) -> str:
        """Texto da alternativa (regras da oferta), para o selo de indisponibilidade."""
        alt = [r for r in self.regras if re.search(r"alternativ|em vez|no lugar|substitu|usar ", r, re.I)]
        return " ".join(alt or self.regras)


@dataclass
class BaseOfertas:
    versao: str
    ofertas: list[Oferta]
    exclusoes_globais: list[Termo]
    marcas_logo: list[Termo]
    marcas_mvs: list[Termo]
    fonte: str = ""
    por_id: dict[str, Oferta] = field(default_factory=dict)

    def __post_init__(self):
        self.por_id = {o.id: o for o in self.ofertas}

    # ------------------------------------------------------------------ carga
    @classmethod
    def from_dict(cls, d: dict[str, Any], fonte: str = "") -> "BaseOfertas":
        faltando = [k for k in ("ofertas", "exclusoes_globais", "marcas_logo", "marcas_mvs") if k not in d]
        if faltando:
            raise OfertasError(f"base de ofertas sem as chaves: {', '.join(faltando)}")
        ofertas = []
        ids = set()
        for i, o in enumerate(d["ofertas"]):
            if not o.get("id") or o["id"] in ids:
                raise OfertasError(f"oferta #{i} sem id ou com id duplicado: {o.get('id')!r}")
            ids.add(o["id"])
            if o.get("portfolio") not in PORTFOLIO_KEY:
                raise OfertasError(f"oferta {o['id']}: portfolio inválido {o.get('portfolio')!r}")
            b = o.get("busca") or {}
            ofertas.append(Oferta(
                id=o["id"],
                nome_pt=o.get("nome_pt") or o.get("nome_oficial") or o["id"],
                portfolio=o["portfolio"],
                prioridade=(o.get("prioridade") or "").lower(),
                disponivel_brasil=(o.get("disponivel_brasil") or "").lower(),
                regras=list(o.get("regras") or []),
                exatos=_termos(b.get("termos_exatos")),
                marcas=_termos(b.get("marcas")),
                servicos=_termos(b.get("termos_servico")),
                excluir=_termos(b.get("excluir")),
            ))
        return cls(
            versao=str(d.get("versao") or ""),
            ofertas=ofertas,
            exclusoes_globais=_termos(d.get("exclusoes_globais")),
            marcas_logo=_termos(d.get("marcas_logo")),
            marcas_mvs=_termos(d.get("marcas_mvs")),
            fonte=fonte,
        )

    @classmethod
    def load(cls, path: str | Path | None = None) -> "BaseOfertas | None":
        """Carrega a base privada. Retorna None se nenhuma fonte estiver configurada."""
        if path:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")), str(path))
        raw = os.environ.get("RADAR_OFERTAS_JSON", "").strip()
        if raw:
            return cls.from_dict(json.loads(raw), "env:RADAR_OFERTAS_JSON")
        fp = os.environ.get("RADAR_OFERTAS_FILE", "").strip()
        if fp:
            return cls.from_dict(json.loads(Path(fp).read_text(encoding="utf-8")), fp)
        if LOCAL_FILE.exists():
            return cls.from_dict(json.loads(LOCAL_FILE.read_text(encoding="utf-8")), str(LOCAL_FILE))
        if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            from .supa import fetch_ofertas  # import tardio: só no Actions
            d = fetch_ofertas()
            if d:
                return cls.from_dict(d, "supabase:radar_ofertas")
        return None

    def resumo_publico(self) -> dict[str, Any]:
        """Metadados mínimos para o site (nomes das ofertas para chips/filtros)."""
        return {
            "versao": self.versao,
            "ofertas": {o.id: {"nome_pt": o.nome_pt, "portfolio": o.portfolio_key} for o in self.ofertas},
        }

    def todos_termos(self) -> list[Termo]:
        """Termos que tornam um registro candidato (pré-filtro da coleta)."""
        out: dict[str, Termo] = {}
        for o in self.ofertas:
            for t in o.exatos + o.marcas:
                out.setdefault(t.n, t)
        for t in self.marcas_logo + self.marcas_mvs:
            out.setdefault(t.n, t)
        return list(out.values())

    def prefiltro(self) -> re.Pattern:
        alts = sorted({re.escape(t.n) for t in self.todos_termos()}, key=len, reverse=True)
        return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alts) + r")(?![a-z0-9])")

    def marcas_em(self, texto_norm: str) -> list[str]:
        vistos: dict[str, str] = {}
        for o in self.ofertas:
            for t in o.marcas:
                if t.n not in vistos and t.em(texto_norm):
                    vistos[t.n] = t.original
        for t in self.marcas_logo + self.marcas_mvs:
            if t.n not in vistos and t.em(texto_norm):
                vistos[t.n] = t.original
        return list(vistos.values())

    # ------------------------------------------------------------------ casamento
    def classificar(self, textos: Iterable[str | None]) -> dict[str, Any]:
        """Aplica as regras_de_match a um conjunto de textos (cada um avaliado isoladamente
        para marca + serviço). Retorna o resultado pronto para gravar no registro."""
        normais = [n for n in (norm(t) for t in textos if t) if n]
        casadas: dict[str, dict[str, Any]] = {}
        for o in self.ofertas:
            melhor = 0.0
            termos: list[str] = []
            via = None
            for tx in normais:
                if o.excluir and _achados(o.excluir, tx):
                    continue
                ex = _achados(o.exatos, tx)
                if ex:
                    termos += ex
                    if melhor < PESO_EXATO:
                        melhor, via = PESO_EXATO, "termo_exato"
                if o.servicos:
                    mc = _achados(o.marcas, tx)
                    if mc:
                        sv = _achados(o.servicos, tx)
                        if sv:
                            termos += mc + sv
                            if melhor < PESO_MARCA_SERVICO:
                                melhor, via = PESO_MARCA_SERVICO, "marca_servico"
            if melhor:
                pontos = melhor * (MULT_ALTA if o.prioridade == "alta" else 1.0)
                casadas[o.id] = {
                    "id": o.id,
                    "nome_pt": o.nome_pt,
                    "portfolio": o.portfolio_key,
                    "via": via,
                    "pontos": round(pontos, 2),
                    "termos": list(dict.fromkeys(termos)),
                }

        tudo = " | ".join(normais)
        if not casadas:
            # "só marca" não classifica (regras_de_match): fica só como sinal interno, usado
            # para decidir quais registros merecem a coleta de itens/documentos.
            return {"tls": False, "ofertas_casadas": [], "pontuacao": 0, "score": 0, "portfolio": [],
                    "termos": [], "selos": [], "sinais": self.marcas_em(tudo), "versao_ofertas": self.versao}

        portfolio: list[str] = []
        kinds = {c["portfolio"] for c in casadas.values()}
        marcas_logo = _achados(self.marcas_logo, tudo)
        marcas_mvs = _achados(self.marcas_mvs, tudo)
        if "logo" in kinds or marcas_logo:
            portfolio.append("logo")
        if "mvs" in kinds or marcas_mvs:
            portfolio.append("mvs")
        if not portfolio:
            portfolio = ["transversal"]

        pontuacao = sum(c["pontos"] for c in casadas.values())
        selos: list[dict[str, str]] = []
        excl = _achados(self.exclusoes_globais, tudo)
        if excl:
            pontuacao *= FATOR_EXCLUSAO_GLOBAL
            selos.append({"tipo": "falso_positivo", "texto": SELO_FALSO_POSITIVO,
                          "detalhe": "Termos de exclusão global: " + ", ".join(excl)})
        indisp = [self.por_id[i] for i in casadas if self.por_id[i].disponivel_brasil == "nao"]
        if indisp:
            selos.append({"tipo": "indisponivel_brasil", "texto": SELO_INDISPONIVEL,
                          "detalhe": " · ".join(f"{o.nome_pt}: {o.alternativa}" for o in indisp)})

        ordem = sorted(casadas.values(), key=lambda c: (-c["pontos"], c["nome_pt"]))
        termos = list(dict.fromkeys(t for c in ordem for t in c["termos"]))
        return {
            "tls": True,
            "ofertas_casadas": ordem,
            "ofertas": [c["nome_pt"] for c in ordem],
            "pontuacao": round(pontuacao, 2),
            "score": round(pontuacao, 2),
            "portfolio": portfolio,
            "termos": termos,
            "marcas_portfolio": {"logo": marcas_logo, "mvs": marcas_mvs},
            "exclusoes_globais": excl,
            "selos": selos,
            "versao_ofertas": self.versao,
        }


def portfolio_label(portfolio: list[str]) -> str:
    if "logo" in portfolio and "mvs" in portfolio:
        return "Logo IBM + MVS"
    if "logo" in portfolio:
        return "Logo IBM"
    if "mvs" in portfolio:
        return "MVS"
    return "Transversal" if portfolio else ""
