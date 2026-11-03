import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.calculo import (analizar_receta, coste_adquisicion, mejores_oportunidades,
                         probabilidades)

FIXTURE = Path(__file__).parent / "fixtures" / "catalogo_mini.json"
AHORA = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

MINERAL, FUNDENTE, LINGOTE = 610620013, 630541001, 610710001
ESPADA, ESPADA_ESPLENDIDA, HACHA = 100000001, 100000002, 100000010
OKRA, CARNE, ACEITE, OKRA_FRITA, ESTOFADO = 620100001, 620100002, 620100003, 620200001, 620200002


@pytest.fixture(scope="module")
def cat():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def receta(cat, rid):
    return next(r for r in cat["recetas"] if r["id"] == rid)


def info(precio, ofertas=None, horas=1, cantidad_total=None, num_anuncios=None):
    return {"precio_min": precio, "ofertas": ofertas or [], "fecha": AHORA - timedelta(hours=horas),
            "cantidad_total": cantidad_total, "num_anuncios": num_anuncios}


def precios_okra(venta=12500, okra_ofertas=None):
    return {OKRA: info(788, okra_ofertas), CARNE: info(700), ACEITE: info(880), OKRA_FRITA: info(venta)}


# --- User's Excel: artisan Okra frita ----------------------------------------

def test_okra_frita_reproduce_excel(cat):
    r = receta(cat, 125010001)
    a = analizar_receta(r, cat, precios_okra(), {"rebaja_listado": 0}, nivel=3, intentos=76, ahora=AHORA)
    assert a["desbloqueada"]
    assert a["coste_intento"] == pytest.approx(8864)
    assert a["p_exito"] == pytest.approx(0.90888)
    assert a["p_combo"] == pytest.approx(0.90888 * 0.30 * 0.90888)
    assert a["items_esperados"] == pytest.approx(1.13185, abs=1e-5)
    assert a["coste_por_objeto"] == pytest.approx(7831.40, abs=0.01)
    assert a["precio_equilibrio"] == pytest.approx(8899.32, abs=0.01)
    assert a["beneficio_total"] == pytest.approx(272565.70, abs=0.01)
    assert a["beneficio_intento"] * 76 == pytest.approx(272565.70, abs=0.01)
    assert {f["id"]: f["origen"] for f in a["desglose_ingredientes"]} == {
        OKRA: "mercado", CARNE: "mercado", ACEITE: "mercado"}
    # no order book or quantity: stock is unknown → no limit
    assert a["max_intentos_mercado"] is None
    # 76 attempts ≈ 86 units > 10 listings
    assert any("anuncios" in av for av in a["avisos"])


def test_combo_fallido_queda_base(cat):
    r = receta(cat, 125010001)
    p = 0.90888
    a = analizar_receta(r, cat, precios_okra(), {"combo_fallido": "queda_base"}, nivel=3, ahora=AHORA)
    esperado = p * 0.7 + 2 * p * 0.3 * p + p * 0.3 * (1 - p)
    assert a["items_esperados"] == pytest.approx(esperado)
    assert a["p_combo_fallido"] == pytest.approx(p * 0.3 * (1 - p))


def test_comisiones_y_rebaja(cat):
    r = receta(cat, 125010001)
    a = analizar_receta(r, cat, precios_okra(10000), {"rebaja_listado": 100}, nivel=3, ahora=AHORA)
    assert a["precio_venta"] == 9900
    assert a["ingreso_esperado"] == pytest.approx(a["items_esperados"] * 9900 * 0.88)


def test_producto_combo_distinto(cat):
    r = receta(cat, 115016002)  # sword: 20% combo with a 50% curve → splendent
    precios = {LINGOTE: info(300), ESPADA: info(2000), ESPADA_ESPLENDIDA: info(10000)}
    a = analizar_receta(r, cat, precios, {"rebaja_listado": 0}, nivel=5, ahora=AHORA)
    p = 0.60
    assert a["salidas_esperadas"][ESPADA] == pytest.approx(p * 0.8)
    assert a["salidas_esperadas"][ESPADA_ESPLENDIDA] == pytest.approx(p * 0.2 * 0.5)
    assert a["ingreso_esperado"] == pytest.approx((p * 0.8 * 2000 + p * 0.1 * 10000) * 0.88)


def test_curva_satura_al_ultimo_valor(cat):
    r = receta(cat, 115016002)
    assert probabilidades(r, 5, cat)["p_exito"] == pytest.approx(0.60)
    assert probabilidades(r, 8, cat)["p_exito"] == pytest.approx(0.90)
    assert probabilidades(r, 99, cat)["p_exito"] == pytest.approx(0.90)


# --- buy vs craft ------------------------------------------------------------

def test_fabricar_si_es_mas_barato(cat):
    precios = {MINERAL: info(100), LINGOTE: info(300)}
    # crafted ingot = 2 × 100 + 50 (NPC flux) = 250 < 300
    assert coste_adquisicion(LINGOTE, cat, precios, niveles={"herreria": 1}) == (250, "fabricar", 115016001)


def test_comprar_si_es_mas_barato(cat):
    precios = {MINERAL: info(100), LINGOTE: info(200)}
    assert coste_adquisicion(LINGOTE, cat, precios, niveles={"herreria": 1}) == (200, "mercado", None)


def test_sin_nivel_no_se_puede_fabricar(cat):
    precios = {MINERAL: info(100)}
    assert coste_adquisicion(LINGOTE, cat, precios, niveles={"herreria": 0}) == (None, None, None)


def test_npc_para_vinculados(cat):
    assert coste_adquisicion(FUNDENTE, cat, {}) == (50, "npc", None)


def test_cadena_mineral_lingote_espada(cat):
    precios = {MINERAL: info(100), LINGOTE: info(300), ESPADA: info(3000)}
    a = analizar_receta(receta(cat, 115016002), cat, precios, None, nivel=5,
                        niveles={"herreria": 5}, ahora=AHORA)
    fila = a["desglose_ingredientes"][0]
    assert fila["origen"] == "fabricar" and fila["receta_id"] == 115016001
    assert a["coste_intento"] == pytest.approx(3 * 250)


def test_inventario_valorado_a_cero_o_mercado(cat):
    precios = {MINERAL: info(100), LINGOTE: info(300)}
    inv = {LINGOTE: 5}
    assert coste_adquisicion(LINGOTE, cat, precios, {"valorar_inventario": "cero"},
                             inventario=inv) == (0.0, "inventario", None)
    assert coste_adquisicion(LINGOTE, cat, precios, {"valorar_inventario": "mercado"},
                             inventario=inv) == (300, "inventario", None)


def test_ciclos_no_cuelgan():
    cat = {"objetos": {"1": {"nombre": "A"}, "2": {"nombre": "B"}}, "curvas": {},
           "recetas": [
               {"id": 1, "faccion": "ambas", "profesion": "alquimia", "nivel": 1, "producto": 1,
                "cantidad": 1, "ingredientes": [[2, 1]], "curva": None, "combo_pct": 0},
               {"id": 2, "faccion": "ambas", "profesion": "alquimia", "nivel": 1, "producto": 2,
                "cantidad": 1, "ingredientes": [[1, 1]], "curva": None, "combo_pct": 0}]}
    assert coste_adquisicion(1, cat, {}) == (None, None, None)
    assert coste_adquisicion(1, cat, {2: {"precio_min": 10}}) == (10, "fabricar", 1)


# --- level lock --------------------------------------------------------------

def test_receta_bloqueada_por_nivel(cat):
    precios = {LINGOTE: info(300), HACHA: info(5000)}
    a = analizar_receta(receta(cat, 115016003), cat, precios, None, nivel=10, ahora=AHORA)
    assert not a["desbloqueada"]
    assert any("bloqueada" in av for av in a["avisos"])
    ops = mejores_oportunidades(cat, precios, None, {"herreria": 10}, "elyos", ahora=AHORA)
    assert HACHA not in [o["producto"] for o in ops]
    ops = mejores_oportunidades(cat, precios, None, {"herreria": 50}, "elyos", ahora=AHORA)
    assert HACHA in [o["producto"] for o in ops]


# --- tiered order book -------------------------------------------------------

def test_libro_de_ofertas_por_tramos(cat):
    r = receta(cat, 125010001)
    ofertas = [(788, 6), (900, 3), (2000, 100)]
    a = analizar_receta(r, cat, precios_okra(okra_ofertas=ofertas), {"rebaja_listado": 0},
                        nivel=3, intentos=3, ahora=AHORA)
    okra = a["desglose_ingredientes"][0]
    assert okra["coste_total"] == pytest.approx(6 * 788 + 3 * 900)
    assert a["coste_total"] == pytest.approx(6 * 788 + 3 * 900 + 3 * (2100 + 4400))
    # 4th attempt: 3 × 2000 + 6500 = 12500 ≥ expected income 12450.39 → not worth it
    assert a["max_intentos_mercado"] == 3


def test_max_intentos_limitado_por_stock(cat):
    r = receta(cat, 125010001)
    ofertas = [(788, 6), (900, 4)]  # 10 units → 3 attempts
    a = analizar_receta(r, cat, precios_okra(okra_ofertas=ofertas), {"rebaja_listado": 0},
                        nivel=3, ahora=AHORA)
    assert a["max_intentos_mercado"] == 3
    a = analizar_receta(r, cat, precios_okra(okra_ofertas=ofertas), {"rebaja_listado": 0},
                        nivel=3, intentos=4, ahora=AHORA)
    assert any("No hay suficientes Okra" in av for av in a["avisos"])


def test_tramos_cambian_a_fabricar_cuando_el_mercado_encarece(cat):
    precios = {MINERAL: info(100), LINGOTE: info(200, [(200, 3), (400, 10)]), ESPADA: info(3000)}
    a = analizar_receta(receta(cat, 115016002), cat, precios, None, nivel=5, intentos=2, ahora=AHORA)
    fila = a["desglose_ingredientes"][0]
    assert fila["coste_total"] == pytest.approx(3 * 200 + 3 * 250)
    assert fila["origenes"] == {"mercado": 3, "fabricar": 3}


# --- warnings ----------------------------------------------------------------

def test_avisos_precio_antiguo_sin_precio_y_saturado(cat):
    r = receta(cat, 125010001)
    precios = {OKRA: info(788, horas=30), CARNE: info(700),
               OKRA_FRITA: info(12500, num_anuncios=80)}
    a = analizar_receta(r, cat, precios, None, nivel=3, ahora=AHORA)
    assert a["coste_intento"] is None and a["beneficio_intento"] is None
    texto = " | ".join(a["avisos"])
    assert "Sin precio para Aceite" in texto
    assert "Okra antiguo (30 h)" in texto
    assert "saturado" in texto
    assert a["antiguedad_precios_horas"] == pytest.approx(30)


# --- inventory and dashboard -------------------------------------------------

def test_inventario_puedes_hacer_y_te_faltan(cat):
    r = receta(cat, 125010001)
    inv = {OKRA: 7, CARNE: 6, ACEITE: 10}
    a = analizar_receta(r, cat, precios_okra(), {"valorar_inventario": "cero"}, nivel=3,
                        inventario=inv, intentos=3, ahora=AHORA)
    assert a["intentos_con_inventario"] == 2
    assert {f["id"]: f["faltan"] for f in a["faltan"]} == {OKRA: 2, CARNE: 3, ACEITE: 5}
    assert a["coste_faltante"] == pytest.approx(2 * 788 + 3 * 700 + 5 * 880)
    assert a["coste_total"] == pytest.approx(a["coste_faltante"])  # owned items cost 0
    assert "Puedes hacer 2 intento(s)" in a["mensaje_inventario"]
    assert "te faltan" in a["mensaje_inventario"]

    a = analizar_receta(r, cat, precios_okra(), {"valorar_inventario": "mercado"}, nivel=3,
                        inventario=inv, intentos=1, ahora=AHORA)
    assert a["coste_intento"] == pytest.approx(8864)
    assert all(f["origen"] == "inventario" for f in a["desglose_ingredientes"])


def test_mejores_oportunidades_filtros_y_orden(cat):
    precios = {MINERAL: info(100), LINGOTE: info(400), ESPADA: info(3000),
               **precios_okra(), ESTOFADO: info(5000)}
    niveles = {"herreria": 5, "cocina": 3}
    ops = mejores_oportunidades(cat, precios, None, niveles, "elyos", ahora=AHORA)
    productos = [o["producto"] for o in ops]
    assert ESTOFADO not in productos            # asmodian recipe
    assert LINGOTE in productos                 # profitable intermediate (250 → 400)
    beneficios = [o["beneficio_total"] for o in ops]
    assert beneficios == sorted(beneficios, reverse=True)
    assert all(o["intentos_recomendados"] == 100 for o in ops)

    ops = mejores_oportunidades(cat, precios, None, niveles, "elyos",
                                filtros={"incluir_intermedios": False, "profesion": "herreria"})
    assert [o["producto"] for o in ops] == [ESPADA]

    ops = mejores_oportunidades(cat, precios, None, niveles, "elyos", filtros={"inversion_max": 9000})
    okra = next(o for o in ops if o["producto"] == OKRA_FRITA)
    assert okra["intentos_recomendados"] == 1 and okra["inversion"] <= 9000

    ops = mejores_oportunidades(cat, precios, None, niveles, "elyos", filtros={"margen_min": 5})
    assert ops == []


def test_mejores_oportunidades_con_inventario(cat):
    ops = mejores_oportunidades(cat, precios_okra(), None, {"cocina": 3}, "elyos",
                                inventario={OKRA: 3, CARNE: 3, ACEITE: 5},
                                filtros={"tope_intentos": 2})
    okra = next(o for o in ops if o["producto"] == OKRA_FRITA)
    assert okra["intentos_con_inventario"] == 1
    assert okra["inversion"] == pytest.approx(8864)  # only the 2nd attempt has to be bought
