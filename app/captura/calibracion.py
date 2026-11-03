"""Calibración de la zona de la lista del mercado, por resolución de pantalla.

`data/calibracion.json`:
{
  "version": 1,
  "monitor": 1,                       # índice de mss (1 = monitor principal)
  "resoluciones": {
    "2560x1440": {
      "lista":    [x, y, w, h],       # píxeles absolutos de la imagen/pantalla
      "columnas": {"nombre": [x0, x1], "precio": [x0, x1], "cantidad": [x0, x1]} | null,
      "escala":   null,               # escala del OCR (null = automática 2–3×)
      "actualizado": "2026-11-02T12:00:00Z"
    }
  }
}
Mientras no haya calibración para una resolución, la región por defecto es la
imagen completa. `columnas` es opcional: si se marca, el parser asigna cada
palabra a su columna por su posición horizontal (más fiable que la heurística).
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CALIBRACION = RAIZ / "data" / "calibracion.json"
COLUMNAS_VALIDAS = ("nombre", "precio", "cantidad", "total")

_lock = threading.Lock()


def _vacia() -> dict:
    return {"version": 1, "monitor": 1, "resoluciones": {}}


def clave(ancho: int, alto: int) -> str:
    return f"{int(ancho)}x{int(alto)}"


def cargar(ruta: Path | str | None = None) -> dict:
    ruta = Path(ruta or RUTA_CALIBRACION)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return _vacia()
    base = _vacia()
    base.update(datos if isinstance(datos, dict) else {})
    base.setdefault("resoluciones", {})
    return base


def guardar(datos: dict, ruta: Path | str | None = None) -> None:
    ruta = Path(ruta or RUTA_CALIBRACION)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ruta)


def _validar_region(region, ancho: int, alto: int) -> list[int]:
    x, y, w, h = (int(round(v)) for v in region)
    if w <= 0 or h <= 0:
        raise ValueError("La región debe tener ancho y alto positivos.")
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(ancho, x + w), min(alto, y + h)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("La región queda fuera de la pantalla.")
    return [x0, y0, x1 - x0, y1 - y0]


def _validar_columnas(columnas) -> dict | None:
    if not columnas:
        return None
    salida = {}
    for nombre, rango in columnas.items():
        if nombre not in COLUMNAS_VALIDAS:
            raise ValueError(f"Columna desconocida: {nombre!r} (válidas: {', '.join(COLUMNAS_VALIDAS)})")
        x0, x1 = sorted(int(round(v)) for v in rango)
        salida[nombre] = [x0, x1]
    if "nombre" not in salida and not ({"precio", "cantidad"} <= salida.keys()):
        raise ValueError("Marca al menos la columna de nombre o las de precio y cantidad.")
    return salida


def configuracion_para(ancho: int, alto: int, ruta=None) -> dict:
    """Calibración completa para una resolución (con valores por defecto)."""
    datos = cargar(ruta).get("resoluciones", {}).get(clave(ancho, alto))
    if not datos:
        return {"lista": [0, 0, int(ancho), int(alto)], "columnas": None, "escala": None, "calibrada": False}
    return {
        "lista": list(datos.get("lista") or [0, 0, int(ancho), int(alto)]),
        "columnas": datos.get("columnas"),
        "escala": datos.get("escala"),
        "calibrada": True,
    }


def region_para(ancho: int, alto: int, ruta=None) -> tuple[int, int, int, int]:
    """Región (x, y, w, h) de la lista; pantalla completa si no hay calibración."""
    return tuple(configuracion_para(ancho, alto, ruta)["lista"])


def guardar_region(ancho, alto, region, columnas=None, escala=None, ruta=None) -> dict:
    """Guarda la región que el usuario marca en la interfaz para esa resolución."""
    entrada = {
        "lista": _validar_region(region, ancho, alto),
        "columnas": _validar_columnas(columnas),
        "escala": float(escala) if escala else None,
        "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with _lock:
        datos = cargar(ruta)
        datos["resoluciones"][clave(ancho, alto)] = entrada
        guardar(datos, ruta)
    return entrada


def borrar_region(ancho, alto, ruta=None) -> bool:
    with _lock:
        datos = cargar(ruta)
        existia = datos["resoluciones"].pop(clave(ancho, alto), None) is not None
        if existia:
            guardar(datos, ruta)
    return existia


def monitor(ruta=None) -> int:
    return int(cargar(ruta).get("monitor", 1) or 1)


def resolucion_pantalla(indice_monitor: int | None = None) -> tuple[int, int]:
    """Resolución del monitor (lectura pasiva con mss, sin tocar el juego)."""
    import mss

    with mss.mss() as sct:
        i = indice_monitor if indice_monitor is not None else monitor()
        i = i if 0 <= i < len(sct.monitors) else 1
        m = sct.monitors[i]
        return int(m["width"]), int(m["height"])
