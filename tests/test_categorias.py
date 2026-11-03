"""Categoría de icono de cada objeto (app/categorias.py) y su coherencia con app/static/iconos.js."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.categorias import CATEGORIAS, categoria, mapa_categorias

URL = "https://metabot.gg/web/aion2/items/"


@pytest.mark.parametrize("nombre, icono, esperada", [
    ("Espadón de orichalcum", URL + "icon_wp_gs_0064_t05.webp", "arma"),
    ("Anillo de zafiro", URL + "icon_acc_ring_0012.webp", "joya"),
    ("Coraza de cuero", URL + "icon_gm_lt_0003_torso.webp", "armadura"),
    ("Filete en cubos de dragón oscuro", URL + "icon_item_usable_01.webp", "comida"),
    ("Pergamino de velocidad", "", "pergamino"),
    ("Piedra de refinamiento", "", "refinamiento"),
    ("Piedra de maná de ataque", "", "piedra"),
    ("Piedra espiritual", "", "cristal"),
    ("Polvo de piedra espiritual", "", "cristal"),
    ("Od", "", "cristal"),
    ("Poción de vida superior", "", "pocion"),
    ("Esencia de Balaur", "", "esencia"),
    ("Martillo de circón (vinculado)", "", "herramienta"),
    ("Diamante pulido", "", "gema"),
    ("Mineral de orichalcum", "", "mineral"),
    ("Lingote de orichalcum", "", "mineral"),
    ("Tronco de asvata", "", "madera"),
    ("Pimienta de Altgard", "", "condimento"),
    ("Cuerno grueso de Balaur refinado", "", "escama"),
    ("Carne suave de Balaur", "", "carne"),
    ("Okra", "", "carne"),
    ("Morfa", URL + "icon_item_gather_0001.webp", "hierba"),
    ("Cosa rara", "", "otro"),
])
def test_categoria(nombre, icono, esperada):
    assert categoria({"nombre": nombre, "icono": icono}) == esperada


def test_categoria_sin_objeto_y_mapa():
    assert categoria(None) == "otro"
    assert categoria({}) == "otro"
    m = mapa_categorias({1: {"nombre": "Okra"}, "2": {"nombre": "Mineral de hierro"}})
    assert m == {"1": "carne", "2": "mineral"}
    assert set(m.values()) <= set(CATEGORIAS)


def test_categorias_tienen_icono_en_el_frontend():
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "iconos.js").read_text(encoding="utf-8")
    bloque = re.search(r"ICONOS_CATEGORIA = \{(.*?)\n\};", js, re.S).group(1)
    claves = set(re.findall(r"^\s*(\w+):", bloque, re.M))
    assert claves == set(CATEGORIAS)
