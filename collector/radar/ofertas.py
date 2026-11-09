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
  * nota de aderência 0–100 (bloco `pontuacao` do JSON, mesmo modelo da versão anterior do
    Radar): aderência técnica (portfólio, suporte, fabricante, evidências) + urgência comercial
    (valor, estágio) multiplicada pelo fator técnico; tetos para "só família" e exclusão global;
    faixas Alta prioridade ≥ 80, Analisar 60–79, Potencial indireto 40–59, Baixa < 40;
  * familia_principal: família da oferta de maior peso; empate → menor 'ordem' da família;
  * exclusoes_globais: não descartam; nota limitada ao teto + selo "possível falso positivo";
  * portfólio: logo / mvs (podem coexistir) / transversal; pelo caminho de família,
    ibm_logo → logo e as demais → mvs; marcas no texto acrescentam logo/mvs.
  * disponivel_brasil fica no JSON só como informação: não gera selo nem aparece na interface.
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

# Peso de cada caminho só para ESCOLHER a oferta/família principal (a nota vem do bloco pontuacao)
PESO_EXATO = 3.0
PESO_MARCA_SERVICO = 2.0
PESO_FAMILIA = 2.0
FORCA_KEY = {"termo_exato": "exato", "marca_servico": "marca_servico", "familia": "familia"}

SELO_FALSO_POSITIVO = "possível falso positivo"

TIPO_SERVICO = {
    "suporte_manutencao": "Serviço de suporte/manutenção de infraestrutura",
    "software_suporte": "Suporte/subscrição de software de terceiros",
    "aquisicao_com_garantia": "Aquisição de hardware com garantia/suporte embutido",
    "aquisicao_hardware": "Aquisição de hardware (potencial de suporte futuro)",
    "infraestrutura_geral": "Contratação de infraestrutura de TIC (escopo a detalhar)",
}

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


def _num(d: dict, k: str, ctx: str) -> float:
    try:
        return float(d[k])
    except (KeyError, TypeError, ValueError):
        raise OfertasError(f"pontuacao.{ctx}{k} ausente ou não numérico") from None


@dataclass
class Pontuacao:
    """Parâmetros da nota (bloco `pontuacao` do JSON). Nenhum número da nota fica no código."""
    pesos: dict[str, float]
    forca: dict[str, float]
    fator_prioridade: dict[str, float]
    sup_fortes: list[Termo]
    sup_medios: list[Termo]
    sup_aquisicao: list[Termo]
    saturacao: float
    so_aquisicao: float
    alianca: list[Termo]
    fator_outras: float
    faixas_valor: list[tuple[float, float]]
    valor_desconhecido: float
    estagio: dict[str, float]
    fator_tecnico_pleno: float
    teto_so_familia: float
    teto_exclusao: float
    faixas: dict[str, float]
    rotulos: dict[str, str]

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Pontuacao":
        if not isinstance(d, dict):
            raise OfertasError("base de ofertas sem o bloco 'pontuacao' (parâmetros da nota de aderência)")
        pesos = {k: _num(d.get("pesos") or {}, k, "pesos.") for k in
                 ("portfolio", "suporte", "fabricante", "valor", "estagio", "evidencias")}
        forca = {k: _num(d.get("forca_portfolio") or {}, k, "forca_portfolio.") for k in ("exato", "marca_servico", "familia")}
        fp = {k: _num(d.get("fator_prioridade") or {}, k, "fator_prioridade.") for k in ("alta", "media", "baixa")}
        sup = d.get("suporte") or {}
        fab = d.get("fabricante") or {}
        tetos = d.get("tetos") or {}
        faixas = {k: _num(d.get("faixas") or {}, k, "faixas.") for k in ("alta", "analisar", "indireto")}
        bandas = sorted(((_num(b, "min", "faixas_valor[]."), _num(b, "fator", "faixas_valor[].")) for b in d.get("faixas_valor") or []),
                        reverse=True)
        if not bandas:
            raise OfertasError("pontuacao.faixas_valor vazio")
        return cls(
            pesos=pesos, forca=forca, fator_prioridade=fp,
            sup_fortes=_termos(sup.get("fortes")), sup_medios=_termos(sup.get("medios")),
            sup_aquisicao=_termos(sup.get("aquisicao")),
            saturacao=_num(sup, "saturacao", "suporte."), so_aquisicao=_num(sup, "so_aquisicao", "suporte."),
            alianca=_termos(fab.get("alianca")), fator_outras=_num(fab, "outras", "fabricante."),
            faixas_valor=bandas, valor_desconhecido=_num(d, "valor_desconhecido", ""),
            estagio={k: float(v) for k, v in (d.get("estagio") or {}).items()},
            fator_tecnico_pleno=_num(d, "fator_tecnico_pleno", ""),
            teto_so_familia=_num(tetos, "so_familia", "tetos."), teto_exclusao=_num(tetos, "exclusao_global", "tetos."),
            faixas=faixas,
            rotulos={k: str(v) for k, v in (d.get("rotulos") or {}).items()},
        )

    def faixa(self, nota: int) -> str:
        for k in ("alta", "analisar", "indireto"):
            if nota >= self.faixas[k]:
                return k
        return "baixa"

    def suporte(self, texto_norm: str) -> tuple[float, list[str], bool]:
        """Força de suporte (termos distintos; um termo mais longo consome o trecho dos
        mais curtos contidos nele: "manutenção corretiva" não conta também "manutenção")."""
        termos = sorted([(t, 1.0) for t in self.sup_fortes] + [(t, 0.5) for t in self.sup_medios],
                        key=lambda x: len(x[0].n), reverse=True)
        usado = bytearray(len(texto_norm))
        forca, achados = 0.0, []
        for t, w in termos:
            conta = False
            for m in t.rx.finditer(texto_norm):
                a, b = m.span()
                if any(usado[a:b]):
                    continue
                usado[a:b] = b"\x01" * (b - a)
                conta = True
            if conta:
                forca += w
                achados.append(t.original)
        aquisicao = bool(_achados(self.sup_aquisicao, texto_norm))
        return forca, achados, aquisicao


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


@dataclass
class BaseOfertas:
    versao: str
    ofertas: list[Oferta]
    exclusoes_globais: list[Termo]
    marcas_logo: list[Termo]
    marcas_mvs: list[Termo]
    familias: list[Familia] = field(default_factory=list)
    fonte: str = ""
    pontuacao: Pontuacao | None = None
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
            pontuacao=Pontuacao.from_dict(d.get("pontuacao")),
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

    def classificar(self, textos: Iterable[str | None], estagio: str | None = None, valor: float | None = None,
                    tem_itens: bool = False) -> dict[str, Any]:
        """Aplica as regras_de_match a um conjunto de textos (cada um avaliado isoladamente
        para marca + serviço e categoria + serviço) e calcula a nota de aderência 0–100 com o
        bloco `pontuacao` (estágio e valor entram na urgência comercial)."""
        normais = [n for n in (norm(t) for t in textos if t) if n]
        tudo = " | ".join(normais)
        casadas = self._casar_ofertas(normais)
        familias_casadas = {} if casadas else self._casar_familias(normais)

        if not casadas and not familias_casadas:
            # "só marca" não classifica (regras_de_match): fica só como sinal interno, usado
            # para decidir quais registros merecem a coleta de itens/documentos.
            return {"tls": False, "via": None, "ofertas_casadas": [], "familias_casadas": [], "familias": [],
                    "familia_principal": None, "score": None, "aderencia": None, "faixa": None,
                    "portfolio": [], "termos": [], "selos": [], "sinais": self.marcas_em(tudo),
                    "versao_ofertas": self.versao}

        P = self.pontuacao
        fprio = lambda prio: P.fator_prioridade.get(prio, P.fator_prioridade["baixa"])  # noqa: E731
        if casadas:
            via = "oferta"
            forca = lambda c: P.forca[FORCA_KEY[c["via"]]] * fprio(c["prioridade"])  # noqa: E731
            ordem = sorted(casadas.values(), key=lambda c: (-forca(c), -c["pontos"], self._ordem_familia(c["familia"]),
                                                            self.por_id[c["id"]].ordem_json))
            principal = ordem[0]
            familias = list(dict.fromkeys(c["familia"] for c in ordem if c["familia"]))
            kinds = {c["portfolio"] for c in ordem}
            termos = list(dict.fromkeys(t for c in ordem for t in c["termos"]))
            fam_lista: list[dict[str, Any]] = []
        else:
            via = "familia"
            forca = lambda f: P.forca["familia"] * fprio(f["prioridade"])  # noqa: E731
            fam_lista = sorted(familias_casadas.values(), key=lambda f: (-forca(f), self._ordem_familia(f["id"])))
            principal = fam_lista[0]
            familias = [f["id"] for f in fam_lista]
            kinds = {self.familia_por_id[f].portfolio_key for f in familias}
            termos = list(dict.fromkeys(t for f in fam_lista for t in f["termos"]))
            ordem = []

        excl = _achados(self.exclusoes_globais, tudo)
        marcas_logo = _achados(self.marcas_logo, tudo)
        marcas_mvs = _achados(self.marcas_mvs, tudo)
        alianca = _achados(P.alianca, tudo)
        fab_nomes = list(dict.fromkeys(alianca + marcas_logo + marcas_mvs))

        # ---- nota (modelo da versão anterior do Radar, parâmetros do JSON)
        W = P.pesos
        c_portfolio = W["portfolio"] * forca(principal)
        s_forca, s_termos, aquisicao = P.suporte(tudo)
        if s_forca > 0:
            c_suporte = W["suporte"] * min(1.0, s_forca / P.saturacao)
        else:
            c_suporte = W["suporte"] * (P.so_aquisicao if aquisicao else 0.0)
        f_fab = 1.0 if alianca else (P.fator_outras if (marcas_logo or marcas_mvs) else 0.0)
        c_fabricante = W["fabricante"] * f_fab
        tec_max = W["portfolio"] + W["suporte"] + W["fabricante"]
        fator_tecnico = min(1.0, (c_portfolio + c_suporte + c_fabricante) / tec_max / P.fator_tecnico_pleno)
        tem_valor = bool(valor and valor > 0)
        f_valor = next((f for m, f in P.faixas_valor if valor >= m), 0.0) if tem_valor else P.valor_desconhecido
        c_valor = W["valor"] * f_valor * fator_tecnico
        c_estagio = W["estagio"] * P.estagio.get(estagio or "", 0.5) * fator_tecnico
        evid = sum([via == "oferta", s_forca >= 0.5, bool(fab_nomes), bool(tem_itens), tem_valor])
        c_evid = W["evidencias"] * evid / 5
        total = c_portfolio + c_suporte + c_fabricante + c_valor + c_estagio + c_evid
        if via == "familia":
            total = min(total, P.teto_so_familia)
        if excl:
            total = min(total, P.teto_exclusao)
        nota = int(round(max(0.0, min(100.0, total))))
        faixa = P.faixa(nota)

        # ---- tipo de serviço e relação com o TLS (direta = suporte/manutenção/subscrição;
        # indireta = só aquisição, possível atuação via parceiro licitante)
        if s_forca >= 0.5:
            tipo = "software_suporte" if familias and familias[0] == "software_terceiros" else (
                "aquisicao_com_garantia" if aquisicao else "suporte_manutencao")
            relacao = "direta"
        elif aquisicao:
            tipo, relacao = "aquisicao_hardware", "indireta"
        else:
            tipo, relacao = "infraestrutura_geral", "a_validar"

        portfolio: list[str] = []
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

        fam_principal = familias[0] if familias else None
        nomes = [c["nome_pt"] for c in ordem]
        return {
            "tls": True,
            "via": via,
            "ofertas_casadas": [{k: v for k, v in c.items() if k not in ("prioridade", "pontos")} for c in ordem],
            "ofertas": nomes,
            "familias_casadas": [{k: v for k, v in f.items() if k not in ("prioridade", "pontos")} for f in fam_lista],
            "familias": familias,
            "familia_principal": fam_principal,
            "score": nota,
            "aderencia": nota,
            "faixa": faixa,
            "score_tecnico": int(round(100 * (c_portfolio + c_suporte + c_fabricante + c_evid) / (tec_max + W["evidencias"]))),
            "score_comercial": int(round(100 * (c_valor + c_estagio) / (W["valor"] + W["estagio"]))),
            "componentes": {k: round(v, 1) for k, v in (
                ("portfolio", c_portfolio), ("suporte", c_suporte), ("fabricante", c_fabricante),
                ("valor", c_valor), ("estagio", c_estagio), ("evidencias", c_evid))},
            "tipo_servico": tipo,
            "tipo_servico_label": TIPO_SERVICO[tipo],
            "relacao": relacao,
            "via_parceiro": relacao == "indireta",
            "justificativa": self._justificativa(via, nomes, fam_lista, termos, s_termos, fab_nomes, tipo, relacao, excl),
            "fabricantes": [{"nome": n, "alianca": n in alianca} for n in fab_nomes],
            "portfolio": portfolio,
            "termos": termos,
            "termos_suporte": s_termos,
            "marcas_portfolio": {"logo": marcas_logo, "mvs": marcas_mvs},
            "exclusoes_globais": excl,
            "selos": selos,
            "versao_ofertas": self.versao,
        }

    @staticmethod
    def _justificativa(via, nomes, fam_lista, termos, s_termos, fabricantes, tipo, relacao, excl) -> str:
        """Uma frase gerada SOMENTE com os termos encontrados no texto público."""
        marcas = {m.lower() for m in fabricantes}
        citados = [t for t in dict.fromkeys(list(termos) + list(s_termos)) if t.lower() not in marcas][:6]
        if via == "oferta":
            alvo = "/".join(nomes[:3])
        else:
            alvo = "família " + "/".join(f["nome"] for f in fam_lista[:2]) + " (sem oferta específica)"
        frase = f"Possível aderência a {alvo}"
        if citados:
            frase += ": objeto menciona " + ", ".join(f"“{t}”" for t in citados)
        if fabricantes:
            frase += "; fabricante(s): " + ", ".join(fabricantes[:4])
        partes = [frase + ".", TIPO_SERVICO[tipo] + "."]
        if relacao == "indireta":
            partes.append("Oportunidade indireta — possível atuação via parceiro licitante.")
        if excl:
            partes.append("O texto também cita itens fora do escopo TLS: " + ", ".join(excl[:5]) + ".")
        return " ".join(partes)


def portfolio_label(portfolio: list[str]) -> str:
    if "logo" in portfolio and "mvs" in portfolio:
        return "Logo IBM + MVS"
    if "logo" in portfolio:
        return "Logo IBM"
    if "mvs" in portfolio:
        return "MVS"
    return "Transversal" if portfolio else ""
