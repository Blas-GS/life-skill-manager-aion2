"""Tests for app/db.py: SQLite in a temporary folder and Supabase with a simulated PostgREST."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import httpx
import pytest

from app.db import (
    Lectura, RepositorioLocal, RepositorioSupabase, ResultadoGuardado,
    obtener_repositorio,
)

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
SRV = "srv-elyos"


def lectura(objeto_id=610620013, minutos=0, precio=100.0, ofertas=None, fuente="captura"):
    ofertas = [(precio + 5, 3), (precio, 10)] if ofertas is None else ofertas
    return Lectura(servidor_id=SRV, objeto_id=objeto_id, fecha=T0 + timedelta(minutes=minutos),
                   precio_min=precio, cantidad_total=sum(c for _, c in ofertas),
                   num_anuncios=len(ofertas), ofertas=ofertas, fuente=fuente)


# ---------------------------------------------------------------------------
# Simulated PostgREST (just enough for what app/db.py uses)
# ---------------------------------------------------------------------------

CLAVES = {
    "servidores": ("id",), "perfiles": ("id",), "niveles": ("perfil_id", "profesion"),
    "inventario": ("perfil_id", "objeto_id", "ubicacion"), "lecturas_mercado": ("id",),
    "ofertas": ("lectura_id", "posicion"), "precios_npc": ("objeto_id",),
    "operaciones": ("id",), "ajustes": ("clave",), "objetos": ("id",), "curvas": ("id",),
    "recetas": ("id",), "receta_ingredientes": ("receta_id", "posicion"),
}


class FalsoPostgrest:
    def __init__(self):
        self.tablas: dict[str, list[dict]] = {t: [] for t in CLAVES}
        self.caido = False             # simulates no network
        self.fallar_tablas: set[str] = set()   # returns 503 on these tables
        self.rechazar_tablas: set[str] = set() # returns 409 on these tables
        self.peticiones: list[httpx.Request] = []

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(lambda req: self.manejar(req))

    # --- filters -----------------------------------------------------------
    @staticmethod
    def _cumple(fila: dict, col: str, expr: str) -> bool:
        op, _, val = expr.partition(".")
        v = fila.get(col)
        if op == "is":
            return (v is None) == (val == "null")
        if op == "not":
            return not FalsoPostgrest._cumple(fila, col, val)
        if op == "in":
            return str(v) in val.strip("()").split(",")
        conv = type(v) if v is not None else str
        val = conv(val)
        return {"eq": v == val, "gte": v >= val, "lte": v <= val,
                "gt": v > val, "lt": v < val}[op]

    def _vista(self, nombre: str) -> list[dict]:
        if nombre == "ultima_lectura":
            mejor: dict = {}
            for f in self.tablas["lecturas_mercado"]:
                k = (f["servidor_id"], f["objeto_id"])
                if k not in mejor or f["fecha"] > mejor[k]["fecha"]:
                    mejor[k] = f
            return list(mejor.values())
        return self.tablas[nombre]

    def manejar(self, req: httpx.Request) -> httpx.Response:
        self.peticiones.append(req)
        if self.caido:
            raise httpx.ConnectError("sin red", request=req)
        tabla = req.url.path.removeprefix("/rest/v1/")
        if tabla in self.fallar_tablas:
            return httpx.Response(503, json={"message": "caído"})
        if tabla in self.rechazar_tablas:
            return httpx.Response(409, json={"message": "violación de clave foránea"})
        params = parse_qsl(req.url.query.decode())
        especiales = {"select", "order", "limit", "offset", "on_conflict"}
        filtros = [(k, v) for k, v in params if k not in especiales]
        p = dict(params)

        if req.method == "GET":
            filas = [f for f in self._vista(tabla) if all(self._cumple(f, k, v) for k, v in filtros)]
            for clave in reversed(p.get("order", "").split(",")):
                if clave:
                    col, _, dirc = clave.partition(".")
                    filas.sort(key=lambda f: (f.get(col) is None, f.get(col)), reverse=dirc == "desc")
            if "select" in p and p["select"] != "*":
                cols = p["select"].split(",")
                filas = [{c: f.get(c) for c in cols} for f in filas]
            ini = int(p.get("offset", 0))
            fin = ini + int(p["limit"]) if "limit" in p else None
            return httpx.Response(200, json=filas[ini:fin])

        if req.method == "POST":
            cuerpo = json.loads(req.content)
            prefer = req.headers.get("prefer", "")
            pk = tuple(p["on_conflict"].split(",")) if "on_conflict" in p else CLAVES[tabla]
            if len({tuple(sorted(f)) for f in cuerpo}) > 1:
                return httpx.Response(400, json={"message": "All object keys must match"})
            salida = []
            for nueva in cuerpo:
                actual = next((f for f in self.tablas[tabla]
                               if all(f.get(c) == nueva.get(c) for c in pk)), None)
                if actual is None:
                    self.tablas[tabla].append(dict(nueva))
                    salida.append(dict(nueva))
                elif "merge-duplicates" in prefer:
                    actual.update(nueva)
                    salida.append(dict(actual))
                elif "ignore-duplicates" not in prefer:
                    return httpx.Response(409, json={"message": "duplicado"})
            return httpx.Response(201, json=salida if "return=representation" in prefer else None)

        if req.method == "DELETE":
            self.tablas[tabla] = [f for f in self.tablas[tabla]
                                  if not all(self._cumple(f, k, v) for k, v in filtros)]
            return httpx.Response(204)
        return httpx.Response(405)


@pytest.fixture
def falso():
    return FalsoPostgrest()


@pytest.fixture
def supa(tmp_path, falso):
    repo = RepositorioSupabase("https://ejemplo.supabase.co", "sb_secret_prueba",
                               ruta_cola=tmp_path / "pendientes.jsonl",
                               transport=falso.transporte())
    repo.guardar_servidor({"id": SRV, "nombre": "Siel", "faccion": "elyos", "region": "EU"})
    yield repo
    repo.cerrar()


@pytest.fixture
def local(tmp_path):
    repo = RepositorioLocal(tmp_path / "aion2.db")
    repo.guardar_servidor({"id": SRV, "nombre": "Siel", "faccion": "elyos", "region": "EU"})
    return repo


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def test_obtener_repositorio_elige_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("SUPABASE_URL=\nSUPABASE_KEY=\n", encoding="utf-8")
    repo = obtener_repositorio(ruta_env=env, ruta_datos=tmp_path)
    assert repo.backend == "local" and (tmp_path / "aion2.db").exists()

    env.write_text("SUPABASE_URL=https://x.supabase.co/\nSUPABASE_KEY=sb_secret_abc\n",
                   encoding="utf-8")
    repo = obtener_repositorio(ruta_env=env, ruta_datos=tmp_path)
    assert repo.backend == "supabase"
    assert repo.ruta_cola == tmp_path / "pendientes.jsonl"
    assert "sb_secret_abc" not in repr(repo)
    repo.cerrar()


def test_supabase_rechaza_http_sin_cifrar():
    with pytest.raises(ValueError):
        RepositorioSupabase("http://ejemplo.supabase.co", "sb_secret_x")


def test_cabeceras_segun_tipo_de_clave(tmp_path, falso):
    for clave, con_bearer in (("sb_secret_abc", False), ("eyJhbGciOi.prueba.firma", True)):
        repo = RepositorioSupabase("https://x.supabase.co", clave, ruta_cola=tmp_path / "c.jsonl",
                                   transport=falso.transporte())
        repo.listar_servidores()
        req = falso.peticiones[-1]
        assert req.url.path == "/rest/v1/servidores"
        assert req.headers["apikey"] == clave
        assert ("authorization" in req.headers) == con_bearer
        if con_bearer:
            assert req.headers["authorization"] == f"Bearer {clave}"
        repo.cerrar()


# ---------------------------------------------------------------------------
# Common interface: tested the same way on both backends
# ---------------------------------------------------------------------------

@pytest.fixture(params=["local", "supabase"])
def repo(request):
    return request.getfixturevalue("local" if request.param == "local" else "supa")


def test_servidores_y_perfiles(repo):
    otro = repo.guardar_servidor({"nombre": "Tiamat", "faccion": "Asmodian"})
    assert otro["faccion"] == "asmodian" and otro["id"]
    assert {s["nombre"] for s in repo.listar_servidores()} == {"Siel", "Tiamat"}
    # updating a single field keeps the rest
    repo.guardar_servidor({"id": SRV, "impuesto_venta": 0.08})
    siel = next(s for s in repo.listar_servidores() if s["id"] == SRV)
    assert siel["impuesto_venta"] == 0.08 and siel["nombre"] == "Siel"
    with pytest.raises(ValueError):
        repo.guardar_servidor({"nombre": "X", "faccion": "balaur"})

    p = repo.guardar_perfil({"nombre": "Blas", "servidor_id": SRV})
    assert repo.listar_perfiles() == [{"id": p["id"], "nombre": "Blas", "servidor_id": SRV}]


def test_niveles_e_inventario(repo):
    p = repo.guardar_perfil({"nombre": "Blas", "servidor_id": SRV})
    repo.guardar_nivel(p["id"], "herreria", 12)
    repo.guardar_nivel(p["id"], "cocina", 3)
    repo.guardar_nivel(p["id"], "herreria", 13)
    assert repo.niveles(p["id"]) == {"herreria": 13, "cocina": 3}

    repo.guardar_inventario(p["id"], 610620013, 20)
    repo.guardar_inventario(p["id"], 610620013, 5, ubicacion="almacen")
    repo.guardar_inventario(p["id"], 630541001, 7)
    assert repo.inventario(p["id"]) == {610620013: 25, 630541001: 7}
    assert len(repo.inventario_detalle(p["id"])) == 3
    repo.guardar_inventario(p["id"], 630541001, 0)   # 0 = remove
    assert repo.inventario(p["id"]) == {610620013: 25}


def test_guardar_verificar_y_leer_lecturas(repo):
    a1 = lectura(minutos=0, precio=100)
    a2 = lectura(minutos=30, precio=90, ofertas=[(95, 1), (90, 4), (92, 2)])
    b = lectura(objeto_id=630541001, minutos=10, precio=7, ofertas=[])
    res = repo.guardar_lecturas([a1, a2, b], sesion_id="sesion-1")
    assert isinstance(res, ResultadoGuardado) and res.en_cola is False
    assert len(res.ids) == 3 and a1.id == res.ids[0]
    assert repo.verificar_lecturas(res.ids) is True
    assert repo.verificar_lecturas([]) is True
    assert repo.verificar_lecturas(["no-es-uuid"]) is False
    assert repo.verificar_lecturas(["00000000-0000-0000-0000-000000000000"]) is False

    ult = repo.ultimas_lecturas(SRV)
    assert set(ult) == {610620013, 630541001}
    assert ult[610620013].id == a2.id
    assert ult[610620013].ofertas == [(90.0, 4), (92.0, 2), (95.0, 1)]   # sorted by price
    assert ult[610620013].fecha == T0 + timedelta(minutes=30)
    assert ult[630541001].ofertas == []

    hist = repo.historico(SRV, 610620013, T0 - timedelta(days=1))
    assert [h.precio_min for h in hist] == [100.0, 90.0]
    assert repo.historico(SRV, 610620013, T0 + timedelta(minutes=5))[0].id == a2.id

    # saving the same thing twice doesn't duplicate it
    repo.guardar_lecturas([a1])
    assert len(repo.historico(SRV, 610620013, T0 - timedelta(days=1))) == 2


def test_lectura_invalida_no_se_guarda(repo):
    with pytest.raises(ValueError):
        repo.guardar_lecturas([lectura(fuente="telepatia")])


def test_ajustes_precios_npc_y_operaciones(repo):
    assert repo.ajustes() == {}
    repo.guardar_ajustes({"rebaja_listado": 5, "combo_fallido": "conserva"})
    assert repo.ajustes() == {"rebaja_listado": 5, "combo_fallido": "conserva"}

    repo.guardar_precio_npc(610620013, 120)
    repo.guardar_precio_npc(610620013, 150.5)
    assert repo.precios_npc() == {610620013: 150.5}

    p = repo.guardar_perfil({"nombre": "Blas", "servidor_id": SRV})
    op = repo.registrar_operacion(p["id"], "venta", 610710001, 3, 9000, T0)
    assert op["id"] and op["precio"] == 9000.0
    guardadas = (repo._filas("select tipo from operaciones where perfil_id = ?", [p["id"]]) if repo.backend == "local"
                 else repo._get("operaciones", [("select", "tipo"), ("perfil_id", f"eq.{p['id']}")]))
    assert [o["tipo"] for o in guardadas] == ["venta"]
    with pytest.raises(ValueError):
        repo.registrar_operacion(p["id"], "regalo", 1, 1, 1, T0)


def test_local_vistas_sqlite(local):
    local.guardar_lecturas([lectura(minutos=0, precio=100), lectura(minutos=60, precio=80)])
    filas = local._filas("select * from precio_diario")
    assert filas[0]["precio_min"] == 80 and filas[0]["num_lecturas"] == 2
    assert filas[0]["dia"] == "2026-11-01"


# ---------------------------------------------------------------------------
# Supabase: offline queue
# ---------------------------------------------------------------------------

def test_sin_red_va_a_la_cola_y_se_sube_despues(supa, falso):
    falso.caido = True
    lecs = [lectura(minutos=0), lectura(objeto_id=630541001, minutos=1)]
    res = supa.guardar_lecturas(lecs, sesion_id="s1")
    assert res.en_cola is True and len(res.ids) == 2 and res.error
    assert supa.num_pendientes() == 2
    assert supa.ruta_cola.exists()
    assert falso.tablas["lecturas_mercado"] == []

    # queued → not verified, with or without network
    assert supa.verificar_lecturas(res.ids) is False
    falso.caido = False
    assert supa.verificar_lecturas(res.ids) is False

    assert supa.subir_pendientes() == 2
    assert supa.num_pendientes() == 0 and not supa.ruta_cola.exists()
    assert supa.verificar_lecturas(res.ids) is True
    assert len(falso.tablas["ofertas"]) == 4
    assert {f["sesion_id"] for f in falso.tablas["lecturas_mercado"]} == {"s1"}
    assert supa.subir_pendientes() == 0


def test_subida_a_medias_se_reintenta_sin_duplicar(supa, falso):
    falso.fallar_tablas = {"ofertas"}       # the reading goes in, the offers don't
    res = supa.guardar_lecturas([lectura()])
    assert res.en_cola is True
    assert len(falso.tablas["lecturas_mercado"]) == 1 and falso.tablas["ofertas"] == []
    assert supa.verificar_lecturas(res.ids) is False

    falso.fallar_tablas = set()
    assert supa.subir_pendientes() == 1
    assert len(falso.tablas["lecturas_mercado"]) == 1 and len(falso.tablas["ofertas"]) == 2
    assert supa.verificar_lecturas(res.ids) is True


def test_verificar_falla_si_faltan_ofertas(supa, falso):
    res = supa.guardar_lecturas([lectura()])
    falso.tablas["ofertas"].pop()
    assert supa.verificar_lecturas(res.ids) is False


def test_verificar_sin_red_devuelve_false(supa, falso):
    res = supa.guardar_lecturas([lectura()])
    falso.caido = True
    assert supa.verificar_lecturas(res.ids) is False


def test_corte_a_mitad_de_la_cola_conserva_el_resto(supa, falso):
    falso.caido = True
    r1 = supa.guardar_lecturas([lectura(minutos=0)])
    r2 = supa.guardar_lecturas([lectura(minutos=1)])
    assert supa.num_pendientes() == 2
    falso.caido = False

    llamadas = {"n": 0}
    original = falso.manejar

    def cae_tras_la_primera_entrada(req):
        if req.method == "POST" and req.url.path.endswith("lecturas_mercado"):
            llamadas["n"] += 1
            if llamadas["n"] > 1:
                raise httpx.ConnectError("sin red", request=req)
        return original(req)

    falso.manejar = cae_tras_la_primera_entrada
    assert supa.subir_pendientes() == 1
    assert supa.num_pendientes() == 1
    assert supa.verificar_lecturas(r1.ids) is True
    assert supa.verificar_lecturas(r2.ids) is False
    falso.manejar = original
    assert supa.subir_pendientes() == 1
    assert supa.verificar_lecturas(r2.ids) is True


def test_rechazo_de_supabase_se_conserva_con_el_error(supa, falso):
    falso.rechazar_tablas = {"lecturas_mercado"}
    malo = supa.guardar_lecturas([lectura()])
    assert malo.en_cola is True and "409" in malo.error
    falso.rechazar_tablas = set()
    falso.caido = True
    bueno = supa.guardar_lecturas([lectura(minutos=5)])
    falso.caido = False
    falso.rechazar_tablas = {"lecturas_mercado"}

    # the rejected entry doesn't block the others... unless it is rejected too
    assert supa.subir_pendientes() == 0
    pend = supa._leer_cola()
    assert len(pend) == 2 and all(p["intentos"] == 1 and "409" in p["error"] for p in pend)

    falso.rechazar_tablas = set()
    assert supa.subir_pendientes() == 2
    assert supa.verificar_lecturas(malo.ids + bueno.ids) is True


def test_guardar_con_red_vacia_la_cola(supa, falso):
    falso.caido = True
    viejo = supa.guardar_lecturas([lectura(minutos=0)])
    falso.caido = False
    nuevo = supa.guardar_lecturas([lectura(minutos=1)])
    assert nuevo.en_cola is False
    assert supa.num_pendientes() == 0
    assert supa.verificar_lecturas(viejo.ids + nuevo.ids) is True


def test_operacion_sin_red_va_a_la_cola(supa, falso):
    falso.caido = True
    op = supa.registrar_operacion(None, "compra", 610620013, 10, 95, T0)
    assert op["en_cola"] is True
    falso.caido = False
    assert supa.subir_pendientes() == 1
    assert [o["id"] for o in falso.tablas["operaciones"]] == [op["id"]]


def test_linea_corrupta_se_conserva(supa, falso):
    falso.caido = True
    res = supa.guardar_lecturas([lectura()])
    with supa.ruta_cola.open("a", encoding="utf-8") as f:
        f.write('{"tipo": "lecturas", "fil\n')
    falso.caido = False
    assert supa.subir_pendientes() == 1
    assert supa.verificar_lecturas(res.ids) is True
    assert '"fil' in supa.ruta_cola.read_text(encoding="utf-8")


def test_paginacion(supa, falso, monkeypatch):
    monkeypatch.setattr(RepositorioSupabase, "TAM_PAGINA", 2)
    monkeypatch.setattr(RepositorioSupabase, "TAM_IN", 2)
    lecs = [lectura(minutos=i, precio=100 - i) for i in range(5)]
    res = supa.guardar_lecturas(lecs)
    assert len(supa.historico(SRV, 610620013, T0)) == 5
    assert supa.verificar_lecturas(res.ids) is True
