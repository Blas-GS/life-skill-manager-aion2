"""OCR de Windows (Windows.Media.Ocr vía winrt) sobre imágenes PIL.

Solo trabaja con imágenes ya capturadas: no toca el proceso del juego,
ni su memoria, ni su red, ni envía entrada alguna.

Uso:
    lineas = leer_imagen(img, region=(x, y, w, h))
    # -> [{"texto", "x", "y", "w", "h", "palabras": [{"texto", "x", "y", "w", "h"}]}]

Las coordenadas devueltas están SIEMPRE en el sistema de la imagen original
(sin escalar y con el desplazamiento de la región ya sumado).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

import numpy as np
from PIL import Image, ImageOps

LineaOCR = dict[str, Any]

IDIOMA_RESPALDO = "en-US"

# --------------------------------------------------------------------------
# Bucle asíncrono propio para winrt
# --------------------------------------------------------------------------
# recognize_async devuelve una operación de WinRT que se espera con `await`.
# Usar asyncio.run() en cada llamada falla si quien llama ya tiene un bucle en
# marcha (p.ej. un endpoint async de FastAPI). Por eso todas las llamadas se
# ejecutan en un único hilo con su propio bucle, seguro para varios hilos.

_bucle: asyncio.AbstractEventLoop | None = None
_bucle_lock = threading.Lock()


def _obtener_bucle() -> asyncio.AbstractEventLoop:
    global _bucle
    with _bucle_lock:
        if _bucle is None or _bucle.is_closed():
            bucle = asyncio.new_event_loop()
            hilo = threading.Thread(target=bucle.run_forever, name="ocr-winrt", daemon=True)
            hilo.start()
            _bucle = bucle
        return _bucle


def _ejecutar(coro, timeout: float = 30.0):
    futuro = asyncio.run_coroutine_threadsafe(coro, _obtener_bucle())
    return futuro.result(timeout)


# --------------------------------------------------------------------------
# Motores OCR
# --------------------------------------------------------------------------
_motores: dict[str, Any] = {}
_motores_lock = threading.Lock()
_ocr_lock = threading.Lock()


def idiomas_disponibles() -> list[str]:
    from winrt.windows.media.ocr import OcrEngine

    return [l.language_tag for l in OcrEngine.available_recognizer_languages]


def _motor(idioma: str):
    """Devuelve un OcrEngine para `idioma`, con respaldo en-US y luego el del perfil."""
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    with _motores_lock:
        if idioma in _motores:
            return _motores[idioma]
        motor = None
        for tag in (idioma, IDIOMA_RESPALDO):
            try:
                lang = Language(tag)
                if OcrEngine.is_language_supported(lang):
                    motor = OcrEngine.try_create_from_language(lang)
            except Exception:
                motor = None
            if motor is not None:
                break
        if motor is None:
            motor = OcrEngine.try_create_from_user_profile_languages()
        if motor is None:
            raise RuntimeError(
                "No hay ningún idioma de OCR de Windows instalado. Instala el paquete "
                "'Language.OCR~~~es-ES~0.0.1.0' (Configuración > Hora e idioma)."
            )
        _motores[idioma] = motor
        return motor


def _a_software_bitmap(img: Image.Image):
    import winrt.windows.graphics.imaging as gi
    import winrt.windows.storage.streams as ss

    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    datos = Image.merge("RGBA", (b, g, r, a)).tobytes()  # BGRA8
    escritor = ss.DataWriter()
    escritor.write_bytes(datos)
    buffer = escritor.detach_buffer()
    return gi.SoftwareBitmap.create_copy_from_buffer(
        buffer, gi.BitmapPixelFormat.BGRA8, rgba.width, rgba.height
    )


# --------------------------------------------------------------------------
# Preprocesado
# --------------------------------------------------------------------------
def _recortar(img: Image.Image, region) -> tuple[Image.Image, int, int]:
    if not region:
        return img, 0, 0
    x, y, w, h = (int(round(v)) for v in region)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.width, x + w), min(img.height, y + h)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"La región {region} queda fuera de la imagen {img.size}")
    return img.crop((x0, y0, x1, y1)), x0, y0


def preprocesar(
    img: Image.Image,
    escala: float | None = None,
    invertir: bool | None = None,
    umbral: int | None = None,
) -> tuple[Image.Image, float]:
    """Prepara texto de interfaz de juego para el OCR.

    - Gris por canal máximo (no luminancia): el texto de color (verde, azul,
      dorado según el grado) sigue siendo claro sobre el fondo oscuro.
    - Inversión automática si el fondo es oscuro (el OCR prefiere texto oscuro
      sobre claro).
    - Autocontraste, escala 2–3× (Lanczos) y umbral opcional.
    Devuelve (imagen_en_gris, escala_aplicada).
    """
    arr = np.asarray(img.convert("RGB"))
    gris = Image.fromarray(arr.max(axis=2).astype(np.uint8), "L")
    if invertir is None:
        # Mediana: representa el fondo aunque haya mucho texto.
        invertir = float(np.median(np.asarray(gris))) < 110
    if invertir:
        gris = ImageOps.invert(gris)
    gris = ImageOps.autocontrast(gris, cutoff=1)

    if escala is None:
        escala = 3.0 if gris.height <= 360 else 2.0
    max_dim = 9800
    escala = max(1.0, min(escala, max_dim / max(gris.width, gris.height)))
    if escala != 1.0:
        gris = gris.resize(
            (max(1, round(gris.width * escala)), max(1, round(gris.height * escala))),
            Image.Resampling.LANCZOS,
        )
    if umbral is not None:
        gris = gris.point(lambda p: 255 if p > umbral else 0)
    return gris, escala


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------
def reconocer(img: Image.Image, idioma: str = "es-ES") -> list[LineaOCR]:
    """OCR directo, sin preprocesado. Coordenadas en píxeles de `img`."""
    motor = _motor(idioma)
    bitmap = _a_software_bitmap(img)

    async def _ocr():
        return await motor.recognize_async(bitmap)

    # Un OcrEngine no admite dos RecognizeAsync a la vez: se serializa.
    with _ocr_lock:
        resultado = _ejecutar(_ocr())
    lineas: list[LineaOCR] = []
    for linea in resultado.lines:
        palabras = []
        for p in linea.words:
            r = p.bounding_rect
            palabras.append({"texto": p.text, "x": r.x, "y": r.y, "w": r.width, "h": r.height})
        if not palabras:
            continue
        lineas.append(_linea(linea.text, palabras))
    return lineas


def _linea(texto: str, palabras: list[dict]) -> LineaOCR:
    x0 = min(p["x"] for p in palabras)
    y0 = min(p["y"] for p in palabras)
    x1 = max(p["x"] + p["w"] for p in palabras)
    y1 = max(p["y"] + p["h"] for p in palabras)
    return {"texto": texto, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "palabras": palabras}


def leer_imagen(
    img: Image.Image,
    region: tuple | None = None,
    idioma: str = "es-ES",
    escala: float | None = None,
    invertir: bool | None = None,
    umbral: int | None = None,
) -> list[LineaOCR]:
    """Recorta `region` (x, y, w, h), preprocesa y aplica OCR.

    Las cajas devueltas están en coordenadas de la imagen original.
    """
    recorte, dx, dy = _recortar(img, region)
    prep, factor = preprocesar(recorte, escala=escala, invertir=invertir, umbral=umbral)
    lineas = reconocer(prep, idioma=idioma)
    salida = []
    for linea in lineas:
        palabras = [
            {
                "texto": p["texto"],
                "x": p["x"] / factor + dx,
                "y": p["y"] / factor + dy,
                "w": p["w"] / factor,
                "h": p["h"] / factor,
            }
            for p in linea["palabras"]
        ]
        salida.append(_linea(linea["texto"], palabras))
    return salida
