"""Optional official icons (app/iconos.py) and their API routes, offline: mocked transport."""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

import app.main as main
from app.iconos import DescargaIconos, nombre_archivo, ruta_icono
from app.servicios import Servicios

URL = "https://metabot.gg/web/aion2/items/"
OBJETOS = {
    "1": {"nombre": "Mineral de orichalcum", "icono": URL + "icon_item_ore_01.webp"},
    "2": {"nombre": "Lingote de orichalcum", "nombre_en": "Orichalcum Ingot", "icono": URL + "icon_item_ore_01.webp"},  # same icon
    "3": {"nombre": "Espada", "icono": URL + "icon_wp_sw_02.webp"},
    "4": {"nombre": "Sin icono", "icono": None},
    "5": {"nombre": "Otro origen", "icono": "https://ejemplo.com/x.webp"},
}


def _transporte(peticiones):
    def manejar(req: httpx.Request):
        peticiones.append(str(req.url))
        if req.url.path.endswith("icon_wp_sw_02.webp"):
            return httpx.Response(404)
        return httpx.Response(200, content=b"RIFF....WEBP")
    return httpx.MockTransport(manejar)


def test_nombre_archivo_y_ruta(tmp_path):
    assert nombre_archivo(URL + "icon_item_ore_01.webp") == "icon_item_ore_01.webp"
    assert nombre_archivo("https://ejemplo.com/a.webp") is None
    assert nombre_archivo(URL + "..%2F..%2Fsecreto.webp") is None
    assert nombre_archivo(None) is None
    (tmp_path / "a.webp").write_bytes(b"x")
    assert ruta_icono("a.webp", tmp_path) == tmp_path / "a.webp"
    assert ruta_icono("../a.webp", tmp_path) is None
    assert ruta_icono("b.webp", tmp_path) is None


def test_descarga_solo_lo_que_falta(tmp_path):
    peticiones = []
    d = DescargaIconos(carpeta=tmp_path / "iconos", pausa=0, transport=_transporte(peticiones))
    est = d.iniciar(OBJETOS)
    assert est["total"] == 2
    d.esperar()
    assert d.estado["activa"] is False and d.estado["hechos"] == 2 and d.estado["errores"] == 1
    assert len(peticiones) == 2 and all(p.startswith(URL) for p in peticiones)
    assert d.mapa(OBJETOS) == {"1": "icon_item_ore_01.webp", "2": "icon_item_ore_01.webp"}
    # second run: only retries the one that failed
    peticiones.clear()
    assert d.iniciar(OBJETOS)["total"] == 1
    d.esperar()
    assert len(peticiones) == 1


def test_api_iconos(tmp_path):
    cat = {"profesiones": {}, "objetos": OBJETOS, "curvas": {}, "recetas": []}
    d = DescargaIconos(carpeta=tmp_path / "iconos", pausa=0, transport=_transporte([]))
    serv = Servicios(catalogo=cat, repo=None, motor=None, precio_objetivo=None, modulos_captura={},
                     ruta_sesiones=tmp_path / "s.json")
    with TestClient(main.crear_app(serv, arrancar=False, iconos=d)) as c:
        r = c.get("/api/catalogo/iconos").json()
        assert r["categorias"]["1"] == "mineral" and r["categorias"]["3"] == "arma"
        assert r["nombres"]["2"] == ["Lingote de orichalcum", "Orichalcum Ingot"]
        assert r["nombres"]["1"] == ["Mineral de orichalcum", None]
        assert r["oficiales"] == {} and r["descarga"]["activa"] is False
        assert c.get("/api/iconos/icon_item_ore_01.webp").status_code == 404
        assert c.post("/api/catalogo/iconos/descargar").json()["total"] == 2
        d.esperar()
        r = c.get("/api/catalogo/iconos").json()
        assert r["oficiales"]["1"] == "icon_item_ore_01.webp"
        img = c.get("/api/iconos/icon_item_ore_01.webp")
        assert img.status_code == 200 and img.content == b"RIFF....WEBP"
        assert c.get("/api/iconos/..%2Fcatalogo.json").status_code == 404
