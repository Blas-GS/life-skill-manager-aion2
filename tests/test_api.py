"""API tests (app/main.py + app/servicios.py) with a mini catalog, a local SQLite database and the
real engine. Screen capture (OCR) is replaced by a double that returns prepared rows."""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.servicios as servicios
from app.captura import temporales
from app.catalogo import Catalogo
from app.db import RepositorioLocal
from app.servicios import Servicios

CAT_MINI = {
    "fuente": "test", "version_cliente": "0.0.0", "generado": "2026-11-02T12:00:00Z",
    "profesiones": {"herreria": "Herrería", "armadura": "Armadura", "orfebreria": "Orfebrería",
                    "alquimia": "Alquimia", "cocina": "Cocina"},
    "objetos": {
        "1": {"nombre": "Mineral de orichalcum", "nombre_en": "Orichalcum Ore", "vinculado": False, "precio_npc": None},
        "2": {"nombre": "Lingote de orichalcum", "nombre_en": "Orichalcum Ingot", "vinculado": False, "precio_npc": None},
        "3": {"nombre": "Espada de orichalcum", "nombre_en": "Orichalcum Sword", "vinculado": False, "precio_npc": None},
        "4": {"nombre": "Fundente (vinculado)", "nombre_en": "Flux (Bound)", "vinculado": True, "precio_npc": 50},
        "5": {"nombre": "Okra", "nombre_en": "Ohkra", "vinculado": False, "precio_npc": None},
        "6": {"nombre": "Okra frita de artesano", "nombre_en": "Artisan's Ohkra Fried Meat", "vinculado": False, "precio_npc": None},
    },
    "curvas": {"c1": [80.0, 90.0, 100.0]},
    "recetas": [
        {"id": 101, "faccion": "ambas", "profesion": "herreria", "nivel": 1, "producto": 2, "cantidad": 1,
         "ingredientes": [[1, 2], [4, 1]], "curva": None, "combo_pct": 0, "curva_combo": None,
         "producto_combo": None, "cantidad_combo": None},
        {"id": 102, "faccion": "elyos", "profesion": "herreria", "nivel": 5, "producto": 3, "cantidad": 1,
         "ingredientes": [[2, 3]], "curva": "c1", "combo_pct": 0, "curva_combo": None,
         "producto_combo": None, "cantidad_combo": None},
        {"id": 201, "faccion": "asmodian", "profesion": "cocina", "nivel": 1, "producto": 6, "cantidad": 1,
         "ingredientes": [[5, 3]], "curva": None, "combo_pct": 0, "curva_combo": None,
         "producto_combo": None, "cantidad_combo": None},
    ],
}


class GrabacionFalsa:
    """Stands in for app.captura.grabacion (OCR of the screen): returns prepared rows."""
    FILAS = [
        {"objeto_id": 1, "nombre_leido": "Mineral de orichalcum", "precio": 100, "cantidad": 50, "confianza": 0.97, "dudosa": False},
        {"objeto_id": 1, "nombre_leido": "Mineral de orichalcum", "precio": 105, "cantidad": 20, "confianza": 0.95, "dudosa": False},
        {"objeto_id": None, "nombre_leido": "Lingote de oricha1cum", "precio": 900, "cantidad": 7, "confianza": 0.5,
         "dudosa": True, "motivos": ["Nombre no reconocido"]},
    ]

    class SesionGrabacion:
        def __init__(self, fps=3, cat=None):
            self.activa = False

        def iniciar(self):
            self.activa = True
            return self

        def detener(self):
            self.activa = False
            return [dict(f) for f in GrabacionFalsa.FILAS[:2]]

        def estado(self):
            return {"activa": self.activa, "segundos": 1, "fotogramas_procesados": 2, "filas_leidas": 2}

    @staticmethod
    def procesar_imagen(img, cat):
        return [dict(f) for f in GrabacionFalsa.FILAS]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(servicios, "DIR_TMP", tmp_path / "tmp")
    monkeypatch.setattr(main, "DIR_TMP", tmp_path / "tmp")
    monkeypatch.setattr(servicios, "grabacion", GrabacionFalsa)
    monkeypatch.setattr(temporales, "_por_defecto", temporales.Temporales(tmp_path / "tmp"))
    repo = RepositorioLocal(tmp_path / "aion2.db")
    serv = Servicios(catalogo=Catalogo(CAT_MINI), repo=repo, ruta_sesiones=tmp_path / "sesiones.json")
    serv.segundo_plano = False
    with TestClient(main.crear_app(serv, arrancar=False)) as cliente:
        yield SimpleNamespace(c=cliente, repo=repo, serv=serv, tmp=tmp_path)


def preparar_perfil(c, faccion="elyos"):
    s = c.post("/api/servidores", json={"nombre": "Ariel", "faccion": faccion}).json()
    p = c.post("/api/perfiles", json={"nombre": "Blas", "servidor_id": s["id"]}).json()
    return s, p


def precio(c, sid, oid, p, cant=None, ofertas_texto=None, dias_atras=None):
    datos = {"servidor_id": sid, "objeto_id": oid, "precio_min": p, "cantidad_total": cant,
             "ofertas_texto": ofertas_texto}
    if dias_atras is not None:
        datos["fecha"] = (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat()
    r = c.post("/api/mercado/manual", json=datos)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------
def test_frontend_y_estado(entorno):
    r = entorno.c.get("/")
    assert r.status_code == 200 and "Life Skill Manager" in r.text
    for archivo in ("/app.js", "/estilos.css", "/iconos.js", "/i18n.js"):
        assert entorno.c.get(archivo).status_code == 200
    e = entorno.c.get("/api/estado").json()
    assert e["backend"] == "local" and e["en_cola"] == 0
    assert all(v["ok"] for v in e["componentes"].values()) and len(e["componentes"]) == 10
    assert e["catalogo"]["recetas"] == 3 and e["catalogo"]["version_cliente"] == "0.0.0"
    assert entorno.c.get("/api/nada").status_code == 404


def test_panel_sin_perfil_da_aviso(entorno):
    r = entorno.c.get("/api/oportunidades").json()
    assert r["filas"] == [] and "Personaje" in r["avisos"][0]


def test_perfiles_niveles_e_inventario(entorno):
    c = entorno.c
    assert c.post("/api/servidores", json={"nombre": "X", "faccion": "pirata"}).status_code == 400
    s, p = preparar_perfil(c)
    assert s["id"] == "ariel" and p["id"] == "blas"
    perfiles = c.get("/api/perfiles").json()
    assert perfiles[0]["faccion"] == "elyos" and perfiles[0]["servidor"]["nombre"] == "Ariel"

    n = c.put("/api/perfiles/blas/niveles", json={"herreria": 12, "cocina": 3}).json()
    assert n["herreria"] == 12 and n["alquimia"] == 1
    assert c.get("/api/perfiles/blas/niveles").json()["herreria"] == 12
    assert c.put("/api/perfiles/blas/niveles", json={"herreria": 101}).status_code == 400
    assert c.put("/api/perfiles/nadie/niveles", json={"herreria": 1}).status_code == 404

    inv = c.put("/api/perfiles/blas/inventario", json={"filas": [{"objeto_id": 1, "cantidad": 40},
                                                                  {"objeto_id": 5, "cantidad": 3, "ubicacion": "almacen"}]}).json()
    assert {(f["nombre"], f["ubicacion"]) for f in inv} == {("Mineral de orichalcum", "inventario"), ("Okra", "almacen")}

    texto = "Mineral de orichalcum: 120\nOkra x 7\nCosa rarísima que no existe: 3\n"
    prev = c.post("/api/perfiles/blas/inventario/pegar", json={"texto": texto}).json()["filas"]
    assert prev[0]["objeto_id"] == 1 and prev[0]["cantidad"] == 120 and not prev[0]["dudosa"]
    assert prev[1]["objeto_id"] == 5 and prev[1]["cantidad"] == 7
    assert prev[2]["dudosa"]
    r = c.post("/api/perfiles/blas/inventario/pegar", json={"texto": texto, "aplicar": True}).json()
    assert r["guardadas"] == 2
    assert entorno.repo.inventario("blas")[1] == 120
    ctx = c.get("/api/perfiles/blas/contexto").json()
    assert ctx["faccion"] == "elyos" and ctx["inventario"]["1"] == 120


def test_mercado_manual_e_historico(entorno):
    c = entorno.c
    s, _ = preparar_perfil(c)
    r = precio(c, s["id"], 1, None, ofertas_texto="1.250 10\n1.300 25")
    assert r["lectura"]["precio_min"] == 1250 and r["lectura"]["cantidad_total"] == 35
    assert r["lectura"]["num_anuncios"] == 2 and r["lectura"]["nombre"] == "Mineral de orichalcum"
    assert c.post("/api/mercado/manual", json={"servidor_id": s["id"], "objeto_id": 1}).status_code == 400
    ult = c.get("/api/mercado/ultimas", params={"servidor_id": s["id"]}).json()
    assert ult[0]["semaforo"] == "verde" and ult[0]["fuente"] == "manual"
    assert ult[0]["ofertas"] == [[1250.0, 10], [1300.0, 25]]
    d = c.get("/api/mercado/objeto/1", params={"servidor_id": s["id"]}).json()
    assert d["objeto"]["nombre"] == "Mineral de orichalcum" and len(d["historico"]) == 1
    assert d["objetivo_venta"]["estado"] == "sin_datos" and d["objetivo_compra"]["estado"] == "sin_datos"
    assert d["fabricable"] is False
    d = c.get("/api/mercado/objeto/2", params={"servidor_id": s["id"]}).json()
    assert d["fabricable"] and d["recetas"][0]["id"] == 101


def test_oportunidades_y_recetas(entorno):
    c = entorno.c
    s, p = preparar_perfil(c)
    c.put("/api/perfiles/blas/niveles", json={"herreria": 10})
    precio(c, s["id"], 1, 100)
    precio(c, s["id"], 2, 400)
    for dias, p_ in ((3, 2500), (2, 2600), (1, 2400)):
        precio(c, s["id"], 3, p_, dias_atras=dias)
    precio(c, s["id"], 3, 2000)  # below its usual price: "sunk"
    r = c.get("/api/oportunidades", params={"perfil_id": "blas"}).json()
    nombres = [f["nombre"] for f in r["filas"]]
    assert nombres == ["Espada de orichalcum", "Lingote de orichalcum"]  # asmodian cooking excluded
    top = r["filas"][0]
    # 3 ingots crafted at 2×100 + 50 (NPC) each; unknown stock → capped at 100 attempts
    assert top["profesion_nombre"] == "Herrería" and top["intentos_recomendados"] == 100
    assert top["coste_intento"] == pytest.approx(750) and top["inversion"] == pytest.approx(75000)
    assert top["beneficio_intento"] == pytest.approx(1999 * 0.88 - 750)
    assert top["semaforo"] == "verde"
    esc = top["escenario_objetivo"]
    assert esc["estado"] == "hundido" and esc["precio_objetivo"] > 2000
    assert esc["beneficio_total"] > top["beneficio_total"]

    # margins: sword ≈ 134.5 %, ingot ≈ 40.4 %
    filtrado = c.get("/api/oportunidades", params={"perfil_id": "blas", "margen_min": 42}).json()
    assert [f["nombre"] for f in filtrado["filas"]] == ["Espada de orichalcum"]
    barato = c.get("/api/oportunidades", params={"perfil_id": "blas", "inversion_max": 1000}).json()
    assert {f["nombre"]: f["intentos_recomendados"] for f in barato["filas"]} == {
        "Espada de orichalcum": 1, "Lingote de orichalcum": 4}

    lista = c.get("/api/recetas", params={"perfil_id": "blas"}).json()
    assert lista["faccion"] == "elyos" and {f["id"] for f in lista["filas"]} == {101, 102}
    assert c.get("/api/recetas", params={"q": "okra"}).json()["total"] == 0  # default profile: elyos

    det = c.get("/api/recetas/102", params={"perfil_id": "blas", "intentos": 2}).json()
    assert det["receta"]["nombre"] == "Espada de orichalcum" and det["analisis"]["intentos"] == 2
    assert det["escenario_objetivo"]["estado"] == "hundido"
    nodo = det["arbol"][0]
    assert nodo["nombre"] == "Lingote de orichalcum" and nodo["precio_mercado"] == 400
    assert nodo["receta_id"] == 101 and nodo["coste_fabricar"] == pytest.approx(250)
    assert nodo["mejor"] == "fabricar" and nodo["hijos"][0]["nombre"] == "Mineral de orichalcum"

    lc = c.get("/api/recetas/101/lista-compra", params={"perfil_id": "blas", "intentos": 5}).json()
    compras = {i["nombre"]: i for i in lc["comprar"]}
    assert compras["Mineral de orichalcum"]["cantidad"] == 10 and compras["Mineral de orichalcum"]["origen"] == "mercado"
    assert compras["Fundente (vinculado)"]["origen"] == "npc"
    assert "Lista de la compra" in lc["texto"] and lc["coste_total"] == pytest.approx(1250)
    lc = c.get("/api/recetas/102/lista-compra", params={"perfil_id": "blas", "intentos": 3}).json()
    assert lc["fabricar"][0]["receta_id"] == 101 and lc["fabricar"][0]["intentos"] == 9
    assert c.get("/api/recetas/999").status_code == 404


def test_catalogo_ausente(tmp_path, monkeypatch):
    def sin_catalogo(ruta=None):
        raise FileNotFoundError(2, "No existe", "data/catalogo.json")

    monkeypatch.setattr(servicios, "cargar_catalogo", sin_catalogo)
    serv = Servicios(repo=RepositorioLocal(tmp_path / "aion2.db"), ruta_sesiones=tmp_path / "s.json")
    with TestClient(main.crear_app(serv, arrancar=False)) as c:
        r = c.get("/api/catalogo/buscar", params={"q": "okra"})
        assert r.status_code == 503 and "catálogo" in r.json()["detail"]
        e = c.get("/api/estado").json()
        assert not e["componentes"]["catalogo"]["ok"] and e["componentes"]["repo"]["ok"]
        assert c.get("/").status_code == 200


def test_ajustes_y_npc(entorno):
    c = entorno.c
    assert c.get("/api/ajustes").json() == servicios.AJUSTES_POR_DEFECTO
    a = c.put("/api/ajustes", json={"comision_registro": 0.03, "rebaja_listado": 5, "clave_rara": 1}).json()
    assert a["comision_registro"] == 0.03 and a["rebaja_listado"] == 5 and "clave_rara" not in a
    assert c.put("/api/ajustes", json={"combo_fallido": "magia"}).status_code == 400
    npc = c.get("/api/precios-npc").json()
    assert npc[0]["nombre"] == "Fundente (vinculado)" and npc[0]["origen"] == "catálogo"
    c.put("/api/precios-npc", json={"objeto_id": 4, "precio": 70})
    npc = c.get("/api/precios-npc").json()
    assert npc[0]["precio"] == 70 and npc[0]["origen"] == "manual"
    # a server with its own fee overrides the global one
    s = c.post("/api/servidores", json={"nombre": "Zikel", "faccion": "asmodian", "comision_registro": 0.05}).json()
    assert entorno.serv.ajustes_efectivos(s)["comision_registro"] == 0.05


def test_catalogo_buscar(entorno):
    c = entorno.c
    r = c.get("/api/catalogo/buscar", params={"q": "mineral orichalcum"}).json()
    assert r[0]["id"] == 1 and r[0]["nombre"] == "Mineral de orichalcum"
    assert c.get("/api/catalogo/buscar", params={"q": "okra"}).json()[0]["id"] == 5
    assert c.get("/api/catalogo/buscar", params={"q": "2"}).json()[0]["fabricable"] is True
    assert c.get("/api/catalogo/objeto/2").json()["recetas"] == [101]
    assert c.get("/api/catalogo/objeto/999").status_code == 404
    info = c.get("/api/catalogo").json()
    assert info["recetas"] == 3 and info["fuente"] == "test"


def test_captura_imagen_revision_y_limpieza(entorno):
    c = entorno.c
    s, _ = preparar_perfil(c)
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "black").save(buf, "PNG")
    assert c.post("/api/captura/subir", params={"nombre": "x.txt", "servidor_id": s["id"]}, content=b"hola").status_code == 400
    r = c.post("/api/captura/subir", params={"nombre": "mercado.png", "servidor_id": s["id"]}, content=buf.getvalue())
    assert r.status_code == 200, r.text
    ses = r.json()
    assert ses["estado"] == "revision" and ses["n_dudosas"] == 1 and ses["n_ok"] == 2
    archivos = list((entorno.tmp / "tmp").glob("*mercado.png"))
    assert len(archivos) == 1  # kept until saved and verified

    d = c.get(f"/api/captura/sesiones/{ses['id']}").json()
    assert d["filas"][2]["estado"] == "pendiente"
    assert c.post(f"/api/captura/sesiones/{ses['id']}/filas/2", json={"accion": "confirmar"}).status_code == 400
    d = c.post(f"/api/captura/sesiones/{ses['id']}/filas/2",
               json={"accion": "confirmar", "objeto_id": 2, "precio": 900, "cantidad": 7}).json()
    assert d["filas"][2]["estado"] == "corregida" and d["filas"][2]["nombre"] == "Lingote de orichalcum"

    g = c.post(f"/api/captura/sesiones/{ses['id']}/guardar").json()
    assert g["estado"] == "terminada" and g["n_guardadas"] == 2
    lect = entorno.repo.ultimas_lecturas(s["id"])
    assert lect[1].precio_min == 100 and lect[1].cantidad_total == 70 and lect[1].num_anuncios == 2
    assert lect[1].fuente == "captura" and lect[2].precio_min == 900
    assert not list((entorno.tmp / "tmp").glob("*mercado.png"))  # deleted after verification
    assert c.post(f"/api/captura/sesiones/{ses['id']}/guardar").status_code == 400
    # sessions are persisted on disk
    assert (entorno.tmp / "sesiones.json").exists()


def test_captura_grabacion(entorno):
    c = entorno.c
    assert c.post("/api/captura/grabacion/iniciar", json={}).status_code == 400
    s, _ = preparar_perfil(c)
    e = c.post("/api/captura/grabacion/iniciar", json={"servidor_id": s["id"]}).json()
    assert e["grabando"] and e["grabacion"]["activa"]
    assert c.post("/api/captura/grabacion/iniciar", json={"servidor_id": s["id"]}).status_code == 400
    r = c.post("/api/captura/grabacion/detener").json()
    assert r["estado"] == "terminada" and r["n_guardadas"] == 1
    assert entorno.repo.ultimas_lecturas(s["id"])[1].fuente == "grabacion"
    assert not c.get("/api/captura/estado").json()["grabando"]
    assert c.post("/api/captura/grabacion/detener").status_code == 400


def test_operaciones(entorno):
    preparar_perfil(entorno.c)
    r = entorno.c.post("/api/operaciones", json={"perfil_id": "blas", "tipo": "venta", "objeto_id": 3,
                                                 "cantidad": 2, "precio": 1999})
    assert r.status_code == 200 and r.json()["precio"] == 1999.0
    assert entorno.c.post("/api/operaciones", json={"tipo": "regalo", "objeto_id": 3}).status_code == 400


@pytest.mark.skipif(not servicios.RAIZ.joinpath("data", "catalogo.json").exists(),
                    reason="data/catalogo.json is not committed: generate it with tools/importar_metabot.py")
def test_catalogo_real(tmp_path):
    serv = Servicios(repo=RepositorioLocal(tmp_path / "aion2.db"), ruta_sesiones=tmp_path / "s.json")
    res = serv.buscar("Mineral de orichalcum", 3)
    assert res and res[0]["nombre"]
    assert len(serv.cat.recetas) > 100


CAT_COMBO = {
    **CAT_MINI,
    "objetos": {
        "1": {"nombre": "Mineral de orichalcum", "nombre_en": "Orichalcum Ore", "vinculado": False, "precio_npc": None},
        "7": {"nombre": "Espada de artesano", "nombre_en": "Artisan Sword", "vinculado": False, "precio_npc": None},
        "8": {"nombre": "Espada brillante de artesano", "nombre_en": "Splendent Artisan Sword", "vinculado": False,
              "precio_npc": None},
        "9": {"nombre": "Anillo de artesano", "nombre_en": "Artisan Ring", "vinculado": False, "precio_npc": None},
    },
    "recetas": [
        # the Splendent sword only comes out of this recipe as a combo bonus
        {"id": 301, "faccion": "ambas", "profesion": "herreria", "nivel": 1, "producto": 7, "cantidad": 1,
         "ingredientes": [[1, 2]], "curva": None, "combo_pct": 50, "curva_combo": None,
         "producto_combo": 8, "cantidad_combo": 1},
        {"id": 302, "faccion": "ambas", "profesion": "orfebreria", "nivel": 1, "producto": 9, "cantidad": 1,
         "ingredientes": [[8, 1]], "curva": None, "combo_pct": 0, "curva_combo": None,
         "producto_combo": None, "cantidad_combo": None},
    ],
}


def test_combo_no_es_ruta_de_fabricacion(tmp_path):
    """An item that a recipe only yields as a combo bonus is not "crafted": the recipe tree
    must agree with the engine (no craft cost, no sub-recipe)."""
    serv = Servicios(catalogo=Catalogo(CAT_COMBO), repo=RepositorioLocal(tmp_path / "aion2.db"),
                     ruta_sesiones=tmp_path / "sesiones.json")
    serv.segundo_plano = False
    with TestClient(main.crear_app(serv, arrancar=False)) as c:
        s, p = preparar_perfil(c)
        precio(c, s["id"], 1, 100)
        det = c.get("/api/recetas/302", params={"perfil_id": p["id"]}).json()
        nodo = det["arbol"][0]
        assert nodo["id"] == 8 and nodo["coste_fabricar"] is None and nodo["receta_id"] is None
        assert nodo["hijos"] == [] and nodo["mejor"] is None
        (ing,) = det["analisis"]["desglose_ingredientes"]
        assert ing.get("receta_id") is None  # the engine does not craft it either
        lc = c.get("/api/recetas/302/lista-compra", params={"perfil_id": p["id"], "intentos": 1}).json()
        assert lc["fabricar"] == []
