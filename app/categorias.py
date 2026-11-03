"""Categoría visual de cada objeto del catálogo (para elegir su icono propio en la interfaz).

El catálogo no trae categoría: se deduce del nombre del archivo de icono de metabot.gg
(p. ej. `icon_wp_gs_…` = arma, `icon_acc_ring_…` = joya, `icon_gm_…_torso` = armadura)
y de palabras del nombre en español. Las claves coinciden con ICONOS_CATEGORIA de
app/static/iconos.js.
"""
from __future__ import annotations

import re
import unicodedata

CATEGORIAS = ("mineral", "gema", "madera", "hierba", "carne", "escama", "esencia", "cristal", "condimento",
              "herramienta", "pocion", "comida", "pergamino", "piedra", "refinamiento", "arma", "armadura",
              "joya", "otro")

# (categoría, palabras) — se prueban en este orden; la primera que aparezca en el nombre gana.
_REGLAS: list[tuple[str, tuple[str, ...]]] = [
    ("pergamino", ("pergamino", "hoja de papel")),
    ("refinamiento", ("piedra de refinamiento",)),
    ("piedra", ("piedra de mana", "piedra de alma")),
    ("cristal", ("piedra espiritual", "cristal", " od ")),
    ("pocion", ("pocion", "elixir")),
    ("esencia", ("esencia", " ira ", "catalizador", "disolvente", "aceite", "endurecedor", "suavizante", "tinta")),
    ("herramienta", ("martillo", "balanza", "lupa", "tela de fabricante", "abrasivo", "papel de lija", "frasco")),
    ("gema", ("diamante", "rubi", "zafiro")),
    ("mineral", ("mineral", "lingote", "orichalcum")),
    ("madera", ("tronco", "madera")),
    ("condimento", (" sal ", "pimienta", "curry", "salsa", "queso", "mantequilla", "fideos", "condimento")),
    ("escama", ("cuerno", "cuero", "escama")),
    ("carne", ("carne", "okra", "kukuru")),
]
_GUISOS = ("asado", "guiso", "pasta", "frituras", "macedonia", "filete", "solomillo")


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return f" {re.sub(r'[^a-z0-9]+', ' ', t).strip()} "


def categoria(objeto: dict | None) -> str:
    """Categoría de un objeto del catálogo (dict con al menos `nombre` e `icono`)."""
    if not objeto:
        return "otro"
    icono = (objeto.get("icono") or "").lower()
    if "/icon_wp_" in icono or "icon_weapon_" in icono:
        return "arma"
    if "/icon_acc_" in icono:
        return "joya"
    if "/icon_gm_" in icono:
        return "armadura"
    nombre = _normal(objeto.get("nombre") or objeto.get("nombre_en") or "")
    if any(f" {p}" in nombre for p in _GUISOS):
        return "comida"
    for cat, palabras in _REGLAS:
        if any(p in nombre for p in palabras):
            return cat
    if "icon_item_gather" in icono or "icon_item_currency" in icono:
        return "hierba"
    if "icon_item_usable" in icono:
        return "comida"
    return "otro"


def mapa_categorias(objetos: dict) -> dict[str, str]:
    """{id (str): categoría} para todos los objetos del catálogo."""
    return {str(oid): categoria(o) for oid, o in (objetos or {}).items()}
