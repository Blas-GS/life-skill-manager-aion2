"""Capa de datos: Supabase (PostgREST vía httpx) o SQLite local.

Uso:
    repo = obtener_repositorio()   # Supabase si .env tiene SUPABASE_URL y SUPABASE_KEY; si no, SQLite
    repo.backend                   # "supabase" | "local"

Contrato completo en docs/contratos.md (sección 2).

Cola offline (solo Supabase): si guardar_lecturas no puede escribir en Supabase,
las lecturas se guardan en data/pendientes.jsonl (una línea por lote) y
subir_pendientes() las reintenta. Los ids (uuid) se generan aquí, antes de
subir, así que las subidas repetidas son idempotentes y verificar_lecturas()
puede preguntar por ellos aunque sigan en la cola (devuelve False hasta que
estén en la base de datos con todas sus ofertas).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import httpx
from dotenv import dotenv_values

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DATOS = RAIZ / "data"
RUTA_ENV = RAIZ / ".env"

AJUSTES_POR_DEFECTO: dict[str, Any] = {
    "comision_registro": 0.02,
    "impuesto_venta": 0.10,
    "rebaja_listado": 1,
    "combo_fallido": "pierde_todo",
    "valorar_inventario": "mercado",
    "tope_tmp_mb": 500,
}

FUENTES = {"grabacion", "video", "captura", "manual", "excel"}
FACCIONES = {"elyos", "asmodian"}
TIPOS_OPERACION = {"venta", "compra"}

_COLS_SERVIDOR = ("id", "nombre", "faccion", "region", "comision_registro", "impuesto_venta")
_COLS_PERFIL = ("id", "nombre", "servidor_id")
_COLS_LECTURA = (
    "id", "servidor_id", "objeto_id", "fecha", "precio_min", "cantidad_total",
    "num_anuncios", "n_ofertas", "fuente", "sesion_id",
)
_COLS_OPERACION = ("id", "perfil_id", "tipo", "objeto_id", "cantidad", "precio", "fecha")


# ---------------------------------------------------------------------------
# Tipos públicos
# ---------------------------------------------------------------------------

@dataclass
class Lectura:
    servidor_id: str
    objeto_id: int
    fecha: datetime                   # UTC
    precio_min: float | None
    cantidad_total: int | None        # unidades en oferta
    num_anuncios: int | None
    ofertas: list[tuple[float, int]]  # [(precio, cantidad)] ordenado por precio
    fuente: str                       # "grabacion" | "video" | "captura" | "manual" | "excel"
    id: str | None = None             # uuid asignado al guardar


@dataclass
class ResultadoGuardado:
    ids: list[str]
    en_cola: bool                     # True si quedó en la cola offline
    error: str | None = None          # motivo, si quedó en cola


class ErrorBaseDatos(RuntimeError):
    """La base de datos rechazó la operación."""


class ErrorRed(ErrorBaseDatos):
    """No se pudo contactar con Supabase (sin red, caído, pausado o saturado)."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _utc(fecha: datetime | str) -> datetime:
    if isinstance(fecha, str):
        fecha = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def _iso(fecha: datetime | str) -> str:
    # Formato fijo: en SQLite el orden de texto coincide con el cronológico.
    return _utc(fecha).isoformat(timespec="microseconds")


def _ahora() -> str:
    return _iso(datetime.now(timezone.utc))


def _uuid(valor: str | None) -> str:
    return str(uuid.uuid4()) if valor is None else str(uuid.UUID(str(valor)))


def _es_uuid(valor: Any) -> bool:
    try:
        uuid.UUID(str(valor))
        return True
    except ValueError:
        return False


def _trozos(lista: list, n: int) -> Iterator[list]:
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


def _num(v: Any, tipo: type) -> Any:
    return None if v is None else tipo(v)


def _lectura_de_fila(fila: dict, ofertas: list[tuple[float, int]]) -> Lectura:
    return Lectura(
        servidor_id=fila["servidor_id"],
        objeto_id=int(fila["objeto_id"]),
        fecha=_utc(fila["fecha"]),
        precio_min=_num(fila["precio_min"], float),
        cantidad_total=_num(fila["cantidad_total"], int),
        num_anuncios=_num(fila["num_anuncios"], int),
        ofertas=ofertas,
        fuente=fila["fuente"],
        id=str(fila["id"]),
    )


def _agrupar_ofertas(filas: Iterable[dict]) -> dict[str, list[tuple[float, int]]]:
    por_lectura: dict[str, list[tuple[int, float, int]]] = {}
    for f in filas:
        por_lectura.setdefault(str(f["lectura_id"]), []).append(
            (int(f["posicion"]), float(f["precio"]), int(f["cantidad"])))
    return {k: [(p, c) for _, p, c in sorted(v)] for k, v in por_lectura.items()}


_CANDADOS: dict[str, threading.Lock] = {}
_CANDADO_GLOBAL = threading.Lock()


def _candado(ruta: Path) -> threading.Lock:
    clave = str(ruta.resolve())
    with _CANDADO_GLOBAL:
        return _CANDADOS.setdefault(clave, threading.Lock())


# ---------------------------------------------------------------------------
# Lógica común a los dos backends
# ---------------------------------------------------------------------------

class _RepositorioBase:
    backend = ""

    # --- validación / normalización -------------------------------------
    @staticmethod
    def _normalizar_servidor(datos: dict) -> dict:
        fila = {k: datos[k] for k in _COLS_SERVIDOR if k in datos}
        fila["id"] = str(fila.get("id") or uuid.uuid4())
        if "faccion" in fila:
            fila["faccion"] = str(fila["faccion"]).strip().lower()
            if fila["faccion"] not in FACCIONES:
                raise ValueError(f"Facción no válida: {fila['faccion']!r} (elyos | asmodian)")
        return fila

    @staticmethod
    def _normalizar_perfil(datos: dict) -> dict:
        fila = {k: datos[k] for k in _COLS_PERFIL if k in datos}
        fila["id"] = str(fila.get("id") or uuid.uuid4())
        return fila

    @staticmethod
    def _preparar_lecturas(lecturas: list[Lectura], sesion_id: str | None
                           ) -> tuple[list[dict], list[dict], list[str]]:
        """Valida, asigna ids y ordena ofertas. Devuelve (filas, ofertas, ids)."""
        filas, ofertas, ids = [], [], []
        for lec in lecturas:
            if not isinstance(lec, Lectura):
                raise TypeError("guardar_lecturas espera objetos Lectura")
            if not lec.servidor_id:
                raise ValueError("Lectura sin servidor_id")
            if lec.fuente not in FUENTES:
                raise ValueError(f"Fuente no válida: {lec.fuente!r} ({', '.join(sorted(FUENTES))})")
            lec.id = _uuid(lec.id)
            lec.ofertas = sorted(((float(p), int(c)) for p, c in (lec.ofertas or [])),
                                 key=lambda o: o[0])
            filas.append({
                "id": lec.id,
                "servidor_id": str(lec.servidor_id),
                "objeto_id": int(lec.objeto_id),
                "fecha": _iso(lec.fecha),
                "precio_min": _num(lec.precio_min, float),
                "cantidad_total": _num(lec.cantidad_total, int),
                "num_anuncios": _num(lec.num_anuncios, int),
                "n_ofertas": len(lec.ofertas),
                "fuente": lec.fuente,
                "sesion_id": None if sesion_id is None else str(sesion_id),
            })
            ofertas.extend({"lectura_id": lec.id, "posicion": i, "precio": p, "cantidad": c}
                           for i, (p, c) in enumerate(lec.ofertas))
            ids.append(lec.id)
        return filas, ofertas, ids

    @staticmethod
    def _fila_operacion(perfil_id, tipo, objeto_id, cantidad, precio, fecha) -> dict:
        if tipo not in TIPOS_OPERACION:
            raise ValueError(f"Tipo de operación no válido: {tipo!r} (venta | compra)")
        return {
            "id": str(uuid.uuid4()),
            "perfil_id": None if perfil_id is None else str(perfil_id),
            "tipo": tipo,
            "objeto_id": int(objeto_id),
            "cantidad": int(cantidad),
            "precio": float(precio),
            "fecha": _iso(fecha or datetime.now(timezone.utc)),
        }

    @staticmethod
    def _filas_catalogo(datos: dict) -> dict[str, list[dict]]:
        objetos = [{
            "id": int(k),
            "nombre": v.get("nombre") or v.get("nombre_en") or str(k),
            "nombre_en": v.get("nombre_en"),
            "grado": v.get("grado"),
            "icono": v.get("icono"),
            "comerciable": v.get("comerciable"),
            "vinculado": v.get("vinculado"),
            "precio_npc": v.get("precio_npc"),
            "slug": v.get("slug"),
        } for k, v in (datos.get("objetos") or {}).items()]
        curvas = [{"id": str(k), "valores": list(v)} for k, v in (datos.get("curvas") or {}).items()]
        recetas, ingredientes = [], []
        for r in datos.get("recetas") or []:
            recetas.append({
                "id": int(r["id"]),
                "faccion": r.get("faccion") or "ambas",
                "profesion": r["profesion"],
                "nivel": int(r.get("nivel") or 0),
                "producto": int(r["producto"]),
                "cantidad": int(r.get("cantidad") or 1),
                "curva": r.get("curva"),
                "combo_pct": float(r.get("combo_pct") or 0),
                "curva_combo": r.get("curva_combo"),
                "producto_combo": _num(r.get("producto_combo"), int),
                "cantidad_combo": _num(r.get("cantidad_combo"), int),
            })
            ingredientes.extend({"receta_id": int(r["id"]), "posicion": i,
                                 "objeto_id": int(o), "cantidad": int(c)}
                                for i, (o, c) in enumerate(r.get("ingredientes") or []))
        return {"objetos": objetos, "curvas": curvas, "recetas": recetas,
                "receta_ingredientes": ingredientes}

    @staticmethod
    def _sumar_inventario(detalle: list[dict]) -> dict[int, int]:
        total: dict[int, int] = {}
        for f in detalle:
            total[int(f["objeto_id"])] = total.get(int(f["objeto_id"]), 0) + int(f["cantidad"])
        return {k: v for k, v in total.items() if v > 0}

    # --- por defecto (los sobrescribe Supabase) ---------------------------
    def subir_pendientes(self) -> int:
        return 0

    def num_pendientes(self) -> int:
        return 0

    def cerrar(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()


# ---------------------------------------------------------------------------
# SQLite local
# ---------------------------------------------------------------------------

_ESQUEMA_SQLITE = """
create table if not exists servidores (
    id text primary key, nombre text not null,
    faccion text not null check (faccion in ('elyos', 'asmodian')),
    region text, comision_registro real, impuesto_venta real,
    creado text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));
create table if not exists perfiles (
    id text primary key, nombre text not null,
    servidor_id text references servidores (id) on update cascade on delete set null,
    creado text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));
create table if not exists niveles (
    perfil_id text not null references perfiles (id) on update cascade on delete cascade,
    profesion text not null, nivel integer not null check (nivel >= 0),
    actualizado text, primary key (perfil_id, profesion));
create table if not exists inventario (
    perfil_id text not null references perfiles (id) on update cascade on delete cascade,
    objeto_id integer not null, ubicacion text not null default 'inventario',
    cantidad integer not null check (cantidad >= 0), actualizado text,
    primary key (perfil_id, objeto_id, ubicacion));
create table if not exists objetos (
    id integer primary key, nombre text not null, nombre_en text, grado text, icono text,
    comerciable integer, vinculado integer, precio_npc real, slug text);
create table if not exists curvas (id text primary key, valores text not null);
create table if not exists recetas (
    id integer primary key, faccion text not null, profesion text not null,
    nivel integer not null, producto integer not null, cantidad integer not null default 1,
    curva text, combo_pct real not null default 0, curva_combo text,
    producto_combo integer, cantidad_combo integer);
create table if not exists receta_ingredientes (
    receta_id integer not null references recetas (id) on delete cascade,
    posicion integer not null, objeto_id integer not null, cantidad integer not null,
    primary key (receta_id, posicion));
create table if not exists lecturas_mercado (
    id text primary key,
    servidor_id text not null references servidores (id) on update cascade,
    objeto_id integer not null, fecha text not null,
    precio_min real, cantidad_total integer, num_anuncios integer,
    n_ofertas integer not null default 0,
    fuente text not null check (fuente in ('grabacion', 'video', 'captura', 'manual', 'excel')),
    sesion_id text,
    creado text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));
create index if not exists lecturas_servidor_objeto_fecha
    on lecturas_mercado (servidor_id, objeto_id, fecha desc);
create index if not exists lecturas_sesion on lecturas_mercado (sesion_id);
create table if not exists ofertas (
    lectura_id text not null references lecturas_mercado (id) on delete cascade,
    posicion integer not null, precio real not null, cantidad integer not null,
    primary key (lectura_id, posicion));
create table if not exists precios_npc (
    objeto_id integer primary key, precio real not null, actualizado text);
create table if not exists operaciones (
    id text primary key,
    perfil_id text references perfiles (id) on update cascade on delete set null,
    tipo text not null check (tipo in ('venta', 'compra')),
    objeto_id integer not null, cantidad integer not null, precio real not null,
    fecha text not null,
    creado text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));
create index if not exists operaciones_perfil_fecha on operaciones (perfil_id, fecha desc);
create table if not exists ajustes (clave text primary key, valor text, actualizado text);

-- En SQLite no hay percentile_cont: p25/mediana/p75 solo existen en Supabase.
create view if not exists precio_diario as
select servidor_id, objeto_id, substr(fecha, 1, 10) as dia,
       min(precio_min) as precio_min, avg(precio_min) as precio_medio,
       avg(cantidad_total) as cantidad_media, count(*) as num_lecturas
from lecturas_mercado where precio_min is not null
group by servidor_id, objeto_id, substr(fecha, 1, 10);

create view if not exists ultima_lectura as
select * from (
    select l.*, row_number() over (
        partition by servidor_id, objeto_id order by fecha desc, creado desc) as _orden
    from lecturas_mercado l)
where _orden = 1;
"""


class RepositorioLocal(_RepositorioBase):
    backend = "local"

    def __init__(self, ruta_db: str | Path | None = None):
        self.ruta = Path(ruta_db) if ruta_db else RUTA_DATOS / "aion2.db"
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.ruta, timeout=30)
        try:
            con.execute("pragma journal_mode = wal")
            con.executescript(_ESQUEMA_SQLITE)
        finally:
            con.close()

    def __repr__(self) -> str:
        return f"RepositorioLocal({str(self.ruta)!r})"

    @contextmanager
    def _con(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.ruta, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("pragma foreign_keys = on")
        try:
            with con:  # commit al salir bien, rollback si hay excepción
                yield con
        except sqlite3.Error as e:
            raise ErrorBaseDatos(f"Error en la base de datos local: {e}") from e
        finally:
            con.close()

    def _filas(self, sql: str, params: Iterable = ()) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute(sql, tuple(params))]

    def _upsert(self, con, tabla: str, fila: dict, clave: tuple[str, ...]) -> None:
        cols = list(fila)
        actualizar = [c for c in cols if c not in clave]
        accion = ("do update set " + ", ".join(f"{c} = excluded.{c}" for c in actualizar)
                  if actualizar else "do nothing")
        con.execute(
            f"insert into {tabla} ({', '.join(cols)}) values ({', '.join('?' * len(cols))}) "
            f"on conflict ({', '.join(clave)}) {accion}",
            [fila[c] for c in cols])

    # --- servidores / perfiles ---------------------------------------------
    def listar_servidores(self) -> list[dict]:
        return self._filas(f"select {', '.join(_COLS_SERVIDOR)} from servidores order by nombre")

    def _guardar_por_id(self, tabla: str, cols: tuple[str, ...], fila: dict) -> dict:
        sql = f"select {', '.join(cols)} from {tabla} where id = ?"
        actual = self._filas(sql, [fila["id"]])
        fila = {**(actual[0] if actual else {}), **fila}  # actualizar solo lo indicado
        with self._con() as con:
            self._upsert(con, tabla, fila, ("id",))
        return self._filas(sql, [fila["id"]])[0]

    def guardar_servidor(self, datos: dict) -> dict:
        return self._guardar_por_id("servidores", _COLS_SERVIDOR, self._normalizar_servidor(datos))

    def listar_perfiles(self) -> list[dict]:
        return self._filas(f"select {', '.join(_COLS_PERFIL)} from perfiles order by nombre")

    def guardar_perfil(self, datos: dict) -> dict:
        return self._guardar_por_id("perfiles", _COLS_PERFIL, self._normalizar_perfil(datos))

    def niveles(self, perfil_id: str) -> dict[str, int]:
        return {f["profesion"]: int(f["nivel"]) for f in self._filas(
            "select profesion, nivel from niveles where perfil_id = ?", [perfil_id])}

    def guardar_nivel(self, perfil_id: str, profesion: str, nivel: int) -> None:
        with self._con() as con:
            self._upsert(con, "niveles", {"perfil_id": perfil_id, "profesion": profesion,
                                          "nivel": int(nivel), "actualizado": _ahora()},
                         ("perfil_id", "profesion"))

    def inventario(self, perfil_id: str) -> dict[int, int]:
        return self._sumar_inventario(self.inventario_detalle(perfil_id))

    def inventario_detalle(self, perfil_id: str) -> list[dict]:
        return self._filas("select objeto_id, cantidad, ubicacion from inventario "
                           "where perfil_id = ? order by objeto_id, ubicacion", [perfil_id])

    def guardar_inventario(self, perfil_id: str, objeto_id: int, cantidad: int,
                           ubicacion: str = "inventario") -> None:
        with self._con() as con:
            if int(cantidad) <= 0:
                con.execute("delete from inventario where perfil_id = ? and objeto_id = ? "
                            "and ubicacion = ?", (perfil_id, int(objeto_id), ubicacion))
            else:
                self._upsert(con, "inventario", {
                    "perfil_id": perfil_id, "objeto_id": int(objeto_id), "ubicacion": ubicacion,
                    "cantidad": int(cantidad), "actualizado": _ahora()},
                    ("perfil_id", "objeto_id", "ubicacion"))

    # --- mercado -------------------------------------------------------------
    def guardar_lecturas(self, lecturas: list[Lectura], sesion_id: str | None = None
                         ) -> ResultadoGuardado:
        filas, ofertas, ids = self._preparar_lecturas(lecturas, sesion_id)
        with self._con() as con:
            con.executemany(
                f"insert into lecturas_mercado ({', '.join(_COLS_LECTURA)}) "
                f"values ({', '.join('?' * len(_COLS_LECTURA))}) on conflict (id) do nothing",
                [[f[c] for c in _COLS_LECTURA] for f in filas])
            con.executemany(
                "insert into ofertas (lectura_id, posicion, precio, cantidad) values (?, ?, ?, ?) "
                "on conflict (lectura_id, posicion) do nothing",
                [(o["lectura_id"], o["posicion"], o["precio"], o["cantidad"]) for o in ofertas])
        return ResultadoGuardado(ids=ids, en_cola=False)

    def _ofertas_de(self, ids: list[str]) -> dict[str, list[tuple[float, int]]]:
        filas: list[dict] = []
        for trozo in _trozos(ids, 500):
            filas += self._filas(
                f"select lectura_id, posicion, precio, cantidad from ofertas "
                f"where lectura_id in ({', '.join('?' * len(trozo))})", trozo)
        return _agrupar_ofertas(filas)

    def verificar_lecturas(self, ids: list[str]) -> bool:
        ids = [str(i) for i in ids]
        if not all(_es_uuid(i) for i in ids):
            return False
        for trozo in _trozos(list(dict.fromkeys(ids)), 500):
            marcas = ", ".join("?" * len(trozo))
            esperadas = {f["id"]: f["n_ofertas"] for f in self._filas(
                f"select id, n_ofertas from lecturas_mercado where id in ({marcas})", trozo)}
            reales = {f["lectura_id"]: f["n"] for f in self._filas(
                f"select lectura_id, count(*) as n from ofertas where lectura_id in ({marcas}) "
                f"group by lectura_id", trozo)}
            for i in trozo:
                if i not in esperadas or reales.get(i, 0) != esperadas[i]:
                    return False
        return True

    def _a_lecturas(self, filas: list[dict]) -> list[Lectura]:
        ofertas = self._ofertas_de([f["id"] for f in filas])
        return [_lectura_de_fila(f, ofertas.get(f["id"], [])) for f in filas]

    def ultimas_lecturas(self, servidor_id: str) -> dict[int, Lectura]:
        filas = self._filas("select * from ultima_lectura where servidor_id = ?", [servidor_id])
        return {lec.objeto_id: lec for lec in self._a_lecturas(filas)}

    def historico(self, servidor_id: str, objeto_id: int, desde: datetime | None = None,
                  con_ofertas: bool = True) -> list[Lectura]:
        sql = "select * from lecturas_mercado where servidor_id = ? and objeto_id = ?"
        params: list = [servidor_id, int(objeto_id)]
        if desde is not None:
            sql += " and fecha >= ?"
            params.append(_iso(desde))
        filas = self._filas(sql + " order by fecha, creado", params)
        if not con_ofertas:
            return [_lectura_de_fila(f, []) for f in filas]
        return self._a_lecturas(filas)

    # --- otros -----------------------------------------------------------------
    def precios_npc(self) -> dict[int, float]:
        return {int(f["objeto_id"]): float(f["precio"])
                for f in self._filas("select objeto_id, precio from precios_npc")}

    def guardar_precio_npc(self, objeto_id: int, precio: float | None) -> None:
        with self._con() as con:
            if precio is None:
                con.execute("delete from precios_npc where objeto_id = ?", (int(objeto_id),))
            else:
                self._upsert(con, "precios_npc", {"objeto_id": int(objeto_id),
                                                  "precio": float(precio), "actualizado": _ahora()},
                             ("objeto_id",))

    def ajustes(self) -> dict:
        datos = dict(AJUSTES_POR_DEFECTO)
        for f in self._filas("select clave, valor from ajustes"):
            datos[f["clave"]] = json.loads(f["valor"]) if f["valor"] is not None else None
        return datos

    def guardar_ajustes(self, datos: dict) -> None:
        with self._con() as con:
            for clave, valor in datos.items():
                self._upsert(con, "ajustes", {"clave": str(clave), "valor": json.dumps(valor),
                                              "actualizado": _ahora()}, ("clave",))

    def registrar_operacion(self, perfil_id, tipo, objeto_id, cantidad, precio, fecha=None) -> dict:
        fila = self._fila_operacion(perfil_id, tipo, objeto_id, cantidad, precio, fecha)
        with self._con() as con:
            self._upsert(con, "operaciones", fila, ("id",))
        return fila

    def operaciones(self, perfil_id: str | None = None, desde: datetime | None = None) -> list[dict]:
        sql, params = f"select {', '.join(_COLS_OPERACION)} from operaciones where 1 = 1", []
        if perfil_id is not None:
            sql += " and perfil_id = ?"
            params.append(perfil_id)
        if desde is not None:
            sql += " and fecha >= ?"
            params.append(_iso(desde))
        return self._filas(sql + " order by fecha", params)

    def sincronizar_catalogo(self, datos: dict) -> dict[str, int]:
        """Copia data/catalogo.json (ya cargado como dict) a las tablas del catálogo."""
        tablas = self._filas_catalogo(datos)
        with self._con() as con:
            for f in tablas["objetos"]:
                self._upsert(con, "objetos", f, ("id",))
            for f in tablas["curvas"]:
                self._upsert(con, "curvas", {**f, "valores": json.dumps(f["valores"])}, ("id",))
            for f in tablas["recetas"]:
                self._upsert(con, "recetas", f, ("id",))
            con.execute("delete from receta_ingredientes")
            con.executemany(
                "insert into receta_ingredientes (receta_id, posicion, objeto_id, cantidad) "
                "values (:receta_id, :posicion, :objeto_id, :cantidad)",
                tablas["receta_ingredientes"])
        return {k: len(v) for k, v in tablas.items()}


# ---------------------------------------------------------------------------
# Supabase (PostgREST)
# ---------------------------------------------------------------------------

class RepositorioSupabase(_RepositorioBase):
    backend = "supabase"
    TAM_PAGINA = 1000   # máximo por defecto de filas por respuesta en Supabase
    TAM_LOTE = 500      # filas por POST
    TAM_IN = 50         # ids por filtro in.(...)

    def __init__(self, url: str, clave: str, ruta_cola: str | Path | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 15.0):
        url = (url or "").strip().rstrip("/")
        if url.endswith("/rest/v1"):
            url = url[: -len("/rest/v1")]
        local = url.startswith(("http://localhost", "http://127.0.0.1"))
        if not (url.startswith("https://") or local):
            raise ValueError("SUPABASE_URL debe empezar por https:// (la clave no se envía sin cifrar)")
        clave = (clave or "").strip()
        if not clave:
            raise ValueError("Falta SUPABASE_KEY")
        cabeceras = {"apikey": clave, "Accept": "application/json"}
        # Las claves antiguas (anon / service_role) son JWT y van también en Authorization.
        # Las nuevas (sb_secret_... / sb_publishable_...) no son JWT: solo en apikey.
        if clave.startswith("eyJ"):
            cabeceras["Authorization"] = f"Bearer {clave}"
        if clave.startswith("sb_publishable_"):
            log.warning("SUPABASE_KEY es la clave pública: con el RLS del esquema no podrá leer "
                        "ni escribir. Usa la clave secreta (ver docs/supabase.md).")
        self.url = url
        self._http = httpx.Client(base_url=url + "/rest/v1", headers=cabeceras,
                                  timeout=httpx.Timeout(timeout, connect=5.0), transport=transport)
        self.ruta_cola = Path(ruta_cola) if ruta_cola else RUTA_DATOS / "pendientes.jsonl"
        self._candado = _candado(self.ruta_cola)

    def __repr__(self) -> str:  # nunca mostrar la clave
        return f"RepositorioSupabase({self.url!r})"

    def cerrar(self) -> None:
        self._http.close()

    # --- HTTP ----------------------------------------------------------------
    def _peticion(self, metodo: str, ruta: str, params: list[tuple[str, Any]] | None = None,
                  cuerpo: Any = None, prefer: str | None = None) -> httpx.Response:
        cabeceras = {"Prefer": prefer} if prefer else {}
        try:
            r = self._http.request(metodo, "/" + ruta, params=params, json=cuerpo,
                                   headers=cabeceras)
        except httpx.TransportError as e:
            raise ErrorRed(f"Sin conexión con Supabase ({type(e).__name__})") from e
        if r.status_code >= 500 or r.status_code in (408, 429):
            raise ErrorRed(f"Supabase no disponible (HTTP {r.status_code})")
        if r.status_code >= 400:
            try:
                info = r.json()
                detalle = info.get("message") or info.get("hint") or r.text
            except ValueError:
                detalle = r.text
            raise ErrorBaseDatos(f"Supabase rechazó la petición a {ruta} "
                                 f"(HTTP {r.status_code}): {detalle[:300]}")
        return r

    def _get(self, tabla: str, params: list[tuple[str, Any]]) -> list[dict]:
        filas: list[dict] = []
        desplazamiento = 0
        while True:
            pagina = self._peticion("GET", tabla, params + [
                ("limit", self.TAM_PAGINA), ("offset", desplazamiento)]).json()
            filas.extend(pagina)
            if len(pagina) < self.TAM_PAGINA:
                return filas
            desplazamiento += self.TAM_PAGINA

    def _insertar(self, tabla: str, filas: list[dict], conflicto: str,
                  duplicados: str = "merge", devolver: bool = False) -> list[dict]:
        prefer = (f"resolution={'merge' if duplicados == 'merge' else 'ignore'}-duplicates,"
                  f"return={'representation' if devolver else 'minimal'}")
        salida: list[dict] = []
        for lote in _trozos(filas, self.TAM_LOTE):
            r = self._peticion("POST", tabla, [("on_conflict", conflicto)], lote, prefer)
            if devolver:
                salida.extend(r.json())
        return salida

    def _borrar(self, tabla: str, filtros: list[tuple[str, Any]]) -> None:
        self._peticion("DELETE", tabla, filtros, prefer="return=minimal")

    @staticmethod
    def _en(ids: list[str]) -> str:
        return "in.(" + ",".join(ids) + ")"

    # --- servidores / perfiles ---------------------------------------------
    def listar_servidores(self) -> list[dict]:
        return self._get("servidores", [("select", ",".join(_COLS_SERVIDOR)), ("order", "nombre")])

    def _guardar_por_id(self, tabla: str, cols: tuple[str, ...], fila: dict) -> dict:
        # Postgres comprueba NOT NULL antes del ON CONFLICT: mezclar con lo existente
        # para poder actualizar solo algunos campos.
        actual = self._get(tabla, [("select", ",".join(cols)), ("id", f"eq.{fila['id']}")])
        fila = {**(actual[0] if actual else {}), **fila}
        res = self._insertar(tabla, [fila], "id", devolver=True)
        return {k: res[0].get(k) for k in cols}

    def guardar_servidor(self, datos: dict) -> dict:
        return self._guardar_por_id("servidores", _COLS_SERVIDOR, self._normalizar_servidor(datos))

    def listar_perfiles(self) -> list[dict]:
        return self._get("perfiles", [("select", ",".join(_COLS_PERFIL)), ("order", "nombre")])

    def guardar_perfil(self, datos: dict) -> dict:
        return self._guardar_por_id("perfiles", _COLS_PERFIL, self._normalizar_perfil(datos))

    def niveles(self, perfil_id: str) -> dict[str, int]:
        return {f["profesion"]: int(f["nivel"]) for f in self._get(
            "niveles", [("select", "profesion,nivel"), ("perfil_id", f"eq.{perfil_id}"),
                        ("order", "profesion")])}

    def guardar_nivel(self, perfil_id: str, profesion: str, nivel: int) -> None:
        self._insertar("niveles", [{"perfil_id": perfil_id, "profesion": profesion,
                                    "nivel": int(nivel), "actualizado": _ahora()}],
                       "perfil_id,profesion")

    def inventario(self, perfil_id: str) -> dict[int, int]:
        return self._sumar_inventario(self.inventario_detalle(perfil_id))

    def inventario_detalle(self, perfil_id: str) -> list[dict]:
        return self._get("inventario", [("select", "objeto_id,cantidad,ubicacion"),
                                        ("perfil_id", f"eq.{perfil_id}"),
                                        ("order", "objeto_id,ubicacion")])

    def guardar_inventario(self, perfil_id: str, objeto_id: int, cantidad: int,
                           ubicacion: str = "inventario") -> None:
        if int(cantidad) <= 0:
            self._borrar("inventario", [("perfil_id", f"eq.{perfil_id}"),
                                        ("objeto_id", f"eq.{int(objeto_id)}"),
                                        ("ubicacion", f"eq.{ubicacion}")])
        else:
            self._insertar("inventario", [{
                "perfil_id": perfil_id, "objeto_id": int(objeto_id), "ubicacion": ubicacion,
                "cantidad": int(cantidad), "actualizado": _ahora()}],
                "perfil_id,objeto_id,ubicacion")

    # --- mercado -------------------------------------------------------------
    def _subir_lecturas(self, filas: list[dict], ofertas: list[dict]) -> None:
        # Idempotente: reintentar un lote ya subido (entero o a medias) no duplica nada.
        self._insertar("lecturas_mercado", filas, "id", duplicados="ignore")
        if ofertas:
            self._insertar("ofertas", ofertas, "lectura_id,posicion", duplicados="ignore")

    def guardar_lecturas(self, lecturas: list[Lectura], sesion_id: str | None = None
                         ) -> ResultadoGuardado:
        filas, ofertas, ids = self._preparar_lecturas(lecturas, sesion_id)
        if not filas:
            return ResultadoGuardado(ids=[], en_cola=False)
        try:
            self._subir_lecturas(filas, ofertas)
        except ErrorBaseDatos as e:
            # Sin red, o Supabase lo rechazó: nunca perder datos (pueden venir de una
            # grabación que solo estaba en memoria). Se reintenta con subir_pendientes().
            log.warning("Lecturas guardadas en la cola local: %s", e)
            self._encolar({"tipo": "lecturas", "filas": filas, "ofertas": ofertas, "error": str(e)})
            return ResultadoGuardado(ids=ids, en_cola=True, error=str(e))
        if self.num_pendientes():
            try:
                self.subir_pendientes()  # hay red: aprovechar para vaciar la cola
            except Exception as e:  # noqa: BLE001 - nunca romper el guardado por esto
                log.warning("No se pudo vaciar la cola: %s", e)
        return ResultadoGuardado(ids=ids, en_cola=False)

    def verificar_lecturas(self, ids: list[str]) -> bool:
        """True solo si todas las lecturas están en Supabase con todas sus ofertas.

        Devuelve False (no lanza) si alguna sigue en la cola o si no hay conexión:
        ante la duda, no se borran los archivos temporales.
        """
        ids = list(dict.fromkeys(str(i) for i in ids))
        if not ids:
            return True
        if not all(_es_uuid(i) for i in ids):
            return False
        if set(ids) & self._ids_en_cola():
            return False
        try:
            for trozo in _trozos(ids, self.TAM_IN):
                esperadas = {str(f["id"]): int(f["n_ofertas"]) for f in self._get(
                    "lecturas_mercado", [("select", "id,n_ofertas"), ("id", self._en(trozo)),
                                         ("order", "id")])}
                reales: dict[str, int] = {}
                for f in self._get("ofertas", [("select", "lectura_id"),
                                               ("lectura_id", self._en(trozo)),
                                               ("order", "lectura_id,posicion")]):
                    reales[str(f["lectura_id"])] = reales.get(str(f["lectura_id"]), 0) + 1
                for i in trozo:
                    if i not in esperadas or reales.get(i, 0) != esperadas[i]:
                        return False
        except ErrorBaseDatos as e:
            log.warning("No se pudieron verificar las lecturas: %s", e)
            return False
        return True

    def _a_lecturas(self, filas: list[dict]) -> list[Lectura]:
        ids = [str(f["id"]) for f in filas]
        ofertas_filas: list[dict] = []
        for trozo in _trozos(ids, self.TAM_IN):
            ofertas_filas += self._get("ofertas", [
                ("select", "lectura_id,posicion,precio,cantidad"),
                ("lectura_id", self._en(trozo)), ("order", "lectura_id,posicion")])
        ofertas = _agrupar_ofertas(ofertas_filas)
        return [_lectura_de_fila(f, ofertas.get(str(f["id"]), [])) for f in filas]

    def ultimas_lecturas(self, servidor_id: str) -> dict[int, Lectura]:
        filas = self._get("ultima_lectura", [("select", ",".join(_COLS_LECTURA)),
                                             ("servidor_id", f"eq.{servidor_id}"),
                                             ("order", "objeto_id")])
        return {lec.objeto_id: lec for lec in self._a_lecturas(filas)}

    def historico(self, servidor_id: str, objeto_id: int, desde: datetime | None = None,
                  con_ofertas: bool = True) -> list[Lectura]:
        params = [("select", ",".join(_COLS_LECTURA)), ("servidor_id", f"eq.{servidor_id}"),
                  ("objeto_id", f"eq.{int(objeto_id)}"), ("order", "fecha.asc,id.asc")]
        if desde is not None:
            params.append(("fecha", f"gte.{_iso(desde)}"))
        filas = self._get("lecturas_mercado", params)
        if not con_ofertas:
            return [_lectura_de_fila(f, []) for f in filas]
        return self._a_lecturas(filas)

    # --- cola offline ----------------------------------------------------------
    def _leer_cola(self) -> list[dict]:
        if not self.ruta_cola.exists():
            return []
        entradas = []
        for linea in self.ruta_cola.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            try:
                entradas.append(json.loads(linea))
            except json.JSONDecodeError:
                # Línea a medio escribir (p.ej. corte de luz): se conserva tal cual.
                entradas.append({"cola_id": "corrupta-" + hashlib.sha1(linea.encode()).hexdigest(),
                                 "tipo": "corrupta", "texto": linea})
        return entradas

    def _escribir_cola(self, entradas: list[dict]) -> None:
        if not entradas:
            self.ruta_cola.unlink(missing_ok=True)
            return
        tmp = self.ruta_cola.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for e in entradas:
                f.write((e["texto"] if e.get("tipo") == "corrupta"
                         else json.dumps(e, ensure_ascii=False)) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.ruta_cola)

    def _encolar(self, entrada: dict) -> None:
        entrada = {"cola_id": str(uuid.uuid4()), "encolado": _ahora(), "intentos": 0, **entrada}
        with self._candado:
            self.ruta_cola.parent.mkdir(parents=True, exist_ok=True)
            with self.ruta_cola.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def _ids_en_cola(self) -> set[str]:
        with self._candado:
            entradas = self._leer_cola()
        return {f["id"] for e in entradas if e.get("tipo") == "lecturas" for f in e["filas"]}

    def num_pendientes(self) -> int:
        """Nº de lecturas/operaciones esperando en la cola local."""
        with self._candado:
            return sum(len(e.get("filas", [])) for e in self._leer_cola())

    def pendientes(self) -> list[dict]:
        """Resumen de la cola (para mostrar en el panel)."""
        with self._candado:
            return [{"cola_id": e["cola_id"], "tipo": e.get("tipo"),
                     "filas": len(e.get("filas", [])), "encolado": e.get("encolado"),
                     "intentos": e.get("intentos", 0), "error": e.get("error")}
                    for e in self._leer_cola()]

    def _procesar_entrada(self, e: dict) -> None:
        if e.get("tipo") == "lecturas":
            self._subir_lecturas(e["filas"], e.get("ofertas", []))
        elif e.get("tipo") == "operacion":
            self._insertar("operaciones", e["filas"], "id", duplicados="ignore")
        else:
            raise ErrorBaseDatos("Entrada de la cola ilegible; se conserva en pendientes.jsonl")

    def subir_pendientes(self) -> int:
        """Sube la cola offline. Devuelve el nº de lecturas/operaciones subidas.

        Si se corta la red a mitad, para y deja el resto. Si Supabase rechaza una
        entrada (p.ej. servidor inexistente), la conserva con el error y sigue.
        """
        with self._candado:
            entradas = self._leer_cola()
        hechas: set[str] = set()
        errores: dict[str, str] = {}
        subidas = 0
        for e in entradas:
            try:
                self._procesar_entrada(e)
            except ErrorRed as err:
                errores[e["cola_id"]] = str(err)
                break
            except ErrorBaseDatos as err:
                errores[e["cola_id"]] = str(err)
                continue
            hechas.add(e["cola_id"])
            subidas += len(e.get("filas", []))
        if hechas or errores:
            with self._candado:
                # Releer: otro hilo pudo añadir entradas mientras subíamos.
                restantes = [e for e in self._leer_cola() if e["cola_id"] not in hechas]
                for e in restantes:
                    if e["cola_id"] in errores and e.get("tipo") != "corrupta":
                        e["error"] = errores[e["cola_id"]]
                        e["intentos"] = int(e.get("intentos", 0)) + 1
                self._escribir_cola(restantes)
        return subidas

    # --- otros -----------------------------------------------------------------
    def precios_npc(self) -> dict[int, float]:
        return {int(f["objeto_id"]): float(f["precio"]) for f in self._get(
            "precios_npc", [("select", "objeto_id,precio"), ("order", "objeto_id")])}

    def guardar_precio_npc(self, objeto_id: int, precio: float | None) -> None:
        if precio is None:
            self._borrar("precios_npc", [("objeto_id", f"eq.{int(objeto_id)}")])
        else:
            self._insertar("precios_npc", [{"objeto_id": int(objeto_id), "precio": float(precio),
                                            "actualizado": _ahora()}], "objeto_id")

    def ajustes(self) -> dict:
        datos = dict(AJUSTES_POR_DEFECTO)
        for f in self._get("ajustes", [("select", "clave,valor"), ("order", "clave")]):
            datos[f["clave"]] = f["valor"]
        return datos

    def guardar_ajustes(self, datos: dict) -> None:
        filas = [{"clave": str(k), "valor": v, "actualizado": _ahora()} for k, v in datos.items()]
        if filas:
            self._insertar("ajustes", filas, "clave")

    def registrar_operacion(self, perfil_id, tipo, objeto_id, cantidad, precio, fecha=None) -> dict:
        """Guarda una venta/compra propia (precio por unidad). Sin red, va a la cola."""
        fila = self._fila_operacion(perfil_id, tipo, objeto_id, cantidad, precio, fecha)
        try:
            self._insertar("operaciones", [fila], "id", duplicados="ignore")
        except ErrorRed as e:
            self._encolar({"tipo": "operacion", "filas": [fila], "error": str(e)})
            return {**fila, "en_cola": True}
        return fila

    def operaciones(self, perfil_id: str | None = None, desde: datetime | None = None) -> list[dict]:
        params = [("select", ",".join(_COLS_OPERACION)), ("order", "fecha.asc,id.asc")]
        if perfil_id is not None:
            params.append(("perfil_id", f"eq.{perfil_id}"))
        if desde is not None:
            params.append(("fecha", f"gte.{_iso(desde)}"))
        return self._get("operaciones", params)

    def sincronizar_catalogo(self, datos: dict) -> dict[str, int]:
        """Copia data/catalogo.json (ya cargado como dict) a las tablas del catálogo."""
        tablas = self._filas_catalogo(datos)
        self._insertar("objetos", tablas["objetos"], "id")
        self._insertar("curvas", tablas["curvas"], "id")
        self._insertar("recetas", tablas["recetas"], "id")
        self._borrar("receta_ingredientes", [("receta_id", "not.is.null")])
        self._insertar("receta_ingredientes", tablas["receta_ingredientes"], "receta_id,posicion")
        return {k: len(v) for k, v in tablas.items()}


# ---------------------------------------------------------------------------
# Elección de backend
# ---------------------------------------------------------------------------

def obtener_repositorio(backend: str | None = None, ruta_env: str | Path | None = None,
                        ruta_datos: str | Path | None = None,
                        transport: httpx.BaseTransport | None = None):
    """Devuelve RepositorioSupabase si hay SUPABASE_URL y SUPABASE_KEY (variables de
    entorno o .env); si no, RepositorioLocal. `backend` fuerza "local" o "supabase"."""
    ruta_env = Path(ruta_env) if ruta_env else RUTA_ENV
    datos = Path(ruta_datos) if ruta_datos else RUTA_DATOS
    valores = dotenv_values(ruta_env) if ruta_env.exists() else {}
    url = (os.environ.get("SUPABASE_URL") or valores.get("SUPABASE_URL") or "").strip()
    clave = (os.environ.get("SUPABASE_KEY") or valores.get("SUPABASE_KEY") or "").strip()

    if backend is None:
        backend = "supabase" if url and clave else "local"
    if backend == "local":
        return RepositorioLocal(datos / "aion2.db")
    if backend == "supabase":
        if not (url and clave):
            raise ErrorBaseDatos("Faltan SUPABASE_URL o SUPABASE_KEY en .env (ver docs/supabase.md)")
        return RepositorioSupabase(url, clave, ruta_cola=datos / "pendientes.jsonl",
                                   transport=transport)
    raise ValueError(f"Backend desconocido: {backend!r} (local | supabase)")
