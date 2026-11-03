"""Service layer: ties together catalog, repository, calculation engine and capture for the API.

The catalog (data/catalogo.json) and the database are loaded on first use: if either is
missing or misconfigured, the operations that need it raise `NoDisponible` (HTTP 503) with a
message in Spanish and the rest of the app keeps working.

Tests can inject them: Servicios(catalogo=Catalogo(...), repo=RepositorioLocal(...)).
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app import calculo, precio_objetivo
from app.captura import calibracion, grabacion, parser, temporales, video
from app.catalogo import Catalogo, cargar_catalogo
from app.db import Lectura, obtener_repositorio
from app.precio_objetivo import campo

log = logging.getLogger("aion2.servicios")

RAIZ = Path(__file__).resolve().parent.parent
DIR_TMP = RAIZ / "capturas" / "tmp"
RUTA_SESIONES = RAIZ / "data" / "captura_sesiones.json"
RUTA_COLA = RAIZ / "data" / "pendientes.jsonl"

PROFESIONES = {"herreria": "Herrería", "armadura": "Armadura", "orfebreria": "Orfebrería",
               "alquimia": "Alquimia", "cocina": "Cocina"}
FACCIONES = {"elyos": "Elyos", "asmodian": "Asmodian"}

# defaults shown in the Settings tab (the engine fills in the rest from calculo.AJUSTES_POR_DEFECTO)
AJUSTES_POR_DEFECTO = {
    **{k: calculo.AJUSTES_POR_DEFECTO[k] for k in (
        "comision_registro", "impuesto_venta", "rebaja_listado", "combo_fallido", "valorar_inventario")},
    "tope_tmp_mb": 500,
    "horas_precio_antiguo": 24,
}
# keys editable from the Settings tab and their type
_AJUSTES_EDITABLES = {
    "comision_registro": float, "impuesto_venta": float, "rebaja_listado": float,
    "combo_fallido": str, "valorar_inventario": str, "tope_tmp_mb": int,
    "horas_precio_antiguo": float, "tope_intentos": int, "max_anuncios": int,
    "unidades_por_anuncio": int, "anuncios_saturado": int,
}
_OPCIONES = {"combo_fallido": {"pierde_todo", "queda_base"}, "valorar_inventario": {"mercado", "cero"}}

FUENTE_POR_ORIGEN = {"grabacion": "grabacion", "video": "video", "imagen": "captura"}
EXT_VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v"}
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# price age traffic light (hours)
SEMAFORO_VERDE_H = 6
SEMAFORO_AMBAR_H = 24

# components listed in /api/estado; only the catalog and the database can be missing
COMPONENTES = ("catalogo", "repo", "motor", "precio_objetivo", "ocr", "parser",
               "grabacion", "video", "calibracion", "temporales")
_FALTA = {
    "catalogo": "El catálogo de recetas no está disponible todavía (data/catalogo.json). "
                "Genera el catálogo con tools\\importar_metabot.py.",
    "repo": "La base de datos no está disponible todavía (.env o data/aion2.db).",
}


class NoDisponible(RuntimeError):
    """The catalog or the database could not be loaded."""

    def __init__(self, componente: str, detalle: str | None = None):
        self.componente = componente
        super().__init__(_FALTA[componente] + (f" Detalle: {detalle}" if detalle else ""))


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------

def utc(fecha) -> datetime | None:
    if fecha is None or fecha == "":
        return None
    if isinstance(fecha, str):
        texto = fecha.strip().replace("Z", "+00:00")
        if len(texto) == 10:
            texto += "T12:00:00"
        fecha = datetime.fromisoformat(texto)
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def iso(fecha) -> str | None:
    f = utc(fecha)
    return f.isoformat().replace("+00:00", "Z") if f else None


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def horas_desde(fecha) -> float | None:
    f = utc(fecha)
    return None if f is None else max(0.0, (ahora() - f).total_seconds() / 3600.0)


def semaforo(horas: float | None) -> str:
    if horas is None:
        return "gris"
    if horas <= SEMAFORO_VERDE_H:
        return "verde"
    if horas <= SEMAFORO_AMBAR_H:
        return "ambar"
    return "rojo"


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto.lower()).strip()


def limpio(valor):
    """Prepares a value for JSON: no NaN/inf, dataclasses → dict, dates → ISO."""
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, datetime):
        return iso(valor)
    if is_dataclass(valor) and not isinstance(valor, type):
        return limpio(asdict(valor))
    if isinstance(valor, dict):
        return {(k if isinstance(k, str) else str(k)): limpio(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [limpio(v) for v in valor]
    return valor


def _num(valor, tipo=float, nombre="valor", minimo=None, permitir_none=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if permitir_none:
            return None
        raise ValueError(f"Falta {nombre}.")
    try:
        if isinstance(valor, str):
            valor = valor.strip().replace(" ", "")
            if tipo is int or re.fullmatch(r"\d{1,3}([.,]\d{3})+", valor):
                valor = valor.replace(".", "").replace(",", "")
            else:
                valor = valor.replace(",", ".")
        n = tipo(float(valor)) if tipo is int else tipo(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} no es un número válido: {valor!r}") from None
    if minimo is not None and n < minimo:
        raise ValueError(f"{nombre} no puede ser menor que {minimo}.")
    return n


def _entero_texto(texto: str) -> int | None:
    limpio_ = re.sub(r"[\s.,'’]", "", texto or "")
    return int(limpio_) if limpio_.isdigit() else None


# ---------------------------------------------------------------------------
# services
# ---------------------------------------------------------------------------

class Servicios:
    TOP_ESCENARIOS = 15        # dashboard rows with the "sell at target price" scenario
    TTL_OBJETIVO_S = 300

    def __init__(self, catalogo: Catalogo | None = None, repo=None, ruta_sesiones: Path | None = None):
        self._cat = catalogo
        self._repo = repo
        self._lock = threading.RLock()
        self._cache_objetivo: dict[tuple, tuple[float, dict]] = {}
        self.grabacion = None
        self.grabacion_servidor = None
        self.sesiones: dict[str, dict] = {}
        self.ruta_sesiones = ruta_sesiones if ruta_sesiones is not None else RUTA_SESIONES
        self.arranque_info: dict = {}
        self.segundo_plano = True   # process videos/images in a thread (tests turn this off)
        self._cargar_sesiones()

    # --- catalog and database (loaded on first use) -------------------------
    @property
    def cat(self) -> Catalogo:
        if self._cat is None:
            with self._lock:
                if self._cat is None:
                    try:
                        self._cat = cargar_catalogo()
                    except FileNotFoundError as e:
                        raise NoDisponible("catalogo", f"no existe {e.filename or 'data/catalogo.json'}") from e
                    except Exception as e:  # noqa: BLE001
                        raise NoDisponible("catalogo", f"{type(e).__name__}: {e}") from e
        return self._cat

    @property
    def repo(self):
        if self._repo is None:
            with self._lock:
                if self._repo is None:
                    try:
                        self._repo = obtener_repositorio()
                    except Exception as e:  # noqa: BLE001
                        raise NoDisponible("repo", f"{type(e).__name__}: {e}") from e
        return self._repo

    def _cat_o_none(self) -> Catalogo | None:
        try:
            return self.cat
        except NoDisponible:
            return None

    def _error_de(self, componente: str) -> str | None:
        try:
            getattr(self, "cat" if componente == "catalogo" else componente)
            return None
        except NoDisponible as e:
            return str(e)

    # --- startup -------------------------------------------------------------
    def arranque(self) -> dict:
        """Loads the catalog, uploads the offline queue and cleans up verified temporary files."""
        info: dict[str, Any] = {"inicio": iso(ahora())}
        try:
            info["recetas"] = len(self.cat.recetas)
        except NoDisponible as e:
            info["catalogo"] = str(e)
        try:
            info["subidas_cola"] = self.repo.subir_pendientes()
        except NoDisponible as e:
            info["repo"] = str(e)
        except Exception as e:  # noqa: BLE001
            info["repo"] = f"No se pudo subir la cola offline: {e}"
        try:
            info["temporales_borrados"] = limpio(temporales.limpiar_verificados(self.repo))
            tope = self.ajustes().get("tope_tmp_mb", 500)
            info["tope"] = limpio(temporales.aplicar_tope(tope, repo=self.repo))
        except NoDisponible as e:
            info["temporales"] = str(e)
        except Exception as e:  # noqa: BLE001
            info["temporales"] = f"No se pudieron limpiar los temporales: {e}"
        info["fin"] = iso(ahora())
        self.arranque_info = info
        log.info("Startup: %s", info)
        return info

    # --- status ----------------------------------------------------------------
    def estado(self) -> dict:
        errores = {k: self._error_de(k) for k in ("catalogo", "repo")}
        componentes = {k: {"ok": errores.get(k) is None, "mensaje": errores.get(k)} for k in COMPONENTES}
        salida: dict[str, Any] = {"componentes": componentes, "arranque": self.arranque_info}
        if errores["catalogo"] is None:
            c = self.cat
            salida["catalogo"] = {"recetas": len(c.recetas), "objetos": len(c.objetos), **c.meta}
        if errores["repo"] is None:
            salida["backend"] = self.repo.backend
            try:
                salida["en_cola"] = int(self.repo.num_pendientes())
            except Exception as e:  # noqa: BLE001
                salida["en_cola"] = None
                salida["error_cola"] = str(e)
        else:
            salida["backend"] = None
            salida["en_cola"] = self._contar_cola()
        salida["temporales"] = self._estado_temporales()
        return limpio(salida)

    @staticmethod
    def _contar_cola() -> int:
        try:
            with open(RUTA_COLA, encoding="utf-8") as f:
                return sum(1 for linea in f if linea.strip())
        except FileNotFoundError:
            return 0

    def _estado_temporales(self) -> dict:
        archivos = [p for p in DIR_TMP.rglob("*") if p.is_file()] if DIR_TMP.exists() else []
        try:
            tope = self.ajustes().get("tope_tmp_mb")
        except NoDisponible:
            tope = None
        return {"archivos": len(archivos), "mb": round(sum(p.stat().st_size for p in archivos) / 1_048_576, 1),
                "tope_mb": tope}

    # --- catalog search -----------------------------------------------------------
    def buscar(self, texto: str, limite: int = 10) -> list[dict]:
        texto = (texto or "").strip()
        if not texto:
            return []
        cat = self.cat
        if texto.isdigit() and cat.objeto(texto):
            return [self._resultado(int(texto), 100)]
        return [self._resultado(oid, punt) for oid, _, punt in cat.buscar(texto, limite=limite)]

    def _resultado(self, oid: int, puntuacion) -> dict:
        cat = self.cat
        o = cat.objeto(oid) or {}
        return {"id": oid, "nombre": cat.nombre(oid), "nombre_en": o.get("nombre_en"),
                "puntuacion": round(float(puntuacion or 0), 1), "vinculado": o.get("vinculado"),
                "comerciable": o.get("comerciable"), "fabricable": bool(cat.recetas_que_producen(oid, con_combo=True))}

    # --- profiles / servers ---------------------------------------------------
    def servidores(self) -> list[dict]:
        return self.repo.listar_servidores()

    def guardar_servidor(self, datos: dict) -> dict:
        datos = dict(datos or {})
        if not (datos.get("nombre") or "").strip():
            raise ValueError("El servidor necesita un nombre.")
        faccion = (datos.get("faccion") or "").strip().lower()
        if faccion not in FACCIONES:
            raise ValueError("La facción debe ser «elyos» o «asmodian».")
        fila = {"nombre": datos["nombre"].strip(), "faccion": faccion,
                "region": (datos.get("region") or "EU").strip() or "EU"}
        if datos.get("id"):
            fila["id"] = str(datos["id"])
        else:
            fila["id"] = self._id_libre(fila["nombre"], {s["id"] for s in self.repo.listar_servidores()})
        for k in ("comision_registro", "impuesto_venta"):
            if k in datos:
                v = _num(datos.get(k), float, k, 0)
                if v is not None and v > 1:
                    v = v / 100.0  # accept a percentage
                fila[k] = v
        return self.repo.guardar_servidor(fila)

    def perfiles(self) -> list[dict]:
        servidores = {s["id"]: s for s in self.repo.listar_servidores()}
        salida = []
        for p in self.repo.listar_perfiles():
            s = servidores.get(p.get("servidor_id"))
            salida.append({**p, "servidor": s, "faccion": s.get("faccion") if s else None})
        return salida

    def guardar_perfil(self, datos: dict) -> dict:
        datos = dict(datos or {})
        if not (datos.get("nombre") or "").strip():
            raise ValueError("El perfil necesita un nombre (tu personaje).")
        fila = {"nombre": datos["nombre"].strip(), "servidor_id": datos.get("servidor_id") or None}
        if fila["servidor_id"] and fila["servidor_id"] not in {s["id"] for s in self.repo.listar_servidores()}:
            raise ValueError("Ese servidor no existe: créalo primero.")
        fila["id"] = str(datos.get("id") or self._id_libre(fila["nombre"], {p["id"] for p in self.repo.listar_perfiles()}))
        return self.repo.guardar_perfil(fila)

    @staticmethod
    def _id_libre(nombre: str, usados: set) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", normalizar(nombre)).strip("-") or "id"
        candidato, i = base, 2
        while candidato in usados:
            candidato, i = f"{base}-{i}", i + 1
        return candidato

    def contexto(self, perfil_id: str | None) -> dict:
        """Profile, server, faction, levels, inventory and effective settings."""
        perfiles = self.repo.listar_perfiles()
        perfil = None
        if perfil_id:
            perfil = next((p for p in perfiles if str(p["id"]) == str(perfil_id)), None)
            if perfil is None:
                raise LookupError("Ese perfil no existe.")
        elif perfiles:
            perfil = perfiles[0]
        servidor = None
        if perfil and perfil.get("servidor_id"):
            servidor = next((s for s in self.repo.listar_servidores() if s["id"] == perfil["servidor_id"]), None)
        pid = perfil["id"] if perfil else None
        return {
            "perfil": perfil,
            "servidor": servidor,
            "servidor_id": servidor["id"] if servidor else None,
            "faccion": servidor.get("faccion") if servidor else None,
            "niveles": self.repo.niveles(pid) if pid else {},
            "inventario": {int(k): int(v) for k, v in (self.repo.inventario(pid) if pid else {}).items()},
            "ajustes": self.ajustes_efectivos(servidor),
        }

    # --- levels and inventory ---------------------------------------------------
    def niveles(self, perfil_id) -> dict:
        actuales = self.repo.niveles(perfil_id)
        cat = self._cat_o_none()
        claves = list(cat.profesiones if cat else PROFESIONES)
        return {k: int(actuales.get(k, 1)) for k in claves} | {k: v for k, v in actuales.items() if k not in claves}

    def guardar_niveles(self, perfil_id, niveles: dict) -> dict:
        self._exigir_perfil(perfil_id)
        for prof, nivel in (niveles or {}).items():
            n = _num(nivel, int, f"nivel de {prof}", 0, permitir_none=False)
            if n > 100:
                raise ValueError("El nivel máximo de artesanía es 100.")
            self.repo.guardar_nivel(perfil_id, prof, n)
        return self.niveles(perfil_id)

    def _exigir_perfil(self, perfil_id):
        if not any(str(p["id"]) == str(perfil_id) for p in self.repo.listar_perfiles()):
            raise LookupError("Ese perfil no existe.")

    def inventario(self, perfil_id) -> list[dict]:
        cat = self._cat_o_none()
        salida = [{**f, "objeto_id": int(f["objeto_id"]),
                   "nombre": cat.nombre(f["objeto_id"]) if cat else f"#{f['objeto_id']}"}
                  for f in self.repo.inventario_detalle(perfil_id)]
        salida.sort(key=lambda f: (f.get("ubicacion") or "", normalizar(f["nombre"])))
        return salida

    def guardar_inventario(self, perfil_id, filas: list[dict]) -> list[dict]:
        self._exigir_perfil(perfil_id)
        for f in filas or []:
            oid = _num(f.get("objeto_id"), int, "objeto", permitir_none=False)
            cant = _num(f.get("cantidad"), int, "cantidad", 0, permitir_none=False)
            ubic = (f.get("ubicacion") or "inventario").strip().lower()
            if ubic not in ("inventario", "almacen"):
                raise ValueError("La ubicación debe ser «inventario» o «almacen».")
            self.repo.guardar_inventario(perfil_id, oid, cant, ubic)
        return self.inventario(perfil_id)

    _RE_NOMBRE_CANT = re.compile(r"^(?P<nombre>.*?\S)\s*(?:[:=\t;]|\s[xX×]\s*|\s{2,}|\s(?=\d))\s*(?P<cant>\d[\d.,' ]*)$")
    _RE_CANT_NOMBRE = re.compile(r"^(?P<cant>\d[\d.,']*)\s*[xX×]?\s+(?P<nombre>\D.*)$")

    def interpretar_pegado(self, texto: str) -> list[dict]:
        """Text «name: quantity» (one line per item) → rows matched against the catalog."""
        salida = []
        for n, linea in enumerate((texto or "").splitlines(), 1):
            linea = linea.strip().strip("-•*").strip()
            if not linea:
                continue
            m = self._RE_NOMBRE_CANT.match(linea) or self._RE_CANT_NOMBRE.match(linea)
            if m:
                nombre, cantidad = m.group("nombre").strip(), _entero_texto(m.group("cant"))
            else:
                nombre, cantidad = linea, None
            candidatos = self.buscar(nombre, limite=3)
            mejor = candidatos[0] if candidatos else None
            aceptado = bool(mejor and mejor["puntuacion"] >= 70)
            salida.append({
                "linea": n, "texto": linea, "nombre_leido": nombre, "cantidad": cantidad,
                "objeto_id": mejor["id"] if aceptado else None,
                "nombre": mejor["nombre"] if aceptado else None,
                "puntuacion": mejor["puntuacion"] if mejor else 0,
                "dudosa": not (mejor and mejor["puntuacion"] >= 85) or cantidad is None,
                "candidatos": candidatos,
            })
        return salida

    # --- settings and NPC prices --------------------------------------------------
    def ajustes(self) -> dict:
        return {**AJUSTES_POR_DEFECTO, **{k: v for k, v in (self.repo.ajustes() or {}).items() if v is not None}}

    def ajustes_efectivos(self, servidor: dict | None) -> dict:
        aj = self.ajustes()
        for k in ("comision_registro", "impuesto_venta"):
            if servidor and servidor.get(k) is not None:
                aj[k] = float(servidor[k])
        return aj

    def guardar_ajustes(self, datos: dict) -> dict:
        nuevos = {}
        for k, v in (datos or {}).items():
            tipo = _AJUSTES_EDITABLES.get(k)
            if tipo is None:
                continue
            if tipo is str:
                v = str(v)
                if k in _OPCIONES and v not in _OPCIONES[k]:
                    raise ValueError(f"Valor no válido para {k}: {v!r}.")
            else:
                v = _num(v, tipo, k, 0, permitir_none=False)
            if k in ("comision_registro", "impuesto_venta"):
                if v > 1:
                    v = v / 100.0
                if v >= 0.9:
                    raise ValueError("La comisión/impuesto parece demasiado alta.")
            nuevos[k] = v
        if nuevos:
            self.repo.guardar_ajustes(nuevos)
        self._cache_objetivo.clear()
        return self.ajustes()

    def precios_npc(self) -> list[dict]:
        manuales = self._precios_npc_dict()
        cat = self._cat_o_none()
        filas = {}
        if cat:
            for k, o in cat.objetos.items():
                if o.get("precio_npc") is not None:
                    filas[int(k)] = {"objeto_id": int(k), "nombre": cat.nombre(k), "precio": float(o["precio_npc"]),
                                     "precio_catalogo": float(o["precio_npc"]), "origen": "catálogo"}
        for oid, p in manuales.items():
            fila = filas.setdefault(oid, {"objeto_id": oid, "nombre": cat.nombre(oid) if cat else f"#{oid}",
                                          "precio_catalogo": None})
            fila.update(precio=p, origen="manual")
        return sorted(filas.values(), key=lambda f: normalizar(f["nombre"]))

    def guardar_precio_npc(self, objeto_id, precio) -> dict:
        oid = _num(objeto_id, int, "objeto", permitir_none=False)
        p = _num(precio, float, "precio", 0)
        self.repo.guardar_precio_npc(oid, p)
        return {"objeto_id": oid, "precio": p}

    def _precios_npc_dict(self) -> dict[int, float]:
        return {int(k): float(v) for k, v in (self.repo.precios_npc() or {}).items()}

    # --- market prices ------------------------------------------------------------
    def precios(self, servidor_id) -> dict:
        if not servidor_id:
            return {}
        return {int(k): v for k, v in (self.repo.ultimas_lecturas(servidor_id) or {}).items()}

    def lectura_dict(self, lec, cat=None) -> dict | None:
        if lec is None:
            return None
        d = asdict(lec) if is_dataclass(lec) else dict(lec)
        d["ofertas"] = [[float(p), int(c)] for p, c in (d.get("ofertas") or [])]
        d["antiguedad_horas"] = horas_desde(d.get("fecha"))
        d["semaforo"] = semaforo(d["antiguedad_horas"])
        d["fecha"] = iso(d.get("fecha"))
        if cat is not None:
            d["nombre"] = cat.nombre(d["objeto_id"])
        return d

    def ultimas_mercado(self, servidor_id, texto: str | None = None, limite: int = 200) -> list[dict]:
        cat = self.cat
        filas = [self.lectura_dict(l, cat) for l in self.precios(servidor_id).values()]
        if texto:
            q = normalizar(texto)
            filas = [f for f in filas if q in normalizar(f["nombre"])]
        filas.sort(key=lambda f: f.get("fecha") or "", reverse=True)
        return limpio(filas[:limite])

    def historico(self, servidor_id, objeto_id, dias: int = 30) -> list:
        desde = ahora() - timedelta(days=max(1, int(dias)))
        return list(self.repo.historico(servidor_id, int(objeto_id), desde) or [])

    def mercado_objeto(self, servidor_id, objeto_id, dias: int = 30) -> dict:
        if not servidor_id:
            raise ValueError("Elige un perfil con servidor para ver su mercado.")
        cat = self.cat
        oid = int(objeto_id)
        hist = self.historico(servidor_id, oid, dias)
        actual = self.precios(servidor_id).get(oid)
        servidor = next((s for s in self.repo.listar_servidores() if s["id"] == servidor_id), None)
        recetas = cat.recetas_que_producen(oid, con_combo=True)
        return limpio({
            "objeto": {"id": oid, "nombre": cat.nombre(oid), **(cat.objeto(oid) or {})},
            "actual": self.lectura_dict(actual),
            "historico": [self.lectura_dict(l) for l in hist],
            "dias": dias,
            "fabricable": bool(recetas),
            "recetas": [{"id": r["id"], "profesion": r["profesion"], "nivel": r.get("nivel"),
                         "nombre": cat.nombre(r["producto"])} for r in recetas],
            "volumen_dia": precio_objetivo.volumen_estimado(hist),
            "objetivo_venta": precio_objetivo.precio_objetivo_venta(hist, actual, self.ajustes_efectivos(servidor)),
            "objetivo_compra": precio_objetivo.precio_objetivo_compra(hist, actual),
        })

    def guardar_manual(self, datos: dict) -> dict:
        datos = dict(datos or {})
        servidor_id = datos.get("servidor_id")
        if not servidor_id:
            raise ValueError("Falta el servidor: elige un perfil con servidor.")
        oid = _num(datos.get("objeto_id"), int, "objeto", permitir_none=False)
        cat = self.cat  # checks that the catalog loads
        ofertas = self._ofertas_de(datos.get("ofertas"), datos.get("ofertas_texto"))
        precio = _num(datos.get("precio_min"), float, "precio", 0)
        cantidad = _num(datos.get("cantidad_total"), int, "cantidad", 0)
        anuncios = _num(datos.get("num_anuncios"), int, "nº de anuncios", 0)
        if ofertas:
            precio = precio if precio is not None else ofertas[0][0]
            cantidad = cantidad if cantidad is not None else sum(c for _, c in ofertas)
            anuncios = anuncios if anuncios is not None else len(ofertas)
        if precio is None:
            raise ValueError("Indica al menos el precio mínimo.")
        lectura = Lectura(servidor_id=servidor_id, objeto_id=oid, fecha=utc(datos.get("fecha")) or ahora(),
                          precio_min=precio, cantidad_total=cantidad, num_anuncios=anuncios, ofertas=ofertas,
                          fuente="manual")
        res = self.repo.guardar_lecturas([lectura], None)
        self._invalidar(servidor_id)
        return limpio({"ids": res.ids, "en_cola": res.en_cola, "lectura": self.lectura_dict(lectura, cat)})

    @staticmethod
    def _ofertas_de(ofertas, texto) -> list[tuple[float, int]]:
        salida = []
        for o in ofertas or []:
            p, c = (o.get("precio"), o.get("cantidad")) if isinstance(o, dict) else (o[0], o[1])
            salida.append((_num(p, float, "precio de oferta", 0, False), _num(c, int, "cantidad de oferta", 1, False)))
        for linea in (texto or "").splitlines():
            nums = re.findall(r"\d[\d.,']*", linea)
            if not nums:
                continue
            if len(nums) < 2:
                raise ValueError(f"Cada línea del libro de ofertas necesita «precio cantidad»: {linea!r}")
            salida.append((float(_entero_texto(nums[0]) or 0), int(_entero_texto(nums[1]) or 0)))
        return sorted((p, c) for p, c in salida if p > 0 and c > 0)

    def _invalidar(self, servidor_id):
        for k in [k for k in self._cache_objetivo if k[0] == servidor_id]:
            self._cache_objetivo.pop(k, None)

    def _objetivo_venta(self, servidor_id, oid, actual, ajustes) -> dict:
        clave = (servidor_id, int(oid))
        guardado = self._cache_objetivo.get(clave)
        if guardado and time.monotonic() - guardado[0] < self.TTL_OBJETIVO_S:
            return guardado[1]
        res = precio_objetivo.precio_objetivo_venta(self.historico(servidor_id, oid, 30), actual, ajustes)
        self._cache_objetivo[clave] = (time.monotonic(), res)
        return res

    # --- analysis ---------------------------------------------------------------
    def _nivel(self, ctx, profesion) -> int:
        return int(ctx["niveles"].get(profesion, ctx["ajustes"].get("nivel_por_defecto", 1)))

    def _analizar(self, receta, ctx, precios, npc, intentos=1, inventario=None):
        """Engine analysis; `inventario` defaults to the profile's (pass {} to ignore it)."""
        inv = ctx["inventario"] if inventario is None else inventario
        return calculo.analizar_receta(receta, self.cat, precios, ctx["ajustes"], self._nivel(ctx, receta["profesion"]),
                                       inv or None, intentos, niveles=ctx["niveles"], faccion=ctx["faccion"],
                                       precios_npc=npc)

    def oportunidades(self, perfil_id=None, profesion=None, inversion_max=None, margen_min=None,
                      incluir_intermedios=True, usar_inventario=True, limite=50) -> dict:
        cat = self.cat
        ctx = self.contexto(perfil_id)
        base = {"perfil": ctx["perfil"], "servidor": ctx["servidor"], "filas": [], "avisos": []}
        if not ctx["perfil"]:
            base["avisos"].append("Crea tu perfil (personaje y servidor) en la pestaña Personaje.")
            return limpio(base)
        if not ctx["servidor_id"]:
            base["avisos"].append("Tu perfil no tiene servidor: asígnale uno en Personaje (cada servidor tiene su mercado).")
            return limpio(base)
        precios = self.precios(ctx["servidor_id"])
        npc = self._precios_npc_dict()
        if not precios:
            base["avisos"].append("Aún no hay precios de mercado para este servidor: lee el mercado en Captura, "
                                  "introduce precios a mano en Mercado o importa el Excel.")
        filtros = {"profesion": profesion or None, "inversion_max": inversion_max, "margen_min": margen_min,
                   "incluir_intermedios": bool(incluir_intermedios), "limite": limite}
        inventario = ctx["inventario"] if usar_inventario else None
        res = calculo.mejores_oportunidades(cat, precios, ctx["ajustes"], ctx["niveles"], ctx["faccion"],
                                            inventario, filtros, precios_npc=npc)
        base["filas"] = [self._fila_panel(a, ctx, precios, npc, inventario, con_escenario=i < self.TOP_ESCENARIOS)
                         for i, a in enumerate(res[: int(limite or 50)])]
        base["n_precios"] = len(precios)
        return limpio(base)

    _CAMPOS_PANEL = ("receta_id", "producto", "nombre", "profesion", "nivel_receta", "beneficio_intento", "margen",
                     "inversion", "beneficio_total", "coste_intento", "precio_venta", "precio_equilibrio", "p_exito",
                     "p_combo", "items_esperados", "es_intermedio", "antiguedad_precios_horas", "mensaje_inventario")

    def _fila_panel(self, a: dict, ctx, precios, npc, inventario, con_escenario=True) -> dict:
        n = int(a["intentos_recomendados"])
        fila = {k: a.get(k) for k in self._CAMPOS_PANEL} | {
            "profesion_nombre": self.cat.nombre_profesion(a["profesion"]),
            "intentos_recomendados": n,
            "semaforo": semaforo(a["antiguedad_precios_horas"]),
            "avisos": a["avisos"],
            "escenario_objetivo": None,
        }
        if con_escenario:
            try:
                fila["escenario_objetivo"] = self._escenario_objetivo(
                    self.cat.receta(a["receta_id"]), a, ctx, precios, npc, n, inventario or {})
            except Exception as e:  # noqa: BLE001
                log.warning("Target scenario for %s failed: %s", a["receta_id"], e)
        return fila

    def _escenario_objetivo(self, receta, a, ctx, precios, npc, n, inventario) -> dict:
        """Same analysis if the product were listed at its target price instead of right now."""
        prod = int(a["producto"])
        actual = precios.get(prod)
        po = self._objetivo_venta(ctx["servidor_id"], prod, actual, ctx["ajustes"])
        if po.get("precio_recomendado") is None:
            return {"estado": po.get("estado", "sin_datos"), "aviso": po.get("aviso")}
        rebaja = float(ctx["ajustes"].get("rebaja_listado", 1))
        precios_objetivo = {**precios, prod: {
            "precio_min": float(po["precio_recomendado"]) + rebaja, "ofertas": [],
            "fecha": campo(actual, "fecha") or ahora(), "cantidad_total": campo(actual, "cantidad_total"),
            "num_anuncios": campo(actual, "num_anuncios")}}
        b = self._analizar(receta, ctx, precios_objetivo, npc, n, inventario)
        return {
            "estado": po.get("estado"), "aviso": po.get("aviso"),
            "precio_ya": a.get("precio_venta"), "precio_objetivo": po.get("precio_recomendado"),
            "beneficio_intento": b.get("beneficio_intento"), "beneficio_total": b.get("beneficio_total"),
            "margen": b.get("margen"), "dias_para_vender": po.get("dias_para_vender"),
            "rango_p25": po.get("rango_p25"), "mediana": po.get("mediana"), "rango_p75": po.get("rango_p75"),
        }

    # --- recipes ------------------------------------------------------------------
    def recetas(self, perfil_id=None, texto=None, profesion=None, solo_desbloqueadas=False, limite=300) -> dict:
        cat = self.cat
        try:
            ctx = self.contexto(perfil_id)
        except NoDisponible:
            ctx = {"faccion": None, "niveles": {}}
        q = normalizar(texto) if texto else None
        filas = []
        for r in cat.recetas_de(ctx["faccion"]):
            if profesion and r["profesion"] != profesion:
                continue
            nombre = cat.nombre(r["producto"])
            if q and q not in normalizar(nombre) and q not in normalizar((cat.objeto(r["producto"]) or {}).get("nombre_en")):
                continue
            desbloqueada = int(ctx["niveles"].get(r["profesion"], 1)) >= int(r.get("nivel") or 1)
            if solo_desbloqueadas and not desbloqueada:
                continue
            filas.append({"id": r["id"], "nombre": nombre, "producto": r["producto"], "profesion": r["profesion"],
                          "profesion_nombre": cat.nombre_profesion(r["profesion"]), "nivel": r.get("nivel"),
                          "faccion": r.get("faccion"), "cantidad": r.get("cantidad"), "desbloqueada": desbloqueada,
                          "combo_pct": r.get("combo_pct"), "n_ingredientes": len(r.get("ingredientes") or [])})
        filas.sort(key=lambda f: (f["profesion"], f["nivel"] or 0, normalizar(f["nombre"])))
        return limpio({"total": len(filas), "filas": filas[:limite], "faccion": ctx["faccion"]})

    def _receta(self, receta_id) -> dict:
        receta = self.cat.receta(receta_id)
        if receta is None:
            raise LookupError("Esa receta no existe en el catálogo.")
        return receta

    def detalle_receta(self, receta_id, perfil_id=None, intentos=1) -> dict:
        cat = self.cat
        receta = self._receta(receta_id)
        intentos = max(1, int(intentos))
        ctx = self.contexto(perfil_id)
        precios = self.precios(ctx["servidor_id"])
        npc = self._precios_npc_dict()
        a = self._analizar(receta, ctx, precios, npc, intentos)
        salida = {
            "receta": {**receta, "nombre": cat.nombre(receta["producto"]),
                       "profesion_nombre": cat.nombre_profesion(receta["profesion"]),
                       "ingredientes_nombres": [{"id": i, "nombre": cat.nombre(i), "cantidad": q}
                                                for i, q in receta.get("ingredientes") or []],
                       "producto_combo_nombre": cat.nombre(receta["producto_combo"]) if receta.get("producto_combo") else None},
            "perfil": ctx["perfil"],
            "analisis": a,
            "semaforo": semaforo(a.get("antiguedad_precios_horas")),
            "arbol": self._arbol(receta, ctx, precios, npc, set(), 0),
        }
        if ctx["servidor_id"]:
            salida["escenario_objetivo"] = self._escenario_objetivo(receta, a, ctx, precios, npc, intentos,
                                                                    ctx["inventario"])
        return limpio(salida)

    def _coste_fabricar(self, oid, ctx, precios, npc):
        """Best unlocked recipe for crafting `oid`: (unit cost, recipe)."""
        mejor = (None, None)
        for r in self.cat.recetas_que_producen(oid, con_combo=True):
            if ctx["faccion"] and r.get("faccion") not in (ctx["faccion"], "ambas", None):
                continue
            if self._nivel(ctx, r["profesion"]) < int(r.get("nivel") or 1):
                continue
            a = self._analizar(r, ctx, precios, npc, 1, inventario={})
            salidas = a.get("salidas_esperadas") or {}
            unidades = salidas.get(int(oid)) or (a.get("items_esperados") if int(r["producto"]) == int(oid) else 0)
            if a.get("coste_intento") is None or not unidades:
                continue
            unit = a["coste_intento"] / unidades
            if mejor[0] is None or unit < mejor[0]:
                mejor = (unit, r)
        return mejor

    def _arbol(self, receta, ctx, precios, npc, visitados: set, profundidad: int) -> list[dict]:
        cat = self.cat
        nodos = []
        visitados = visitados | {int(receta["producto"])}
        for ing, q in receta.get("ingredientes") or []:
            ing = int(ing)
            mercado = campo(precios.get(ing), "precio_min")
            npc_p = npc.get(ing, (cat.objeto(ing) or {}).get("precio_npc"))
            nodo = {"id": ing, "nombre": cat.nombre(ing), "cantidad": q, "precio_mercado": mercado,
                    "precio_npc": npc_p, "coste_fabricar": None, "receta_id": None, "hijos": [],
                    "en_inventario": ctx["inventario"].get(ing, 0),
                    "antiguedad_horas": horas_desde(campo(precios.get(ing), "fecha"))}
            if ing not in visitados and profundidad < 5 and cat.recetas_que_producen(ing, con_combo=True):
                coste, sub = self._coste_fabricar(ing, ctx, precios, npc)
                if sub is not None:
                    nodo.update(coste_fabricar=coste, receta_id=sub["id"],
                                hijos=self._arbol(sub, ctx, precios, npc, visitados, profundidad + 1))
                else:
                    nodo["nota"] = "Se puede fabricar, pero no tienes la receta desbloqueada o faltan precios."
            opciones = [(v, k) for k, v in (("mercado", mercado), ("npc", npc_p), ("fabricar", nodo["coste_fabricar"]))
                        if v is not None]
            nodo["coste_mejor"], nodo["mejor"] = min(opciones) if opciones else (None, None)
            nodos.append(nodo)
        return nodos

    def lista_compra(self, receta_id, perfil_id=None, intentos=None) -> dict:
        cat = self.cat
        receta = self._receta(receta_id)
        ctx = self.contexto(perfil_id)
        precios = self.precios(ctx["servidor_id"])
        npc = self._precios_npc_dict()
        if not intentos:
            maxi = self._analizar(receta, ctx, precios, npc, 1).get("max_intentos_mercado")
            tope = int(ctx["ajustes"].get("tope_intentos", 100))
            intentos = max(1, min(tope, maxi if maxi is not None else tope))
        intentos = int(intentos)
        comprar: dict[tuple, dict] = {}
        fabricar: list[dict] = []
        inventario_usado: dict[int, int] = {}
        self._expandir_compra(receta, intentos, ctx, precios, npc, comprar, fabricar, inventario_usado, set(), 0)
        for item in comprar.values():
            item["cantidad"] = math.ceil(item["cantidad"] - 1e-9)
            item["coste"] = item["coste_unit"] * item["cantidad"] if item["coste_unit"] is not None else None
            if ctx["servidor_id"] and item["origen"] == "mercado":
                try:
                    hist = self.historico(ctx["servidor_id"], item["id"], 30)
                    item["comprar_por_debajo_de"] = precio_objetivo.precio_objetivo_compra(
                        hist, precios.get(item["id"])).get("comprar_por_debajo_de")
                except Exception:  # noqa: BLE001
                    item["comprar_por_debajo_de"] = None
        lista = sorted(comprar.values(), key=lambda i: (i["origen"] != "mercado", -(i["coste"] or 0)))
        lineas = [f"Lista de la compra — {cat.nombre(receta['producto'])} × {intentos} intento(s)"]
        for i in lista:
            donde = "tienda NPC" if i["origen"] == "npc" else "mercado"
            precio = f" a ~{i['coste_unit']:,.0f}".replace(",", ".") if i["coste_unit"] is not None else ""
            lineas.append(f"- {i['nombre']}: {i['cantidad']} ({donde}{precio})")
        lineas += [f"* Fabricar antes: {f['nombre']} × {f['intentos']} intento(s)" for f in fabricar]
        lineas += [f"· Del inventario: {cat.nombre(oid)} × {c}" for oid, c in inventario_usado.items()]
        return limpio({"receta_id": receta["id"], "nombre": cat.nombre(receta["producto"]), "intentos": intentos,
                       "comprar": lista, "fabricar": fabricar,
                       "de_inventario": [{"id": k, "nombre": cat.nombre(k), "cantidad": v} for k, v in inventario_usado.items()],
                       "coste_total": sum(i["coste"] or 0 for i in lista), "texto": "\n".join(lineas)})

    def _expandir_compra(self, receta, intentos, ctx, precios, npc, comprar, fabricar, inv_usado, visitados, prof):
        cat = self.cat
        a = self._analizar(receta, ctx, precios, npc, max(1, math.ceil(intentos - 1e-9)))
        visitados = visitados | {int(receta["producto"])}
        for d in a.get("desglose_ingredientes") or []:
            oid = int(d["id"])
            for origen, unidades in (d.get("origenes") or {}).items():
                if not unidades or (isinstance(unidades, float) and not math.isfinite(unidades)):
                    continue
                if origen == "inventario":
                    inv_usado[oid] = inv_usado.get(oid, 0) + int(unidades)
                elif origen == "fabricar" and d.get("receta_id") and oid not in visitados and prof < 5:
                    sub = cat.receta(d["receta_id"])
                    if sub is None:
                        continue
                    a_sub = self._analizar(sub, ctx, precios, npc, 1, inventario={})
                    por_intento = (a_sub.get("salidas_esperadas") or {}).get(oid) or a_sub.get("items_esperados") or 1
                    n_sub = math.ceil(unidades / por_intento - 1e-9)
                    fabricar.append({"receta_id": sub["id"], "nombre": cat.nombre(sub["producto"]), "unidades": unidades,
                                     "intentos": n_sub, "profesion": sub["profesion"]})
                    self._expandir_compra(sub, n_sub, ctx, precios, npc, comprar, fabricar, inv_usado, visitados, prof + 1)
                else:
                    precio = (campo(precios.get(oid), "precio_min") if origen == "mercado"
                              else npc.get(oid, (cat.objeto(oid) or {}).get("precio_npc")))
                    item = comprar.setdefault((oid, origen), {"id": oid, "nombre": cat.nombre(oid), "origen": origen,
                                                              "cantidad": 0.0, "coste_unit": d.get("coste_unit"),
                                                              "precio_ultimo": precio})
                    item["cantidad"] += unidades

    # --- own operations -------------------------------------------------------------
    def registrar_operacion(self, datos: dict) -> dict:
        tipo = datos.get("tipo")
        if tipo not in ("venta", "compra"):
            raise ValueError("El tipo debe ser «venta» o «compra».")
        return limpio(self.repo.registrar_operacion(
            datos.get("perfil_id"), tipo, _num(datos.get("objeto_id"), int, "objeto", permitir_none=False),
            _num(datos.get("cantidad"), int, "cantidad", 1, False), _num(datos.get("precio"), float, "precio", 0, False),
            utc(datos.get("fecha")) or ahora()))

    # ===========================================================================
    # capture
    # ===========================================================================
    def _cargar_sesiones(self):
        try:
            datos = json.loads(Path(self.ruta_sesiones).read_text(encoding="utf-8"))
            for s in datos if isinstance(datos, list) else []:
                if s.get("estado") == "procesando":
                    s["estado"], s["error"] = "error", "La app se cerró mientras se procesaba."
                self.sesiones[s["id"]] = s
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
            pass

    def _persistir_sesiones(self):
        with self._lock:
            # keep those awaiting review and the last 20 finished ones
            ordenadas = sorted(self.sesiones.values(), key=lambda s: s.get("creada") or "", reverse=True)
            abiertas = [s for s in ordenadas if s["estado"] in ("revision", "procesando")]
            cerradas = [s for s in ordenadas if s["estado"] not in ("revision", "procesando")]
            try:
                ruta = Path(self.ruta_sesiones)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                tmp = ruta.with_suffix(".tmp")
                tmp.write_text(json.dumps(limpio(abiertas + cerradas[:20]), ensure_ascii=False, indent=1),
                               encoding="utf-8")
                os.replace(tmp, ruta)
            except OSError as e:
                log.warning("Could not save the capture sessions: %s", e)

    @staticmethod
    def resumen_sesion(s: dict) -> dict:
        filas = s.get("filas") or []
        return {k: s.get(k) for k in ("id", "origen", "servidor_id", "estado", "progreso", "creada", "error",
                                      "mensaje", "nombre_archivo", "en_cola")} | {
            "n_filas": len(filas),
            "n_dudosas": sum(1 for f in filas if f["estado"] == "pendiente"),
            "n_ok": sum(1 for f in filas if f["estado"] in ("ok", "corregida")),
            "n_guardadas": len(s.get("ids_guardados") or []),
        }

    def listar_sesiones(self) -> list[dict]:
        return sorted((self.resumen_sesion(s) for s in self.sesiones.values()),
                      key=lambda s: s.get("creada") or "", reverse=True)

    def _sesion(self, sesion_id) -> dict:
        s = self.sesiones.get(sesion_id)
        if s is None:
            raise LookupError("Esa sesión de lectura no existe.")
        return s

    def sesion(self, sesion_id) -> dict:
        s = self._sesion(sesion_id)
        return limpio({**self.resumen_sesion(s), "filas": s["filas"], "ids_guardados": s.get("ids_guardados", [])})

    def _validar_servidor(self, servidor_id, mensaje: str) -> None:
        if not servidor_id or servidor_id not in {s["id"] for s in self.repo.listar_servidores()}:
            raise ValueError(mensaje)

    def _nueva_sesion(self, origen, servidor_id, archivo=None, nombre_archivo=None) -> dict:
        if not servidor_id:
            raise ValueError("Elige un perfil con servidor: las lecturas se guardan en el mercado de ese servidor.")
        self._validar_servidor(servidor_id, "Ese servidor no existe.")
        s = {"id": str(uuid.uuid4()), "origen": origen, "fuente": FUENTE_POR_ORIGEN[origen], "servidor_id": servidor_id,
             "estado": "procesando", "progreso": 0.0, "creada": iso(ahora()), "archivo": str(archivo) if archivo else None,
             "nombre_archivo": nombre_archivo, "error": None, "mensaje": None, "filas": [], "ids_guardados": [],
             "en_cola": False}
        with self._lock:
            self.sesiones[s["id"]] = s
        return s

    def estado_captura(self) -> dict:
        g = self.grabacion
        estado_g = None
        if g is not None:
            try:
                estado_g = g.estado()
            except Exception as e:  # noqa: BLE001
                estado_g = {"activa": True, "error": str(e)}
        return limpio({"grabando": g is not None, "grabacion": estado_g, "servidor_id": self.grabacion_servidor,
                       "sesiones": self.listar_sesiones()[:30]})

    def iniciar_grabacion(self, servidor_id, fps: float = 3) -> dict:
        if self.grabacion is not None:
            raise ValueError("Ya hay una lectura en marcha: termínala primero.")
        self._validar_servidor(servidor_id, "Elige un perfil con servidor antes de empezar la lectura.")
        g = grabacion.SesionGrabacion(fps=max(1.0, min(4.0, float(fps or 3))), cat=self.cat)
        g.iniciar()
        self.grabacion, self.grabacion_servidor = g, servidor_id
        return self.estado_captura()

    def detener_grabacion(self) -> dict:
        g, servidor_id = self.grabacion, self.grabacion_servidor
        if g is None:
            raise ValueError("No hay ninguna lectura en marcha.")
        self.grabacion = self.grabacion_servidor = None
        s = self._nueva_sesion("grabacion", servidor_id)
        try:
            filas = g.detener()
        except Exception as e:  # noqa: BLE001
            s.update(estado="error", error=str(e))
            self._persistir_sesiones()
            return self.resumen_sesion(s)
        self._registrar_filas(s, filas)
        return self.resumen_sesion(s)

    def procesar_archivo(self, ruta: Path, nombre: str, servidor_id, en_segundo_plano=None) -> dict:
        if en_segundo_plano is None:
            en_segundo_plano = self.segundo_plano
        ext = Path(nombre).suffix.lower()
        if ext in EXT_VIDEO:
            origen = "video"
        elif ext in EXT_IMAGEN:
            origen = "imagen"
        else:
            raise ValueError("Formato no admitido: sube un vídeo (mp4, mkv, mov…) o una imagen (png, jpg…).")
        s = self._nueva_sesion(origen, servidor_id, archivo=ruta, nombre_archivo=nombre)

        def progreso(p):
            s["progreso"] = round(float(p), 3)

        def trabajo():
            try:
                if origen == "video":
                    filas = video.procesar_video(str(ruta), self.cat, progreso=progreso)
                else:
                    from PIL import Image

                    with Image.open(ruta) as img:
                        img = img.convert("RGB")
                        filas = grabacion.procesar_imagen(img, self.cat)
                        for f in filas:
                            if f.get("dudosa") and f.get("caja"):
                                try:
                                    f["recorte"] = grabacion.guardar_recorte(img, f)
                                except Exception:  # noqa: BLE001
                                    pass
                self._registrar_filas(s, filas)
            except Exception as e:  # noqa: BLE001
                log.exception("Error processing %s", nombre)
                s.update(estado="error", error=f"{type(e).__name__}: {e}")
                self._persistir_sesiones()

        if en_segundo_plano:
            threading.Thread(target=trabajo, name=f"captura-{s['id'][:8]}", daemon=True).start()
        else:
            trabajo()
        return self.resumen_sesion(s)

    def _registrar_filas(self, s: dict, filas: list) -> None:
        cat = self.cat
        normalizadas = []
        for i, f in enumerate(filas or []):
            f = asdict(f) if is_dataclass(f) else dict(f)
            oid = f.get("objeto_id")
            dudosa = bool(f.get("dudosa")) or oid is None or not f.get("precio") or not f.get("cantidad")
            normalizadas.append({
                "idx": i, "objeto_id": oid, "nombre": cat.nombre(oid) if oid is not None else None,
                "nombre_leido": f.get("nombre_leido") or "", "precio": f.get("precio"), "cantidad": f.get("cantidad"),
                "confianza": f.get("confianza"), "motivos": f.get("motivos") or [],
                "recorte": f.get("recorte"), "estado": "pendiente" if dudosa else "ok",
            })
        s["filas"] = normalizadas
        s["progreso"] = 1.0
        if not normalizadas:
            s.update(estado="terminada", mensaje="No se reconoció ninguna fila del mercado. Revisa la calibración.")
            self._persistir_sesiones()
            self._limpiar_archivo(s, verificado=True)
            return
        if any(f["estado"] == "pendiente" for f in normalizadas):
            s["estado"] = "revision"
            self._persistir_sesiones()
        else:
            self.guardar_sesion(s["id"])

    def _fila(self, s: dict, idx) -> dict:
        try:
            return s["filas"][int(idx)]
        except (IndexError, ValueError):
            raise LookupError("Esa fila no existe.") from None

    def corregir_fila(self, sesion_id, idx: int, datos: dict) -> dict:
        s = self._sesion(sesion_id)
        if s["estado"] != "revision":
            raise ValueError("Esta sesión ya no está en revisión.")
        fila = self._fila(s, idx)
        accion = datos.get("accion", "confirmar")
        if accion == "descartar":
            fila["estado"] = "descartada"
        elif accion == "confirmar":
            oid = _num(datos.get("objeto_id", fila["objeto_id"]), int, "objeto", permitir_none=False)
            precio = _num(datos.get("precio", fila["precio"]), float, "precio", 1, False)
            cantidad = _num(datos.get("cantidad", fila["cantidad"]), int, "cantidad", 1, False)
            cambio = (oid, precio, cantidad) != (fila["objeto_id"], fila["precio"], fila["cantidad"])
            fila.update(objeto_id=oid, nombre=self.cat.nombre(oid), precio=precio, cantidad=cantidad,
                        estado="corregida" if cambio else "ok")
        else:
            raise ValueError("Acción no válida (confirmar | descartar).")
        self._persistir_sesiones()
        return self.sesion(sesion_id)

    def guardar_sesion(self, sesion_id, descartar_pendientes: bool = True) -> dict:
        """Saves the session's correct rows (pending ones are discarded)."""
        s = self._sesion(sesion_id)
        if s["estado"] not in ("revision", "procesando"):
            raise ValueError("Esta sesión ya está guardada o falló.")
        if not descartar_pendientes and any(f["estado"] == "pendiente" for f in s["filas"]):
            raise ValueError("Quedan filas por revisar.")
        buenas = [f for f in s["filas"] if f["estado"] in ("ok", "corregida")]
        for f in s["filas"]:
            if f["estado"] == "pendiente":
                f["estado"] = "descartada"
        lecturas = parser.a_lecturas(
            [{"objeto_id": f["objeto_id"], "precio": f["precio"], "cantidad": f["cantidad"], "nombre": f.get("nombre"),
              "dudosa": False, "confianza": 1.0} for f in buenas],
            s["servidor_id"], s["fuente"], incluir_dudosas=True, clase_lectura=Lectura)
        ids, en_cola = [], False
        if lecturas:
            res = self.repo.guardar_lecturas(lecturas, s["id"])
            ids, en_cola = list(res.ids), bool(res.en_cola)
        s.update(ids_guardados=ids, en_cola=en_cola, estado="terminada",
                 mensaje=f"Guardados {len(lecturas)} objeto(s) ({len(buenas)} anuncios)."
                         + (" Sin conexión: quedan en la cola y se subirán al reconectar." if en_cola else ""))
        self._invalidar(s["servidor_id"])
        self._persistir_sesiones()
        self._limpiar_archivo(s)
        return self.resumen_sesion(s)

    @staticmethod
    def _borrar_tmp(ruta) -> None:
        p = Path(ruta)
        try:
            if p.resolve().is_relative_to(DIR_TMP.resolve()) and p.exists():
                p.unlink()
        except OSError as e:
            log.warning("Could not delete %s: %s", p, e)

    def _limpiar_archivo(self, s: dict, verificado: bool = False) -> None:
        """After reviewing/saving a session: deletes the reviewed crops and the source
        video/image, the latter only once its readings are verified in the database."""
        recortes = [f["recorte"] for f in s.get("filas") or [] if f.get("recorte")]
        # crops of doubtful rows: already reviewed (the session is closed)
        for ruta in recortes:
            try:
                marcado = bool(temporales.marcar_revisado(ruta))
            except Exception as e:  # noqa: BLE001
                log.warning("marcar_revisado failed: %s", e)
                marcado = False
            if not marcado:
                self._borrar_tmp(ruta)
        if recortes:
            try:
                temporales.limpiar_revisados()
            except Exception as e:  # noqa: BLE001
                log.warning("limpiar_revisados failed: %s", e)

        archivo, ids = s.get("archivo"), s.get("ids_guardados") or []
        if not archivo:
            return
        if verificado or not ids:
            # no data came out of this file (nothing to verify): it can be deleted now
            self._borrar_tmp(archivo)
            return
        try:
            temporales.registrar_temporal(archivo, ids)
            temporales.limpiar_verificados(self.repo)
            return
        except Exception as e:  # noqa: BLE001
            log.warning("temporales failed (%s); verifying and deleting directly", e)
        try:
            ok = self.repo.verificar_lecturas(ids) is True
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            self._borrar_tmp(archivo)

    def ruta_recorte(self, sesion_id, idx) -> Path:
        ruta = self._fila(self._sesion(sesion_id), idx).get("recorte")
        if not ruta or not Path(ruta).exists() or not Path(ruta).resolve().is_relative_to(DIR_TMP.resolve()):
            raise LookupError("No hay imagen de esa fila.")
        return Path(ruta)

    # --- calibration ------------------------------------------------------------
    def calibracion(self) -> dict:
        salida = {"datos": calibracion.cargar(), "resolucion": None, "actual": None}
        try:
            ancho, alto = calibracion.resolucion_pantalla()
            salida["resolucion"] = [ancho, alto]
            salida["actual"] = calibracion.configuracion_para(ancho, alto)
        except Exception as e:  # noqa: BLE001
            salida["aviso"] = f"No se pudo leer la resolución de la pantalla: {e}"
        return limpio(salida)

    def guardar_calibracion(self, datos: dict) -> dict:
        ancho = _num(datos.get("ancho"), int, "ancho", 1, False)
        alto = _num(datos.get("alto"), int, "alto", 1, False)
        region = datos.get("region")
        if not region or len(region) != 4:
            raise ValueError("Marca la zona de la lista del mercado (x, y, ancho, alto).")
        entrada = calibracion.guardar_region(ancho, alto, region, columnas=datos.get("columnas") or None,
                                             escala=datos.get("escala"))
        return limpio({"guardada": entrada, **self.calibracion()})

    def borrar_calibracion(self, ancho, alto) -> dict:
        calibracion.borrar_region(int(ancho), int(alto))
        return self.calibracion()

    def captura_pantalla(self, espera: float = 0, max_ancho: int = 1600) -> tuple[bytes, int, int]:
        """Passive capture (mss) of the calibrated monitor to mark the region. Returns (jpeg, width, height)."""
        import mss
        from PIL import Image

        if espera:
            time.sleep(max(0.0, min(10.0, float(espera))))
        try:
            indice = calibracion.monitor()
        except Exception:  # noqa: BLE001
            indice = 1
        with mss.mss() as sct:
            mon = sct.monitors[indice if 0 < indice < len(sct.monitors) else 1]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        ancho, alto = img.size
        if ancho > max_ancho:
            img = img.resize((max_ancho, round(alto * max_ancho / ancho)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        return buf.getvalue(), ancho, alto
