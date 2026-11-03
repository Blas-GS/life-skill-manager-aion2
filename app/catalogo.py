"""Access to the recipe and item catalog (data/catalogo.json).

Interface (docs/contratos.md, section 1):
    cat = cargar_catalogo()
    cat.objeto(id) -> dict | None
    cat.nombre(id) -> str
    cat.recetas_de(faccion) -> list[dict]
    cat.recetas_que_producen(id) -> list[dict]
    cat.buscar(texto, limite=10) -> list[(id, nombre, puntuacion)]

Extras (compatible with the contract): `buscar(..., faccion=...)`, `receta(id)`,
`recetas_que_usan(id)`, `prob_exito(receta, nivel)`, `prob_combo(receta, nivel)`.
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
        self.version_cliente: str | None = datos.get("version_cliente")

        self._recetas_por_id = {r["id"]: r for r in self.recetas}
        self._por_producto: dict[int, list[dict]] = {}
        self._por_ingrediente: dict[int, list[dict]] = {}
        for r in self.recetas:
            self._por_producto.setdefault(r["producto"], []).append(r)
            for ing, _ in r["ingredientes"]:
                self._por_ingrediente.setdefault(ing, []).append(r)

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

    def recetas_que_producen(self, id) -> list[dict]:
        return list(self._por_producto.get(int(id), []))

    def recetas_que_usan(self, id) -> list[dict]:
        return list(self._por_ingrediente.get(int(id), []))

    # --- probabilities -----------------------------------------------------
    def _valor_curva(self, curva: str | None, diferencia: int) -> float | None:
        if diferencia < 0:
            return None  # recipe locked
        if not curva:
            return 1.0
        valores = self.curvas.get(curva)
        if not valores:
            return 1.0
        return valores[min(diferencia, len(valores) - 1)] / 100.0

    def prob_exito(self, receta: dict, nivel: int) -> float | None:
        """Success probability (0–1) at mastery `nivel`; None if the recipe is locked.
        Curve index = nivel − nivel_receta, clamped to the last value."""
        return self._valor_curva(receta.get("curva"), nivel - receta.get("nivel", 0))

    def prob_combo(self, receta: dict, nivel: int) -> float:
        """Probability that a craft ends in a combo result:
        normal success × combo_pct × success of the combo craft."""
        if not receta.get("combo_pct"):
            return 0.0
        exito = self.prob_exito(receta, nivel)
        if exito is None:
            return 0.0
        exito_combo = self._valor_curva(receta.get("curva_combo"), nivel - receta.get("nivel", 0)) or 0.0
        return exito * receta["combo_pct"] / 100.0 * exito_combo

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
