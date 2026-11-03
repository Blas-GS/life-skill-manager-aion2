"""Parser tests (without OCR): numbers, fuzzy names, rows, order book and consolidation."""
import pytest

from app.captura import parser
from app.captura.parser import (
    IndiceNombres,
    agrupar_libro,
    a_lecturas,
    consolidar,
    es_numerico,
    interpretar_pantalla,
    normalizar,
    parsear_numero,
)

CAT = {
    610620013: "Mineral de orichalcum",
    610620014: "Lingote de orichalcum",
    630541001: "Okra",
    630541002: "Okra frita",
    620110001: "Esencia de Balaur",
    620110002: "Od",
    640010001: "Solomillo wellington de dragón oscuro",
}


def linea(*celdas, y=100, h=18):
    """Builds a LineaOCR from cells (texto, x). Each word of a cell is placed
    right after the previous one, with ~9 px per character."""
    palabras = []
    for texto, x in celdas:
        for trozo in texto.split():
            w = 9 * len(trozo)
            palabras.append({"texto": trozo, "x": x, "y": y, "w": w, "h": h})
            x += w + 6
    return {"texto": " ".join(c[0] for c in celdas), "palabras": palabras,
            "x": palabras[0]["x"], "y": y, "w": 1, "h": h}


def pantalla(filas, y0=100, paso=40):
    """filas: [(nombre, cantidad_txt, precio_txt)] → layout name | quantity | price."""
    lineas = []
    for i, (nombre, cant, precio) in enumerate(filas):
        celdas = []
        if nombre:
            celdas.append((nombre, 80))
        if cant is not None:
            celdas.append((cant, 620))
        if precio is not None:
            celdas.append((precio, 900))
        lineas.append(linea(*celdas, y=y0 + i * paso))
    return lineas


# ---------------------------------------------------------------- numbers
@pytest.mark.parametrize(
    "texto, valor, coherente, corregido",
    [
        ("12.500", 12500, True, False),
        ("1.234.567", 1234567, True, False),
        ("12,500", 12500, True, False),
        ("850", 850, True, False),
        ("1O.5OO", 10500, True, True),
        ("l2.5S0", 12550, True, True),
        ("B5", 85, True, True),
        ("S00", 500, True, True),
        ("x35", 35, True, False),
        ("35x", 35, True, False),
        ("12.50", 1250, False, False),
        ("1.2345", 12345, False, False),
        ("125000", 125000, False, False),
        ("12 500", 12500, True, False),
    ],
)
def test_parsear_numero(texto, valor, coherente, corregido):
    assert parsear_numero(texto) == (valor, coherente, corregido)


@pytest.mark.parametrize(
    "texto, esperado",
    [("Okra", False), ("Od", False), ("SOS", False), ("0", False), ("de", False),
     ("1O", True), ("12.500", True), ("x3", True), ("Mineral", False)],
)
def test_es_numerico(texto, esperado):
    assert es_numerico(texto) is esperado


def test_normalizar_ignora_tildes_y_mayusculas():
    assert normalizar("Solomillo Wellington de DRAGÓN oscuro") == "solomillo wellington de dragon oscuro"
    assert normalizar("  Poción,  de   vida ") == "pocion de vida"


# ---------------------------------------------------------------- names
@pytest.mark.parametrize(
    "leido, esperado",
    [
        ("Mineral de orichalcum", 610620013),
        ("mineral de oricha1cum", 610620013),
        ("ESENCIA DE BALAUR", 620110001),
        ("Esencia de Ba1aur", 620110001),
        ("0kra", 630541001),
        ("Okra", 630541001),
        ("Okra frit", 630541002),
        ("Solomillo wellington de dragon oscuro", 640010001),
        ("Solomillo wellington de dra...", 640010001),
        ("Od", 620110002),
    ],
)
def test_buscar_nombre_difuso(leido, esperado):
    res = IndiceNombres(CAT).buscar(leido)
    assert res[0][0] == esperado
    assert res[0][2] >= parser.UMBRAL_NOMBRE


def test_indice_acepta_formato_catalogo_json():
    cat = {"objetos": {"610620013": {"nombre": "Mineral de orichalcum"}, "630541001": {"nombre": "Okra"}}}
    assert IndiceNombres(cat).buscar("Mineral de orichalcum")[0][0] == 610620013


def test_indice_usa_cat_buscar_si_existe():
    class CatFalso:
        def __init__(self):
            self.llamadas = []

        def buscar(self, texto, limite=10):
            self.llamadas.append(texto)
            return [(630541002, "Okra frita", 90.0), (630541001, "Okra", 95.0)]

    cat = CatFalso()
    res = IndiceNombres(cat).buscar("Okra")
    assert cat.llamadas
    # Rescored with our own criterion: exact "Okra" wins.
    assert res[0][0] == 630541001 and res[0][2] == 100


CAT_FACCIONES = {"objetos": {
    "1001": {"nombre": "Espada de Balaur", "faccion": "elyos"},
    "2001": {"nombre": "Espada de Balaur", "faccion": "asmodian"},
    "3001": {"nombre": "Okra", "faccion": "ambas"},
}}


def test_nombre_repetido_por_faccion_sin_faccion_es_dudosa():
    f = interpretar_pantalla(pantalla([("Espada de Balaur", "1", "250.000")]), CAT_FACCIONES)[0]
    assert f["dudosa"] and any("facción" in m for m in f["motivos"])


@pytest.mark.parametrize("faccion, esperado", [("elyos", 1001), ("asmodian", 2001)])
def test_faccion_elige_el_id_correcto(faccion, esperado):
    filas = interpretar_pantalla(
        pantalla([("Espada de Balaur", "1", "250.000"), ("Okra", "20", "850")]), CAT_FACCIONES, faccion=faccion
    )
    assert [f["objeto_id"] for f in filas] == [esperado, 3001]
    assert not any(f["dudosa"] for f in filas)


def test_faccion_se_pasa_a_cat_buscar():
    class CatFalso:
        def __init__(self):
            self.facciones = []

        def buscar(self, texto, limite=10, faccion=None):
            self.facciones.append(faccion)
            todos = [(1001, "Espada de Balaur", 100.0, "elyos"), (2001, "Espada de Balaur", 100.0, "asmodian")]
            return [t[:3] for t in todos if faccion in (None, t[3])]

    cat = CatFalso()
    f = interpretar_pantalla(pantalla([("Espada de Balaur", "1", "250.000")]), cat, faccion="asmodian")[0]
    assert set(cat.facciones) == {"asmodian"}
    assert f["objeto_id"] == 2001 and not f["dudosa"]


def test_con_catalogo_real_si_existe():
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "data" / "catalogo.json"
    if not ruta.exists():
        pytest.skip("data/catalogo.json does not exist yet")
    from app.catalogo import cargar_catalogo

    cat = cargar_catalogo(ruta)
    filas = interpretar_pantalla(pantalla([("Mineral de orichalcum", "35", "12.500")]), cat, faccion="elyos")
    assert filas[0]["objeto_id"] is not None
    assert cat.nombre(filas[0]["objeto_id"]).lower() == "mineral de orichalcum"


# ---------------------------------------------------------------- rows
def test_pantalla_basica_con_separadores():
    lineas = [linea(("Nombre del objeto", 80), ("Cantidad", 620), ("Precio unitario", 900), y=60)]
    lineas += pantalla([
        ("Mineral de orichalcum", "35", "12.500"),
        ("Okra", "120", "850"),
        ("Esencia de Balaur", "2", "1.234.567"),
    ])
    filas = interpretar_pantalla(lineas, CAT)
    assert [(f["objeto_id"], f["precio"], f["cantidad"]) for f in filas] == [
        (610620013, 12500, 35),
        (630541001, 850, 120),
        (620110001, 1234567, 2),
    ]
    assert not any(f["dudosa"] for f in filas)


def test_disposicion_aprendida_resuelve_filas_ambiguas():
    # "Od 999 | 45": no separator and no clear ratio; the Mineral row shows
    # that the price is on the right (x=900) and the quantity on the left.
    filas = interpretar_pantalla(pantalla([
        ("Mineral de orichalcum", "35", "12.500"),
        ("Od", "999", "450"),
        ("Okra", "300", "120"),
    ]), CAT)
    od = [f for f in filas if f["objeto_id"] == 620110002][0]
    okra = [f for f in filas if f["objeto_id"] == 630541001][0]
    assert (od["precio"], od["cantidad"]) == (450, 999)
    assert (okra["precio"], okra["cantidad"]) == (120, 300)
    assert not od["dudosa"] and not okra["dudosa"]


def test_sin_pistas_la_fila_ambigua_es_dudosa():
    filas = interpretar_pantalla(pantalla([("Od", "999", "450")]), CAT)
    assert filas[0]["dudosa"]
    assert any("precio" in m.lower() for m in filas[0]["motivos"])


def test_confusiones_en_numeros_se_corrigen():
    filas = interpretar_pantalla(pantalla([("Mineral de orichalcum", "3S", "l2.5OO")]), CAT)
    f = filas[0]
    assert (f["precio"], f["cantidad"]) == (12500, 35)
    assert f["confianza"] < 1.0


def test_confusiones_no_afectan_a_nombres():
    # "Od" and "SOS" must not be turned into numbers.
    filas = interpretar_pantalla(pantalla([("Od", "12", "1.500")]), CAT)
    assert filas[0]["objeto_id"] == 620110002 and filas[0]["nombre_leido"] == "Od"


def test_nombre_desconocido_es_dudosa():
    filas = interpretar_pantalla(pantalla([("Espada legendaria del vacío", "1", "250.000")]), CAT)
    assert filas[0]["objeto_id"] is None and filas[0]["dudosa"]


def test_separadores_incoherentes_marcan_dudosa():
    filas = interpretar_pantalla(pantalla([("Okra", "10", "12.50")]), CAT)
    assert filas[0]["dudosa"]
    assert any("Separadores" in m for m in filas[0]["motivos"])


def test_falta_un_numero_es_dudosa():
    filas = interpretar_pantalla(pantalla([("Okra", None, "1.500")]), CAT)
    assert filas[0]["dudosa"] and filas[0]["cantidad"] is None and filas[0]["precio"] == 1500


def test_tres_numeros_con_total_coherente():
    lineas = [linea(("Okra", 80), ("20", 500), ("850", 700), ("17.000", 900), y=100)]
    f = interpretar_pantalla(lineas, CAT)[0]
    assert (f["precio"], f["cantidad"], f["total"]) == (850, 20, 17000)
    assert not f["dudosa"]


def test_tres_numeros_incoherentes_son_dudosa():
    lineas = [linea(("Okra", 80), ("20", 500), ("850", 700), ("99.999", 900), y=100)]
    f = interpretar_pantalla(lineas, CAT)[0]
    assert f["dudosa"]


def test_cabecera_de_libro_asigna_objeto_a_filas_sin_nombre():
    lineas = [linea(("Esencia de Balaur", 80), y=40)]
    lineas += pantalla([(None, "5", "1.200.000"), (None, "1", "1.250.000"), (None, "12", "1.300.000")])
    filas = interpretar_pantalla(lineas, CAT)
    assert [f["objeto_id"] for f in filas] == [620110001] * 3
    assert [f["precio"] for f in filas] == [1200000, 1250000, 1300000]
    assert not any(f["dudosa"] for f in filas)


def test_fila_partida_en_varias_lineas_ocr():
    # The OCR returned name and numbers as separate lines at the same height.
    lineas = [linea(("Mineral de orichalcum", 80), y=100), linea(("35", 620), y=101),
              linea(("12.500", 900), y=99)]
    f = interpretar_pantalla(lineas, CAT)[0]
    assert (f["objeto_id"], f["precio"], f["cantidad"]) == (610620013, 12500, 35)


def test_numero_partido_por_el_ocr_se_une():
    palabras = [
        {"texto": "Okra", "x": 80, "y": 100, "w": 40, "h": 18},
        {"texto": "20", "x": 620, "y": 100, "w": 18, "h": 18},
        {"texto": "12.", "x": 900, "y": 100, "w": 24, "h": 18},
        {"texto": "500", "x": 927, "y": 100, "w": 27, "h": 18},
    ]
    f = interpretar_pantalla([{"texto": "", "palabras": palabras}], CAT)[0]
    assert (f["precio"], f["cantidad"]) == (12500, 20)


def test_columnas_calibradas():
    columnas = {"nombre": [60, 500], "cantidad": [560, 720], "precio": [820, 1050]}
    # No separators and similar values: only the columns decide.
    lineas = pantalla([("Od", "999", "450"), ("Okra", "300", "120")])
    filas = interpretar_pantalla(lineas, CAT, columnas=columnas)
    assert [(f["precio"], f["cantidad"]) for f in filas] == [(450, 999), (120, 300)]
    assert not any(f["dudosa"] for f in filas)


def test_caja_de_la_fila():
    f = interpretar_pantalla(pantalla([("Okra", "20", "850")]), CAT)[0]
    x, y, w, h = f["caja"]
    assert x == 80 and y == 100 and w > 800 and h == 18


# ---------------------------------------------------------------- order book / consolidation
def _fila(oid, precio, cantidad, dudosa=False, confianza=1.0, nombre_leido="x"):
    return {"objeto_id": oid, "nombre_leido": nombre_leido, "precio": precio, "cantidad": cantidad,
            "confianza": confianza, "dudosa": dudosa}


def test_agrupar_libro():
    filas = [_fila(1, 900, 5), _fila(1, 850, 10), _fila(2, 40, 100), _fila(1, 800, 3, dudosa=True)]
    libro = agrupar_libro(filas)
    assert libro[1]["ofertas"] == [(850.0, 10), (900.0, 5)]
    assert libro[1]["precio_min"] == 850 and libro[1]["cantidad_total"] == 15 and libro[1]["num_anuncios"] == 2
    assert libro[2]["num_anuncios"] == 1
    assert agrupar_libro(filas, incluir_dudosas=True)[1]["precio_min"] == 800


def test_consolidar_solapamiento_y_duplicados():
    f1 = [_fila(1, 800, 5), _fila(1, 850, 2), _fila(1, 850, 2)]          # two identical listings
    f2 = [_fila(1, 850, 2), _fila(1, 850, 2), _fila(1, 900, 7)]          # scroll: they overlap
    f3 = [_fila(2, 40, 100), _fila(1, 950, 1, dudosa=True, confianza=0.5)]
    filas = consolidar([f1, f2, f3])
    libro = agrupar_libro(filas)
    assert libro[1]["ofertas"] == [(800.0, 5), (850.0, 2), (850.0, 2), (900.0, 7)]
    assert libro[2]["ofertas"] == [(40.0, 100)]
    assert [f for f in filas if f["dudosa"]] == [f3[1]]


def test_consolidar_descarta_dudosa_leida_bien_en_otro_fotograma():
    filas = consolidar([[_fila(1, 850, 2, dudosa=True, confianza=0.6)], [_fila(1, 850, 2)]])
    assert len(filas) == 1 and not filas[0]["dudosa"]


def test_a_lecturas_con_clase_propia():
    class Lectura:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    lecturas = a_lecturas([_fila(1, 900, 5), _fila(1, 850, 10)], "srv1", "captura", clase_lectura=Lectura)
    assert len(lecturas) == 1
    l = lecturas[0]
    assert (l.servidor_id, l.objeto_id, l.precio_min, l.cantidad_total, l.num_anuncios, l.fuente) == (
        "srv1", 1, 850.0, 15, 2, "captura")
    assert l.ofertas == [(850.0, 10), (900.0, 5)]
