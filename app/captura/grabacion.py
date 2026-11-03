"""Modo grabación: captura PASIVA de pantalla mientras el usuario navega el mercado.

Seguridad (anticheat NCGuard): solo se usa mss para copiar los píxeles de la
pantalla. No se envían clics ni teclas, no se abre el proceso del juego, no se
lee su memoria ni su red.

Los fotogramas viven solo en memoria. Lo único que se escribe en disco son
recortes pequeños de filas dudosas (`capturas/tmp/revision/`) para que el
usuario las revise; se registran en `temporales` y se borran tras revisarlas.

    sesion = SesionGrabacion(fps=3, cat=catalogo)
    sesion.iniciar()
    ...                       # el usuario recorre el mercado a mano
    filas = sesion.detener()  # list[FilaMercado] consolidadas
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import calibracion, parser
from .ocr import leer_imagen

RAIZ = Path(__file__).resolve().parents[2]
DIR_REVISION = RAIZ / "capturas" / "tmp" / "revision"
MAX_RECORTES_SESION = 200


# --------------------------------------------------------------------------
# Deduplicado de fotogramas
# --------------------------------------------------------------------------
class Deduplicador:
    """Decide qué fotogramas merecen OCR.

    Compara una miniatura en gris de la región (lado mayor `lado` px):
      - estable: casi igual que el fotograma ANTERIOR (no se está desplazando
        la lista; evita leer imágenes movidas a medio scroll);
      - nuevo: distinto del último fotograma PROCESADO (si no, es repetido).
    Se usa el número de píxeles que cambian (no la media) para que un solo
    precio distinto cuente como pantalla nueva.
    """

    def __init__(self, lado: int = 640, umbral_pixel: int = 40, min_pixeles: int = 6,
                 exigir_estable: bool = True):
        self.lado = lado
        self.umbral_pixel = umbral_pixel
        self.min_pixeles = min_pixeles
        self.exigir_estable = exigir_estable
        self._anterior: np.ndarray | None = None
        self._procesado: np.ndarray | None = None
        self.vistos = 0
        self.procesados = 0
        self.descartados = 0

    def miniatura(self, img: Image.Image) -> np.ndarray:
        g = img.convert("L")
        f = self.lado / max(g.width, g.height)
        if f < 1:
            g = g.resize((max(1, round(g.width * f)), max(1, round(g.height * f))),
                         Image.Resampling.BILINEAR)
        return np.asarray(g, dtype=np.int16)

    def diferentes(self, a: np.ndarray | None, b: np.ndarray | None) -> bool:
        if a is None or b is None or a.shape != b.shape:
            return True
        cambiados = int(np.count_nonzero(np.abs(a - b) > self.umbral_pixel))
        return cambiados >= self.min_pixeles

    def evaluar(self, img: Image.Image) -> bool:
        """True si hay que hacer OCR de este fotograma."""
        self.vistos += 1
        m = self.miniatura(img)
        estable = not self.exigir_estable or (
            self._anterior is not None and not self.diferentes(m, self._anterior)
        )
        self._anterior = m
        if estable and self.diferentes(m, self._procesado):
            self._procesado = m
            self.procesados += 1
            return True
        self.descartados += 1
        return False


# --------------------------------------------------------------------------
# Procesado de una imagen
# --------------------------------------------------------------------------
def configuracion_imagen(img: Image.Image, region=None, columnas=None, escala=None) -> dict:
    """Mezcla la calibración guardada para el tamaño de la imagen con lo indicado."""
    conf = calibracion.configuracion_para(img.width, img.height)
    if region is not None:
        conf["lista"] = list(region)
    if columnas is not None:
        conf["columnas"] = columnas
    if escala is not None:
        conf["escala"] = escala
    return conf


MAX_RELECTURAS = 12


def _centro_y(p: dict) -> float:
    return p["y"] + p["h"] / 2


def _releer_incompletas(img, lineas, filas, region, idioma, max_filas=MAX_RELECTURAS):
    """El OCR de Windows a veces se salta un número suelto en letra pequeña.
    Para cada fila sin precio o sin cantidad se vuelve a leer SOLO esa franja,
    a más escala, y si salen más números se sustituyen sus palabras.
    Devuelve las líneas corregidas (o las originales si no cambia nada)."""
    incompletas = [f for f in filas if f.get("caja") and (f["precio"] is None or f["cantidad"] is None)]
    if not incompletas:
        return lineas, False
    rx, ry, rw, rh = region
    sustituciones = []
    for f in incompletas[:max_filas]:
        x, y, w, h = f["caja"]
        y0 = max(ry, y - 0.45 * h)
        y1 = min(ry + rh, y + h + 0.45 * h)
        if y1 - y0 < 4:
            continue
        franja = (rx, int(y0), rw, int(round(y1 - y0)) + 1)
        originales = sum(
            parser.es_numerico(p["texto"])
            for l in lineas for p in l["palabras"] if y0 <= _centro_y(p) <= y1
        )
        for esc in (3.0, 4.0, 2.0):
            try:
                nuevas = leer_imagen(img, region=franja, idioma=idioma, escala=esc)
            except Exception:
                break
            palabras = [p for l in nuevas for p in l["palabras"] if y0 <= _centro_y(p) <= y1]
            if sum(parser.es_numerico(p["texto"]) for p in palabras) > originales:
                sustituciones.append((y0, y1, palabras))
                break
    if not sustituciones:
        return lineas, False
    salida = []
    for l in lineas:
        quedan = [p for p in l["palabras"]
                  if not any(a <= _centro_y(p) <= b for a, b, _ in sustituciones)]
        if quedan:
            salida.append(dict(l, palabras=quedan))
    for _, _, palabras in sustituciones:
        salida.append({"texto": " ".join(p["texto"] for p in palabras), "palabras": palabras,
                       "x": 0, "y": 0, "w": 0, "h": 0})
    return salida, True


def procesar_imagen(img: Image.Image, cat, region=None, columnas=None, escala=None,
                    idioma: str = "es-ES", releer: bool = True, faccion: str | None = None) -> list[dict]:
    """OCR + parser de una imagen completa (pantalla, fotograma o captura).
    `cat` puede ser un Catalogo, un dict o un parser.IndiceNombres ya construido."""
    indice = parser._indice(cat, faccion)
    conf = configuracion_imagen(img, region, columnas, escala)
    lineas = leer_imagen(img, region=tuple(conf["lista"]), idioma=idioma, escala=conf["escala"])
    filas = parser.interpretar_pantalla(lineas, indice, columnas=conf["columnas"])
    if releer:
        lineas2, cambio = _releer_incompletas(img, lineas, filas, conf["lista"], idioma)
        if cambio:
            filas = parser.interpretar_pantalla(lineas2, indice, columnas=conf["columnas"])
    return filas


def guardar_recorte(img: Image.Image, fila: dict, carpeta: Path = DIR_REVISION,
                    margen: int = 6, max_ancho: int = 900) -> str | None:
    """Guarda un recorte pequeño (PNG) de una fila dudosa y lo registra."""
    caja = fila.get("caja")
    if not caja:
        return None
    x, y, w, h = caja
    x0, y0 = max(0, int(x) - margen), max(0, int(y) - margen)
    x1, y1 = min(img.width, int(x + w) + margen), min(img.height, int(y + h) + margen)
    if x1 <= x0 or y1 <= y0:
        return None
    rec = img.crop((x0, y0, x1, y1))
    if rec.width > max_ancho:
        rec = rec.resize((max_ancho, max(1, round(rec.height * max_ancho / rec.width))))
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{uuid.uuid4().hex}.png"
    rec.save(ruta, optimize=True)
    try:
        from . import temporales

        temporales.registrar_recorte(ruta, fila)
    except Exception:
        pass
    return str(ruta)


# --------------------------------------------------------------------------
# Sesión de grabación
# --------------------------------------------------------------------------
def _fuente_mss(indice_monitor: int):
    """Devuelve una función que captura el monitor con mss (se crea en el hilo)."""
    import mss

    sct = mss.mss()
    monitores = sct.monitors
    mon = monitores[indice_monitor if 0 < indice_monitor < len(monitores) else 1]

    def capturar() -> Image.Image:
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    capturar.cerrar = sct.close  # type: ignore[attr-defined]
    return capturar


class SesionGrabacion:
    """Captura la pantalla a `fps` en un hilo y acumula filas del mercado.

    - `cat`: catálogo (o IndiceNombres) para emparejar nombres; `faccion`: la
      del servidor ("elyos"|"asmodian") para desambiguar nombres repetidos.
    - `region`/`columnas`: si no se dan, se usa la calibración de la resolución.
    - `fuente`: función sin argumentos que devuelve un PIL.Image (para tests);
      por defecto, mss sobre el monitor calibrado.
    - `al_leer(filas)`: callback opcional tras cada fotograma procesado.
    """

    def __init__(self, fps: float = 3, cat=None, region=None, columnas=None,
                 fuente: Callable[[], Image.Image] | None = None, monitor: int | None = None,
                 guardar_recortes: bool = True, al_leer: Callable[[list], None] | None = None,
                 idioma: str = "es-ES", faccion: str | None = None):
        self.fps = max(0.2, float(fps))
        self.indice = parser._indice(cat, faccion)
        self.region = region
        self.columnas = columnas
        self._fuente = fuente
        self.monitor = monitor
        self.guardar_recortes = guardar_recortes
        self.al_leer = al_leer
        self.idioma = idioma
        self.dedup = Deduplicador()
        self._fotogramas: list[list[dict]] = []
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()
        self.error: BaseException | None = None
        self.recortes = 0
        self._recortadas: set = set()
        self.inicio: float | None = None

    # -- control --
    def iniciar(self) -> "SesionGrabacion":
        if self._hilo and self._hilo.is_alive():
            return self
        self._parar.clear()
        self.inicio = time.time()
        self._hilo = threading.Thread(target=self._bucle, name="grabacion-mercado", daemon=True)
        self._hilo.start()
        return self

    def detener(self, timeout: float = 30.0) -> list[dict]:
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout)
        if self.error:
            raise RuntimeError(f"La grabación falló: {self.error}") from self.error
        return self.filas()

    @property
    def activa(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def filas(self) -> list[dict]:
        with self._lock:
            return parser.consolidar(list(self._fotogramas))

    def estado(self) -> dict:
        with self._lock:
            n_filas = sum(len(f) for f in self._fotogramas)
        return {
            "activa": self.activa,
            "segundos": round(time.time() - self.inicio, 1) if self.inicio else 0,
            "fotogramas_vistos": self.dedup.vistos,
            "fotogramas_procesados": self.dedup.procesados,
            "filas_leidas": n_filas,
            "recortes_dudosos": self.recortes,
            "error": str(self.error) if self.error else None,
        }

    # -- hilo --
    def _bucle(self):
        capturar = self._fuente
        cerrar = None
        try:
            if capturar is None:
                capturar = _fuente_mss(self.monitor or calibracion.monitor())
                cerrar = getattr(capturar, "cerrar", None)
            periodo = 1.0 / self.fps
            while not self._parar.is_set():
                t0 = time.monotonic()
                img = capturar()
                if img is None:
                    break
                self.procesar(img)
                espera = periodo - (time.monotonic() - t0)
                if espera > 0:
                    self._parar.wait(espera)
        except BaseException as e:  # noqa: BLE001 — se informa en detener()/estado()
            self.error = e
        finally:
            if cerrar:
                try:
                    cerrar()
                except Exception:
                    pass

    def procesar(self, img: Image.Image) -> list[dict] | None:
        """Procesa un fotograma (público para poder reutilizarlo y probarlo)."""
        conf = configuracion_imagen(img, self.region, self.columnas)
        x, y, w, h = conf["lista"]
        if not self.dedup.evaluar(img.crop((x, y, x + w, y + h))):
            return None
        filas = procesar_imagen(img, self.indice, region=conf["lista"],
                                columnas=conf["columnas"], escala=conf["escala"], idioma=self.idioma)
        if self.guardar_recortes:
            for f in filas:
                clave = (parser._clave_objeto(f), f.get("precio"), f.get("cantidad"))
                if f["dudosa"] and clave not in self._recortadas and self.recortes < MAX_RECORTES_SESION:
                    f["recorte"] = guardar_recorte(img, f)
                    self._recortadas.add(clave)
                    self.recortes += 1
        with self._lock:
            self._fotogramas.append(filas)
        if self.al_leer:
            try:
                self.al_leer(filas)
            except Exception:
                pass
        return filas
