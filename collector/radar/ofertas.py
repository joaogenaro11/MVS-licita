"""Classificador de ofertas TLS a partir da base de ofertas em JSON (`ofertas_tls_radar.json`).

A base de ofertas é PRIVADA: não fica no repositório público. Ela é lida, nesta ordem, de:
  1. variável de ambiente RADAR_OFERTAS_JSON (conteúdo JSON);
  2. variável de ambiente RADAR_OFERTAS_FILE (caminho do arquivo);
  3. config/ofertas_tls_radar.json (ignorado pelo git; uso local);
  4. Supabase (tabela public.radar_ofertas, id='atual'), quando SUPABASE_URL e
     SUPABASE_SERVICE_ROLE_KEY estão definidas (execução no GitHub Actions).

O JSON é a ÚNICA fonte de palavras-chave. Este módulo implementa o bloco `regras_de_match`:
  * normalização: minúsculas, sem acento, casamento por PALAVRA INTEIRA;
  * oferta casa se (a) aparece um termo de busca.termos_exatos, ou (b) aparece uma
    busca.marcas E um busca.termos_servico da oferta no MESMO texto (objeto, item, PCA).
    Ofertas sem termos_servico próprios só casam por (a). Termo de busca.excluir no mesmo
    texto impede o casamento da oferta naquele texto;
  * caminho_familia (c): se NENHUMA oferta casou, uma família casa quando aparecem um
    termo_categoria E um termo_servico dela no mesmo texto, sem termo de excluir;
  * aderencia: pontos = soma(exato 3; marca+serviço 2; família 2) × 1,5 se a oferta (ou
    família) principal tiver prioridade alta; +1 se tocar 2 ou mais famílias; × 0,5 com
    exclusão global. Aderência 0–100 = min(100, round(pontos / 6 × 100));
    faixas Alta ≥ 70, Média 40–69, Baixa < 40;
  * familia_principal: família da oferta de maior peso; empate → menor 'ordem' da família;
  * exclusoes_globais: não descartam; pontuação pela metade + selo "possível falso positivo";
  * portfólio: logo / mvs (podem coexistir) / transversal; pelo caminho de família,
    ibm_logo → logo e as demais → mvs; marcas no texto acrescentam logo/mvs;
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
PESO_FAMILIA = 2.0
MULT_ALTA = 1.5
BONUS_MULTIFAMILIA = 1.0
FATOR_EXCLUSAO_GLOBAL = 0.5
PONTOS_PARA_100 = 6.0
FAIXAS = (("alta", 70), ("media", 40), ("baixa", 0))

SELO_FALSO_POSITIVO = "possível falso positivo"
SELO_INDISPONIVEL = "oferta indisponível no Brasil: ver alternativa"

PORTFOLIO_KEY = {"Logo IBM": "logo", "MVS": "mvs", "Transversal": "transversal"}
FAMILIA_LOGO = "ibm_logo"


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


def aderencia_de(pontos: float) -> tuple[int, str]:
    ader = int(min(100, round(pontos / PONTOS_PARA_100 * 100)))
    faixa = next(nome for nome, minimo in FAIXAS if ader >= minimo)
    return ader, faixa


# --------------------------------------------------------------------------- base
@dataclass
class Familia:
    id: str
    nome: str
    ordem: int
    prioridade: str
    descricao: str
    categorias: list[Termo]
    servicos: list[Termo]
    excluir: list[Termo]

    @property
    def portfolio_key(self) -> str:
        return "logo" if self.id == FAMILIA_LOGO else "mvs"


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
    familia: str | None = None
    ordem_json: int = 0

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
    familias: list[Familia] = field(default_factory=list)
    fonte: str = ""
    por_id: dict[str, Oferta] = field(default_factory=dict)
    familia_por_id: dict[str, Familia] = field(default_factory=dict)

    def __post_init__(self):
        self.por_id = {o.id: o for o in self.ofertas}
        self.familias = sorted(self.familias, key=lambda f: f.ordem)
        self.familia_por_id = {f.id: f for f in self.familias}

    # ------------------------------------------------------------------ carga
    @classmethod
    def from_dict(cls, d: dict[str, Any], fonte: str = "") -> "BaseOfertas":
        faltando = [k for k in ("ofertas", "exclusoes_globais", "marcas_logo", "marcas_mvs") if k not in d]
        if faltando:
            raise OfertasError(f"base de ofertas sem as chaves: {', '.join(faltando)}")
        familias = []
        for i, f in enumerate(d.get("familias") or []):
            if not f.get("id"):
                raise OfertasError(f"família #{i} sem id")
            familias.append(Familia(
                id=f["id"], nome=f.get("nome") or f["id"], ordem=int(f.get("ordem") or 99),
                prioridade=(f.get("prioridade") or "").lower(), descricao=f.get("descricao") or "",
                categorias=_termos(f.get("termos_categoria")), servicos=_termos(f.get("termos_servico")),
                excluir=_termos(f.get("excluir")),
            ))
        fam_ids = {f.id for f in familias}
        ofertas = []
        ids = set()
        for i, o in enumerate(d["ofertas"]):
            if not o.get("id") or o["id"] in ids:
                raise OfertasError(f"oferta #{i} sem id ou com id duplicado: {o.get('id')!r}")
            ids.add(o["id"])
            if o.get("portfolio") not in PORTFOLIO_KEY:
                raise OfertasError(f"oferta {o['id']}: portfolio inválido {o.get('portfolio')!r}")
            if familias and o.get("familia") not in fam_ids:
                raise OfertasError(f"oferta {o['id']}: família inexistente {o.get('familia')!r}")
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
                familia=o.get("familia"),
                ordem_json=i,
            ))
        return cls(
            versao=str(d.get("versao") or ""),
            ofertas=ofertas,
            exclusoes_globais=_termos(d.get("exclusoes_globais")),
            marcas_logo=_termos(d.get("marcas_logo")),
            marcas_mvs=_termos(d.get("marcas_mvs")),
            familias=familias,
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
        """Metadados mínimos para o site (nomes das ofertas e das famílias)."""
        return {
            "versao": self.versao,
            "ofertas": {o.id: {"nome_pt": o.nome_pt, "portfolio": o.portfolio_key, "familia": o.familia} for o in self.ofertas},
            "familias": [{"id": f.id, "nome": f.nome, "ordem": f.ordem, "prioridade": f.prioridade} for f in self.familias],
        }

    def todos_termos(self) -> list[Termo]:
        """Termos que tornam um registro candidato (pré-filtro da coleta)."""
        out: dict[str, Termo] = {}
        for o in self.ofertas:
            for t in o.exatos + o.marcas:
                out.setdefault(t.n, t)
        for f in self.familias:
            for t in f.categorias:
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

    def _ordem_familia(self, fid: str | None) -> int:
        f = self.familia_por_id.get(fid or "")
        return f.ordem if f else 99

    # ------------------------------------------------------------------ casamento
    def _casar_ofertas(self, normais: list[str]) -> dict[str, dict[str, Any]]:
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
                fam = self.familia_por_id.get(o.familia or "")
                casadas[o.id] = {
                    "id": o.id,
                    "nome_pt": o.nome_pt,
                    "portfolio": o.portfolio_key,
                    "familia": o.familia,
                    "familia_nome": fam.nome if fam else None,
                    "prioridade": o.prioridade,
                    "via": via,
                    "pontos": melhor,
                    "termos": list(dict.fromkeys(termos)),
                }
        return casadas

    def _casar_familias(self, normais: list[str]) -> dict[str, dict[str, Any]]:
        casadas: dict[str, dict[str, Any]] = {}
        for f in self.familias:
            if not f.categorias or not f.servicos:
                continue
            termos: list[str] = []
            for tx in normais:
                if f.excluir and _achados(f.excluir, tx):
                    continue
                cat = _achados(f.categorias, tx)
                if cat:
                    sv = _achados(f.servicos, tx)
                    if sv:
                        termos += cat + sv
            if termos:
                casadas[f.id] = {"id": f.id, "nome": f.nome, "prioridade": f.prioridade, "pontos": PESO_FAMILIA,
                                 "termos": list(dict.fromkeys(termos))}
        return casadas

    def classificar(self, textos: Iterable[str | None]) -> dict[str, Any]:
        """Aplica as regras_de_match a um conjunto de textos (cada um avaliado isoladamente
        para marca + serviço e categoria + serviço). Retorna o resultado para o registro."""
        normais = [n for n in (norm(t) for t in textos if t) if n]
        tudo = " | ".join(normais)
        casadas = self._casar_ofertas(normais)
        familias_casadas = {} if casadas else self._casar_familias(normais)

        if not casadas and not familias_casadas:
            # "só marca" não classifica (regras_de_match): fica só como sinal interno, usado
            # para decidir quais registros merecem a coleta de itens/documentos.
            return {"tls": False, "via": None, "ofertas_casadas": [], "familias_casadas": [], "familias": [],
                    "familia_principal": None, "pontuacao": 0, "aderencia": 0, "faixa": None, "score": 0,
                    "portfolio": [], "termos": [], "selos": [], "sinais": self.marcas_em(tudo),
                    "versao_ofertas": self.versao}

        if casadas:
            via = "oferta"
            peso = lambda c: c["pontos"] * (MULT_ALTA if c["prioridade"] == "alta" else 1.0)  # noqa: E731
            ordem = sorted(casadas.values(), key=lambda c: (-peso(c), self._ordem_familia(c["familia"]),
                                                            self.por_id[c["id"]].ordem_json))
            principal = ordem[0]
            familias = list(dict.fromkeys(c["familia"] for c in ordem if c["familia"]))
            soma = sum(c["pontos"] for c in ordem)
            alta = principal["prioridade"] == "alta"
            kinds = {c["portfolio"] for c in ordem}
            termos = list(dict.fromkeys(t for c in ordem for t in c["termos"]))
            fam_lista: list[dict[str, Any]] = []
        else:
            via = "familia"
            peso = lambda f: f["pontos"] * (MULT_ALTA if f["prioridade"] == "alta" else 1.0)  # noqa: E731
            fam_lista = sorted(familias_casadas.values(), key=lambda f: (-peso(f), self._ordem_familia(f["id"])))
            principal = fam_lista[0]
            familias = [f["id"] for f in fam_lista]
            soma = sum(f["pontos"] for f in fam_lista)
            alta = principal["prioridade"] == "alta"
            kinds = {self.familia_por_id[f].portfolio_key for f in familias}
            termos = list(dict.fromkeys(t for f in fam_lista for t in f["termos"]))
            ordem = []

        pontos = soma * (MULT_ALTA if alta else 1.0)
        if len(familias) >= 2:
            pontos += BONUS_MULTIFAMILIA
        excl = _achados(self.exclusoes_globais, tudo)
        if excl:
            pontos *= FATOR_EXCLUSAO_GLOBAL
        aderencia, faixa = aderencia_de(pontos)

        portfolio: list[str] = []
        marcas_logo = _achados(self.marcas_logo, tudo)
        marcas_mvs = _achados(self.marcas_mvs, tudo)
        if "logo" in kinds or marcas_logo:
            portfolio.append("logo")
        if "mvs" in kinds or marcas_mvs:
            portfolio.append("mvs")
        if not portfolio:
            portfolio = ["transversal"]

        selos: list[dict[str, str]] = []
        if excl:
            selos.append({"tipo": "falso_positivo", "texto": SELO_FALSO_POSITIVO,
                          "detalhe": "Termos de exclusão global: " + ", ".join(excl)})
        indisp = [self.por_id[c["id"]] for c in ordem if self.por_id[c["id"]].disponivel_brasil == "nao"]
        if indisp:
            selos.append({"tipo": "indisponivel_brasil", "texto": SELO_INDISPONIVEL,
                          "detalhe": " · ".join(f"{o.nome_pt}: {o.alternativa}" for o in indisp)})

        fam_principal = familias[0] if familias else None
        return {
            "tls": True,
            "via": via,
            "ofertas_casadas": [{k: v for k, v in c.items() if k != "prioridade"} for c in ordem],
            "ofertas": [c["nome_pt"] for c in ordem],
            "familias_casadas": [{k: v for k, v in f.items() if k != "prioridade"} for f in fam_lista],
            "familias": familias,
            "familia_principal": fam_principal,
            "pontuacao": round(pontos, 2),
            "aderencia": aderencia,
            "faixa": faixa,
            "score": aderencia,
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
