"""Access to the recipe and item catalog (data/catalogo.json).

Interface:
    cat = cargar_catalogo()
    cat.objeto(id) -> dict | None
    cat.nombre(id) -> str
    cat.receta(id) -> dict | None
    cat.recetas_de(faccion) -> list[dict]
    cat.recetas_que_producen(id, con_combo=False) -> list[dict]
    cat.es_intermedio(id) -> bool
    cat.buscar(texto, limite=10, faccion=None) -> list[(id, nombre, puntuacion)]
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

RUTA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "data" / "catalogo.json"

_ALIAS_FACCION = {
    "elyos": "elyos", "elios": "elyos", "e": "elyos",
    "asmodian": "asmodian", "asmodians": "asmodian", "asmodiano": "asmodian",
    "asmodianos": "asmodian", "asmo": "asmodian", "a": "asmodian",
    "ambas": "ambas",
}


def normalizar(texto: str) -> str:
    """Lowercase, no accents and single spaces (for comparing names)."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.lower().split())


def normalizar_faccion(faccion: str | None) -> str | None:
    if faccion is None:
        return None
    clave = normalizar(faccion)
    if clave not in _ALIAS_FACCION:
        raise ValueError(f"Facción desconocida: {faccion!r} (usa 'elyos' o 'asmodian')")
    return _ALIAS_FACCION[clave]


class Catalogo:
    def __init__(self, datos: dict):
        self.datos = datos
        self.objetos: dict[str, dict] = datos["objetos"]
        self.recetas: list[dict] = datos["recetas"]
        self.curvas: dict[str, list[float]] = datos.get("curvas", {})
        self.profesiones: dict[str, str] = datos.get("profesiones", {})
        self.meta = {k: datos.get(k) for k in ("fuente", "version_cliente", "generado")}

        self._recetas_por_id = {r["id"]: r for r in self.recetas}
        self._por_producto: dict[int, list[dict]] = {}
        self._con_combo: dict[int, list[dict]] = {}  # also recipes whose combo yields the item
        self._ingredientes: set[int] = set()
        for r in self.recetas:
            self._por_producto.setdefault(r["producto"], []).append(r)
            self._con_combo.setdefault(r["producto"], []).append(r)
            if r.get("producto_combo"):
                self._con_combo.setdefault(r["producto_combo"], []).append(r)
            self._ingredientes.update(ing for ing, _ in r["ingredientes"])

        # search index: one entry per (id, normalized ES/EN name)
        self._claves: list[tuple[int, str]] = []
        self._textos: list[str] = []
        for k, o in self.objetos.items():
            for n in {o.get("nombre"), o.get("nombre_en")}:
                if n:
                    self._claves.append((int(k), o.get("nombre") or n))
                    self._textos.append(normalizar(n))

    # --- items -------------------------------------------------------------
    def objeto(self, id) -> dict | None:
        return self.objetos.get(str(id))

    def nombre(self, id) -> str:
        o = self.objeto(id)
        return o["nombre"] if o else f"#{id}"

    # --- recipes -----------------------------------------------------------
    def receta(self, id) -> dict | None:
        return self._recetas_por_id.get(int(id))

    def recetas_de(self, faccion: str | None) -> list[dict]:
        """Recipes that faction can craft (includes those marked 'ambas').
        With faccion=None returns all of them."""
        f = normalizar_faccion(faccion)
        if f is None or f == "ambas":
            return list(self.recetas)
        return [r for r in self.recetas if r["faccion"] in (f, "ambas")]

    def recetas_que_producen(self, id, con_combo: bool = False) -> list[dict]:
        """Recipes whose main product is `id` (with `con_combo`, also those whose combo yields it).
        The returned list is shared: do not modify it."""
        return (self._con_combo if con_combo else self._por_producto).get(int(id), [])

    def es_intermedio(self, id) -> bool:
        """True if the item is an ingredient of some recipe."""
        return int(id) in self._ingredientes

    def nombre_profesion(self, clave) -> str:
        return self.profesiones.get(clave) or str(clave or "")

    # --- search ------------------------------------------------------------
    def buscar(self, texto: str, limite: int = 10, faccion: str | None = None) -> list[tuple[int, str, float]]:
        """Fuzzy search by name (ES or EN), ignoring accents and case.
        Returns [(id, nombre, puntuacion 0–100)] sorted from best to worst.
        With `faccion`, items exclusive to the other faction are discarded."""
        consulta = normalizar(texto)
        if not consulta:
            return []
        f = normalizar_faccion(faccion)
        resultados = process.extract(consulta, self._textos, scorer=fuzz.WRatio,
                                     limit=max(limite * 6, 30), score_cutoff=50)
        mejores: dict[int, tuple[float, str, str]] = {}
        for _, puntuacion, idx in resultados:
            oid, nombre = self._claves[idx]
            texto_idx = self._textos[idx]
            if texto_idx == consulta:
                puntuacion = 100.0
            if f and f != "ambas":
                fo = self.objetos[str(oid)].get("faccion")
                if fo and fo not in (f, "ambas"):
                    continue
            previo = mejores.get(oid)
            if previo is None or puntuacion > previo[0]:
                mejores[oid] = (float(puntuacion), nombre, texto_idx)
        orden = sorted(mejores.items(), key=lambda kv: (-kv[1][0], len(kv[1][2]), kv[0]))
        return [(oid, nombre, round(p, 1)) for oid, (p, nombre, _) in orden[:limite]]


@lru_cache(maxsize=4)
def _cargar(ruta: str, mtime: float) -> Catalogo:
    with open(ruta, encoding="utf-8") as f:
        return Catalogo(json.load(f))


def cargar_catalogo(ruta: str | Path | None = None) -> Catalogo:
    """Loads data/catalogo.json (or `ruta`). Cached as long as the file does not change."""
    p = Path(ruta) if ruta else RUTA_POR_DEFECTO
    if not p.exists():
        raise FileNotFoundError(
            f"No existe {p}. Genera el catálogo con: .\\.venv\\Scripts\\python.exe tools\\importar_metabot.py")
    return _cargar(str(p.resolve()), p.stat().st_mtime)
