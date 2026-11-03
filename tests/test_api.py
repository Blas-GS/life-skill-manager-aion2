"""API tests (app/main.py + app/servicios.py) with doubles: mini catalog, in-memory repo,
fake engine and fake target price. At the end, smoke tests with the real modules if they exist."""
from __future__ import annotations

import importlib
import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.servicios as servicios
from app.servicios import Servicios, campo

# ---------------------------------------------------------------------------
# doubles
# ---------------------------------------------------------------------------
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


class RepoMemoria:
    backend = "local"

    def __init__(self):
        self.servidores, self.perfiles, self.niv, self.inv = {}, {}, {}, {}
        self.lecturas, self.npc, self.aj, self.ops = [], {}, {}, []

    def listar_servidores(self):
        return [dict(s) for s in self.servidores.values()]

    def guardar_servidor(self, d):
        d = {**self.servidores.get(d.get("id"), {}), **d}
        d.setdefault("id", str(uuid.uuid4()))
        for k in ("region", "comision_registro", "impuesto_venta"):
            d.setdefault(k, None)
        self.servidores[d["id"]] = d
        return dict(d)

    def listar_perfiles(self):
        return [dict(p) for p in self.perfiles.values()]

    def guardar_perfil(self, d):
        d = {**self.perfiles.get(d.get("id"), {}), **d}
        self.perfiles[d["id"]] = d
        return dict(d)

    def niveles(self, pid):
        return dict(self.niv.get(pid, {}))

    def guardar_nivel(self, pid, prof, nivel):
        self.niv.setdefault(pid, {})[prof] = int(nivel)

    def inventario(self, pid):
        tot = {}
        for (p, oid, _), c in self.inv.items():
            if p == pid:
                tot[oid] = tot.get(oid, 0) + c
        return tot

    def inventario_detalle(self, pid):
        return [{"objeto_id": oid, "cantidad": c, "ubicacion": u} for (p, oid, u), c in self.inv.items() if p == pid]

    def guardar_inventario(self, pid, oid, cantidad, ubicacion="inventario"):
        if cantidad <= 0:
            self.inv.pop((pid, int(oid), ubicacion), None)
        else:
            self.inv[(pid, int(oid), ubicacion)] = int(cantidad)

    def guardar_lecturas(self, lecturas, sesion_id=None):
        ids = []
        for l in lecturas:
            l.id = l.id or str(uuid.uuid4())
            self.lecturas.append(l)
            ids.append(l.id)
        return SimpleNamespace(ids=ids, en_cola=False)

    def verificar_lecturas(self, ids):
        existentes = {l.id for l in self.lecturas}
        return all(i in existentes for i in ids)

    def ultimas_lecturas(self, sid):
        ult = {}
        for l in sorted(self.lecturas, key=lambda x: x.fecha):
            if l.servidor_id == sid:
                ult[l.objeto_id] = l
        return ult

    def historico(self, sid, oid, desde=None):
        return [l for l in sorted(self.lecturas, key=lambda x: x.fecha)
                if l.servidor_id == sid and l.objeto_id == int(oid) and (desde is None or l.fecha >= desde)]

    def subir_pendientes(self):
        return 0

    def num_pendientes(self):
        return 0

    def precios_npc(self):
        return dict(self.npc)

    def guardar_precio_npc(self, oid, precio):
        if precio is None:
            self.npc.pop(int(oid), None)
        else:
            self.npc[int(oid)] = float(precio)

    def ajustes(self):
        return {"comision_registro": 0.02, "impuesto_venta": 0.10, "rebaja_listado": 1,
                "combo_fallido": "pierde_todo", "valorar_inventario": "mercado", "tope_tmp_mb": 500, **self.aj}

    def guardar_ajustes(self, d):
        self.aj.update(d)

    def registrar_operacion(self, pid, tipo, oid, cantidad, precio, fecha=None):
        fila = {"id": str(uuid.uuid4()), "perfil_id": pid, "tipo": tipo, "objeto_id": oid,
                "cantidad": cantidad, "precio": precio, "fecha": fecha}
        self.ops.append(fila)
        return fila


class MotorFalso:
    """Simplified engine: cost = sum of ingredients at market/NPC price, sale at 88%."""

    @staticmethod
    def _precio(oid, cat, precios, npc):
        p = campo(precios.get(int(oid)), "precio_min")
        if p is None:
            p = (npc or {}).get(int(oid))
        if p is None:
            p = (cat["objetos"].get(str(oid)) or {}).get("precio_npc")
        return p

    @classmethod
    def analizar_receta(cls, receta, cat, precios, ajustes, nivel, inventario=None, intentos=1, *,
                        niveles=None, faccion=None, precios_npc=None, ahora=None):
        desglose, coste = [], 0.0
        for oid, q in receta["ingredientes"]:
            p = cls._precio(oid, cat, precios, precios_npc)
            origen = "mercado" if campo(precios.get(int(oid)), "precio_min") is not None else "npc"
            desglose.append({"id": oid, "nombre": cat["objetos"][str(oid)]["nombre"], "cantidad": q,
                             "unidades_necesarias": q * intentos, "en_inventario": 0, "faltan": q * intentos,
                             "origen": origen, "origenes": {origen: q * intentos}, "coste_unit": p,
                             "coste_total": (p or 0) * q * intentos, "receta_id": None})
            coste += (p or 0) * q
        venta = campo(precios.get(int(receta["producto"])), "precio_min")
        ingreso = (venta - 1) * 0.88 if venta else None
        beneficio = ingreso - coste if ingreso is not None else None
        return {"receta_id": receta["id"], "producto": receta["producto"],
                "nombre": cat["objetos"][str(receta["producto"])]["nombre"], "profesion": receta["profesion"],
                "nivel_receta": receta["nivel"], "nivel": nivel, "desbloqueada": nivel >= receta["nivel"],
                "intentos": intentos, "p_exito": 1.0, "p_combo": 0.0, "items_esperados": 1.0,
                "salidas_esperadas": {receta["producto"]: 1.0}, "coste_intento": coste,
                "coste_total": coste * intentos, "precio_venta": venta - 1 if venta else None,
                "ingreso_esperado": ingreso, "beneficio_intento": beneficio,
                "beneficio_total": beneficio * intentos if beneficio is not None else None,
                "margen": beneficio / coste if beneficio is not None and coste else None,
                "precio_equilibrio": coste / 0.88, "desglose_ingredientes": desglose,
                "max_intentos_mercado": 10, "avisos": [], "antiguedad_precios_horas": 1.0,
                "mensaje_inventario": None, "coste_faltante": coste * intentos}

    @classmethod
    def mejores_oportunidades(cls, cat, precios, ajustes, niveles, faccion, inventario=None, filtros=None, *,
                              precios_npc=None, ahora=None):
        filtros = filtros or {}
        res = []
        for r in cat["recetas"]:
            if r["faccion"] not in (faccion, "ambas"):
                continue
            nivel = niveles.get(r["profesion"], 1)
            if nivel < r["nivel"] or (filtros.get("profesion") and r["profesion"] != filtros["profesion"]):
                continue
            a = cls.analizar_receta(r, cat, precios, ajustes, nivel, inventario, 1, precios_npc=precios_npc)
            if a["beneficio_intento"] is None or a["beneficio_intento"] <= 0:
                continue
            if filtros.get("margen_min") is not None and a["margen"] < filtros["margen_min"]:
                continue
            a = cls.analizar_receta(r, cat, precios, ajustes, nivel, inventario, 10, precios_npc=precios_npc)
            a.update(intentos_recomendados=10, inversion=a["coste_total"], es_intermedio=False)
            res.append(a)
        return sorted(res, key=lambda a: a["beneficio_total"], reverse=True)


class PrecioObjetivoFalso:
    @staticmethod
    def precio_objetivo_venta(historico, actual=None, ajustes=None):
        p = campo(actual, "precio_min")
        if p is None:
            return {"precio_recomendado": None, "estado": "sin_datos", "aviso": "Sin datos"}
        return {"precio_recomendado": p * 1.1, "estado": "hundido", "aviso": "Precio hundido", "rango_p25": p,
                "mediana": p * 1.1, "rango_p75": p * 1.2, "dias_para_vender": 2.0, "velocidad_dia": 5.0}

    @staticmethod
    def precio_objetivo_compra(historico, actual=None, ajustes=None):
        return {"comprar_por_debajo_de": 100.0, "estado": "normal"}

    @staticmethod
    def volumen_estimado(historico):
        return 3.5


class GrabacionFalsa:
    """Stands in for app.captura.grabacion: returns prepared rows."""
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
    repo = RepoMemoria()
    serv = Servicios(catalogo=CAT_MINI, repo=repo, motor=MotorFalso, precio_objetivo=PrecioObjetivoFalso,
                     modulos_captura={"grabacion": GrabacionFalsa, "video": None, "temporales": None,
                                      "parser": None, "calibracion": None, "ocr": None},
                     ruta_sesiones=tmp_path / "sesiones.json")
    serv.segundo_plano = False
    with TestClient(main.crear_app(serv, arrancar=False)) as cliente:
        yield SimpleNamespace(c=cliente, repo=repo, serv=serv, tmp=tmp_path)


def preparar_perfil(c, faccion="elyos"):
    s = c.post("/api/servidores", json={"nombre": "Ariel", "faccion": faccion}).json()
    p = c.post("/api/perfiles", json={"nombre": "Blas", "servidor_id": s["id"]}).json()
    return s, p


def precio(c, sid, oid, p, cant=None, ofertas_texto=None):
    r = c.post("/api/mercado/manual", json={"servidor_id": sid, "objeto_id": oid, "precio_min": p,
                                            "cantidad_total": cant, "ofertas_texto": ofertas_texto})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# tests with doubles
# ---------------------------------------------------------------------------
def test_frontend_y_estado(entorno):
    r = entorno.c.get("/")
    assert r.status_code == 200 and "Mejores oportunidades ahora" in r.text
    for archivo in ("/app.js", "/estilos.css"):
        assert entorno.c.get(archivo).status_code == 200
    e = entorno.c.get("/api/estado").json()
    assert e["backend"] == "local" and e["en_cola"] == 0
    assert e["componentes"]["catalogo"]["ok"] and e["componentes"]["motor"]["ok"]
    assert not e["componentes"]["video"]["ok"]
    assert e["catalogo"]["recetas"] == 3
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


def test_mercado_manual_e_historico(entorno):
    c = entorno.c
    s, _ = preparar_perfil(c)
    r = precio(c, s["id"], 1, None, ofertas_texto="1.250 10\n1.300 25")
    assert r["lectura"]["precio_min"] == 1250 and r["lectura"]["cantidad_total"] == 35
    assert r["lectura"]["num_anuncios"] == 2 and r["lectura"]["nombre"] == "Mineral de orichalcum"
    assert c.post("/api/mercado/manual", json={"servidor_id": s["id"], "objeto_id": 1}).status_code == 400
    ult = c.get("/api/mercado/ultimas", params={"servidor_id": s["id"]}).json()
    assert ult[0]["semaforo"] == "verde" and ult[0]["fuente"] == "manual"
    d = c.get("/api/mercado/objeto/1", params={"servidor_id": s["id"]}).json()
    assert d["objeto"]["nombre"] == "Mineral de orichalcum" and len(d["historico"]) == 1
    assert d["volumen_dia"] == 3.5 and d["objetivo_venta"]["estado"] == "hundido"
    assert d["objetivo_compra"]["comprar_por_debajo_de"] == 100.0
    assert d["fabricable"] is False


def test_oportunidades_y_recetas(entorno):
    c = entorno.c
    s, p = preparar_perfil(c)
    c.put("/api/perfiles/blas/niveles", json={"herreria": 10})
    precio(c, s["id"], 1, 100)
    precio(c, s["id"], 2, 400)
    precio(c, s["id"], 3, 2000)
    r = c.get("/api/oportunidades", params={"perfil_id": "blas"}).json()
    nombres = [f["nombre"] for f in r["filas"]]
    assert nombres == ["Espada de orichalcum", "Lingote de orichalcum"]  # asmodian cooking excluded
    top = r["filas"][0]
    assert top["profesion_nombre"] == "Herrería" and top["intentos_recomendados"] == 10
    assert top["semaforo"] == "verde" and top["inversion"] == pytest.approx(12000)
    esc = top["escenario_objetivo"]
    assert esc["estado"] == "hundido" and esc["precio_objetivo"] == pytest.approx(2200)
    assert esc["beneficio_total"] > top["beneficio_total"]

    # margins: sword ≈ 46.6 %, ingot ≈ 40.4 %
    filtrado = c.get("/api/oportunidades", params={"perfil_id": "blas", "margen_min": 42}).json()
    assert [f["nombre"] for f in filtrado["filas"]] == ["Espada de orichalcum"]

    lista = c.get("/api/recetas", params={"perfil_id": "blas"}).json()
    assert lista["faccion"] == "elyos" and {f["id"] for f in lista["filas"]} == {101, 102}
    assert c.get("/api/recetas", params={"q": "okra"}).json()["total"] == 0  # default profile: elyos

    det = c.get("/api/recetas/102", params={"perfil_id": "blas", "intentos": 2}).json()
    assert det["receta"]["nombre"] == "Espada de orichalcum" and det["analisis"]["intentos"] == 2
    nodo = det["arbol"][0]
    assert nodo["nombre"] == "Lingote de orichalcum" and nodo["precio_mercado"] == 400
    assert nodo["receta_id"] == 101 and nodo["coste_fabricar"] == pytest.approx(250)
    assert nodo["mejor"] == "fabricar" and nodo["hijos"][0]["nombre"] == "Mineral de orichalcum"

    lc = c.get("/api/recetas/101/lista-compra", params={"perfil_id": "blas", "intentos": 5}).json()
    compras = {i["nombre"]: i for i in lc["comprar"]}
    assert compras["Mineral de orichalcum"]["cantidad"] == 10 and compras["Mineral de orichalcum"]["origen"] == "mercado"
    assert compras["Fundente (vinculado)"]["origen"] == "npc"
    assert "Lista de la compra" in lc["texto"] and lc["coste_total"] == pytest.approx(1250)
    assert c.get("/api/recetas/999").status_code == 404


def test_motor_ausente_degrada_con_503(entorno, monkeypatch, tmp_path):
    monkeypatch.setitem(servicios._MODULOS, "motor", "app.modulo_que_no_existe")
    serv = Servicios(catalogo=CAT_MINI, repo=RepoMemoria(), ruta_sesiones=tmp_path / "s2.json")
    with TestClient(main.crear_app(serv, arrancar=False)) as c:
        preparar_perfil(c)
        r = c.get("/api/oportunidades", params={"perfil_id": "blas"})
        assert r.status_code == 503 and "app/calculo.py" in r.json()["detail"]
        # the rest keeps working
        assert c.get("/api/recetas").status_code == 200
        assert c.get("/").status_code == 200
        det = c.get("/api/recetas/101").json()
        assert "calculo" in det["aviso"]


def test_catalogo_ausente(tmp_path, monkeypatch):
    def sin_catalogo(self):
        raise servicios.NoDisponible("catalogo")

    monkeypatch.setattr(Servicios, "cat", property(sin_catalogo))
    serv = Servicios(repo=RepoMemoria(), ruta_sesiones=tmp_path / "s.json")
    with TestClient(main.crear_app(serv, arrancar=False)) as c:
        r = c.get("/api/catalogo/buscar", params={"q": "okra"})
        assert r.status_code == 503 and "catálogo" in r.json()["detail"]
        assert c.get("/api/estado").status_code == 200
        assert c.get("/").status_code == 200


def test_ajustes_y_npc(entorno):
    c = entorno.c
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
    assert c.get("/api/catalogo/objeto/2").json()["recetas"] == [101]
    assert c.get("/api/catalogo/objeto/999").status_code == 404


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
    lect = {l.objeto_id: l for l in entorno.repo.lecturas}
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
    assert entorno.repo.lecturas[0].fuente == "grabacion"
    assert not c.get("/api/captura/estado").json()["grabando"]
    assert c.post("/api/captura/grabacion/detener").status_code == 400


def test_captura_sin_modulo_video(entorno):
    s, _ = preparar_perfil(entorno.c)
    r = entorno.c.post("/api/captura/subir", params={"nombre": "v.mp4", "servidor_id": s["id"]}, content=b"x")
    assert r.status_code == 503 and "vídeo" in r.json()["detail"]
    assert not list((entorno.tmp / "tmp").glob("*v.mp4"))


def test_operaciones(entorno):
    preparar_perfil(entorno.c)
    r = entorno.c.post("/api/operaciones", json={"perfil_id": "blas", "tipo": "venta", "objeto_id": 3,
                                                 "cantidad": 2, "precio": 1999})
    assert r.status_code == 200 and entorno.repo.ops[0]["precio"] == 1999.0
    assert entorno.c.post("/api/operaciones", json={"tipo": "regalo", "objeto_id": 3}).status_code == 400


# ---------------------------------------------------------------------------
# smoke tests with the real modules (if they already exist)
# ---------------------------------------------------------------------------
def _hay(modulo):
    try:
        importlib.import_module(modulo)
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not (_hay("app.calculo") and _hay("app.precio_objetivo")), reason="real engine not available yet")
def test_humo_motor_real(tmp_path):
    import app.calculo as calculo
    import app.precio_objetivo as po

    repo = RepoMemoria()
    serv = Servicios(catalogo=CAT_MINI, repo=repo, motor=calculo, precio_objetivo=po,
                     ruta_sesiones=tmp_path / "s.json")
    with TestClient(main.crear_app(serv, arrancar=False)) as c:
        s, _ = preparar_perfil(c)
        c.put("/api/perfiles/blas/niveles", json={"herreria": 10})
        precio(c, s["id"], 1, 100, 500)
        precio(c, s["id"], 2, 400, 200)
        precio(c, s["id"], 3, 2000, 30)
        r = c.get("/api/oportunidades", params={"perfil_id": "blas"})
        assert r.status_code == 200, r.text
        filas = r.json()["filas"]
        assert filas and all(f["beneficio_intento"] > 0 for f in filas)
        assert {f["nombre"] for f in filas} <= {"Espada de orichalcum", "Lingote de orichalcum"}
        det = c.get("/api/recetas/102", params={"perfil_id": "blas"}).json()
        assert det["analisis"]["coste_intento"] is not None and det["arbol"]
        lc = c.get("/api/recetas/102/lista-compra", params={"perfil_id": "blas", "intentos": 3})
        assert lc.status_code == 200, lc.text
        d = c.get("/api/mercado/objeto/3", params={"servidor_id": s["id"]}).json()
        assert d["objetivo_venta"]["estado"] == "sin_datos"


@pytest.mark.skipif(not _hay("app.db"), reason="app/db.py not available yet")
def test_humo_repositorio_local_real(tmp_path):
    from app.db import RepositorioLocal

    repo = RepositorioLocal(tmp_path / "aion2.db")
    serv = Servicios(catalogo=CAT_MINI, repo=repo, motor=MotorFalso, precio_objetivo=PrecioObjetivoFalso,
                     ruta_sesiones=tmp_path / "s.json")
    serv._inyectados.discard("repo")  # use the real Lectura class from app.db
    with TestClient(main.crear_app(serv, arrancar=False)) as c:
        s, p = preparar_perfil(c)
        c.put("/api/perfiles/blas/niveles", json={"herreria": 7})
        c.put("/api/perfiles/blas/inventario", json={"filas": [{"objeto_id": 1, "cantidad": 3}]})
        precio(c, s["id"], 1, 100, ofertas_texto="100 5\n110 9")
        assert c.get("/api/perfiles/blas/niveles").json()["herreria"] == 7
        ult = c.get("/api/mercado/ultimas", params={"servidor_id": s["id"]}).json()
        assert ult[0]["cantidad_total"] == 14 and ult[0]["ofertas"] == [[100.0, 5], [110.0, 9]]
        e = c.get("/api/estado").json()
        assert e["backend"] == "local"


@pytest.mark.skipif(not (_hay("app.catalogo") and servicios.RUTA_CATALOGO.exists()),
                    reason="catálogo real aún no disponible")
def test_humo_catalogo_real():
    serv = Servicios(repo=RepoMemoria())
    res = serv.cat.buscar("Mineral de orichalcum", 3)
    assert res and res[0]["nombre"]
    assert len(serv.cat.recetas) > 100
