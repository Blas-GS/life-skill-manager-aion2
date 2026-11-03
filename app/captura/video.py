"""Importar un vídeo grabado del mercado (OBS, Xbox Game Bar Win+Alt+R...).

Extrae ~3 fotogramas por segundo con OpenCV, descarta los repetidos o movidos
(mismo `Deduplicador` que el modo grabación), hace OCR de los distintos y
devuelve las filas consolidadas. Los fotogramas solo existen en memoria; el
vídeo NO se borra aquí: lo borra `temporales.limpiar_verificados` cuando las
lecturas ya están guardadas y verificadas en la base de datos.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PIL import Image

from . import parser
from .grabacion import Deduplicador, configuracion_imagen, guardar_recorte, procesar_imagen


def _abrir(ruta: str):
    import cv2

    cap = cv2.VideoCapture(ruta)
    if cap.isOpened():
        return cap
    # OpenCV puede fallar con rutas con tildes en Windows: probar la ruta corta 8.3.
    if os.name == "nt" and not ruta.isascii():
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.kernel32.GetShortPathNameW(ruta, buf, len(buf)):
                cap = cv2.VideoCapture(buf.value)
                if cap.isOpened():
                    return cap
        except Exception:
            pass
    raise ValueError(f"No se pudo abrir el vídeo: {ruta}")


def procesar_video(
    ruta,
    cat,
    region=None,
    columnas=None,
    fps_muestreo: float = 3.0,
    guardar_recortes: bool = True,
    progreso: Callable[[float], None] | None = None,
    idioma: str = "es-ES",
    devolver_estadisticas: bool = False,
    faccion: str | None = None,
):
    """Lee un vídeo y devuelve list[FilaMercado] consolidadas.

    Con `devolver_estadisticas=True` devuelve (filas, {"muestreados", "procesados", ...}).
    """
    import cv2

    ruta = str(Path(ruta))
    cap = _abrir(ruta)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if fps <= 0 or fps > 1000:
            fps = 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        paso = max(1, round(fps / max(0.1, fps_muestreo)))
        indice = parser._indice(cat, faccion)
        dedup = Deduplicador()
        fotogramas: list[list[dict]] = []
        recortadas: set = set()
        n = 0
        while True:
            if not cap.grab():
                break
            if n % paso == 0:
                ok, bgr = cap.retrieve()
                if not ok or bgr is None:
                    break
                img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                conf = configuracion_imagen(img, region, columnas)
                x, y, w, h = conf["lista"]
                if dedup.evaluar(img.crop((x, y, x + w, y + h))):
                    filas = procesar_imagen(img, indice, region=conf["lista"],
                                            columnas=conf["columnas"], escala=conf["escala"],
                                            idioma=idioma)
                    if guardar_recortes:
                        for f in filas:
                            clave = (parser._clave_objeto(f), f.get("precio"), f.get("cantidad"))
                            if f["dudosa"] and clave not in recortadas and len(recortadas) < 200:
                                f["recorte"] = guardar_recorte(img, f)
                                recortadas.add(clave)
                    fotogramas.append(filas)
                if progreso and total:
                    try:
                        progreso(min(1.0, n / total))
                    except Exception:
                        pass
            n += 1
    finally:
        cap.release()
    filas = parser.consolidar(fotogramas)
    if progreso:
        try:
            progreso(1.0)
        except Exception:
            pass
    if devolver_estadisticas:
        return filas, {
            "fotogramas_video": n,
            "muestreados": dedup.vistos,
            "procesados": dedup.procesados,
            "descartados": dedup.descartados,
        }
    return filas
