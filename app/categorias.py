"""Visual category of every catalog object (used to pick its own icon in the UI).

The catalog has no category field: it is inferred from the metabot.gg icon file name
(e.g. `icon_wp_gs_…` = weapon, `icon_acc_ring_…` = jewel, `icon_gm_…_torso` = armor)
and from words in the Spanish name. The keys match ICONOS_CATEGORIA in
app/static/iconos.js.
"""
from __future__ import annotations

import re
import unicodedata

CATEGORIAS = ("mineral", "gema", "madera", "hierba", "carne", "escama", "esencia", "cristal", "condimento",
              "herramienta", "pocion", "comida", "pergamino", "piedra", "refinamiento", "arma", "armadura",
              "joya", "otro")

# (category, words) — tried in this order; the first one found in the name wins.
# The words are Spanish because they are matched against the Spanish object name.
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
    """Category of a catalog object (a dict with at least `nombre` and `icono`)."""
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
    """{id (str): category} for every catalog object."""
    return {str(oid): categoria(o) for oid, o in (objetos or {}).items()}
