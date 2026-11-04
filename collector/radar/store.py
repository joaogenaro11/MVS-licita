"""Armazenamento em JSON versionado (branch `data`), com escrita atômica e
salvaguardas contra perda de dados.

Arquivos:
  items.json   — contratações, itens de PCA e contratos relevantes (dedup por id oficial)
  atas.json    — atas de registro de preços relevantes
  state.json   — cursores/checkpoints de cada fonte
  meta.json    — status da última execução (lido pela interface)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    pass


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dump_lines(data: dict, fh) -> None:
    """JSON válido com um registro por linha: compacto e com diffs pequenos no git."""
    head = {k: v for k, v in data.items() if k != "items"}
    if head:
        fh.write(json.dumps(head, ensure_ascii=False)[:-1] + ', "items": [\n')
    else:
        fh.write('{"items": [\n')
    items = data.get("items") or []
    for i, it in enumerate(items):
        fh.write(json.dumps(it, ensure_ascii=False, separators=(",", ":")))
        fh.write(",\n" if i < len(items) - 1 else "\n")
    fh.write("]}\n")


def write_json_atomic(path: Path, data: Any, compact: bool = False, lines: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if lines and isinstance(data, dict) and "items" in data:
                _dump_lines(data, fh)
            elif compact:
                json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=False)
            fh.flush()
            os.fsync(fh.fileno())
        # valida o que foi escrito antes de substituir o arquivo anterior
        with open(tmp, encoding="utf-8") as fh:
            json.load(fh)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.items: dict[str, dict] = {}
        self.atas: dict[str, dict] = {}
        self.state: dict[str, Any] = {}
        self.meta: dict[str, Any] = {}
        self._loaded_counts = (0, 0)

    def load(self) -> "Store":
        items = read_json(self.dir / "items.json", {"items": []})
        atas = read_json(self.dir / "atas.json", {"items": []})
        self.items = {i["id"]: i for i in items.get("items", [])}
        self.atas = {a["id"]: a for a in atas.get("items", [])}
        self.state = read_json(self.dir / "state.json", {})
        self.meta = read_json(self.dir / "meta.json", {})
        self._loaded_counts = (len(self.items), len(self.atas))
        return self

    # ---------------------------------------------------------------- upsert
    def upsert(self, coll: dict[str, dict], new: dict, now_iso: str) -> str:
        """Insere ou atualiza (dedup pelo identificador oficial). Preserva campos
        de enriquecimento e o primeiro registro de coleta. Retorna 'new'|'updated'|'same'."""
        old = coll.get(new["id"])
        if old is None:
            new["coletado_em"] = now_iso
            new["atualizado_em"] = now_iso
            coll[new["id"]] = new
            return "new"
        merged = dict(old)
        changed = False
        for k, v in new.items():
            if k == "feeds":
                feeds = sorted(set(old.get("feeds", [])) | set(v))
                if feeds != old.get("feeds"):
                    merged["feeds"] = feeds
                continue
            if k in ("fornecedores", "contratos_adesao") and old.get(k):
                continue  # enriquecido em outra etapa
            if k == "links":
                links = dict(old.get("links") or {})
                for lk, lv in (v or {}).items():
                    if lv or lk not in links:
                        links[lk] = lv
                if links != old.get("links"):
                    merged["links"] = links
                    changed = True
                continue
            if v is None and old.get(k) is not None and k.startswith(("valor", "data_", "vigencia")):
                continue  # nunca apaga um valor oficial conhecido por ausência na resposta
            if old.get(k) != v:
                merged[k] = v
                changed = True
        if new.get("data_atualizacao_fonte") and new.get("data_atualizacao_fonte") != old.get("data_atualizacao_fonte"):
            merged["enriquecido_em"] = None  # força novo enriquecimento
        if changed:
            merged["atualizado_em"] = now_iso
        coll[new["id"]] = merged
        return "updated" if changed else "same"

    # ------------------------------------------------------------------ save
    def save(self, generated_at: str) -> None:
        n_items, n_atas = len(self.items), len(self.atas)
        prev_items, prev_atas = self._loaded_counts
        # Salvaguarda: a base nunca encolhe (registros não são apagados).
        if n_items < prev_items or n_atas < prev_atas:
            raise StoreError(f"base encolheria ({prev_items}->{n_items} itens, {prev_atas}->{n_atas} atas); abortando")
        write_json_atomic(self.dir / "items.json", {"schema": SCHEMA_VERSION, "generated_at": generated_at,
                                                     "items": sorted(self.items.values(), key=lambda x: x["id"])}, lines=True)
        write_json_atomic(self.dir / "atas.json", {"schema": SCHEMA_VERSION, "generated_at": generated_at,
                                                    "items": sorted(self.atas.values(), key=lambda x: x["id"])}, lines=True)
        self.save_state()
        write_json_atomic(self.dir / "meta.json", self.meta)

    def save_state(self) -> None:
        write_json_atomic(self.dir / "state.json", self.state)
