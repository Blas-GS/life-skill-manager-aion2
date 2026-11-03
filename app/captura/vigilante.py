"""Vigila una carpeta de capturas sueltas (Impr Pant, F12 de Steam...) y las lee.

Sondeo simple (sin dependencias nuevas): cada `intervalo` segundos lista la
carpeta y procesa las imágenes nuevas cuyo tamaño ya no cambia (evita leer una
captura a medio escribir). No borra nada: las imágenes se borran con
`temporales.limpiar_verificados` cuando sus lecturas están guardadas y
verificadas. Las imágenes ya registradas en temporales no se reprocesan.

Carpeta vigilada (en este orden):
  1. el parámetro `carpeta`;
  2. la variable de entorno `AION2_CARPETA_CAPTURAS` (p.ej. en `.env`);
  3. `capturas/pendientes` dentro del proyecto.

Para usar las capturas de Steam (F12): Steam > Ajustes > Capturas de pantalla >
"Carpeta de capturas" muestra la ruta; la de por defecto es
  C:\\Program Files (x86)\\Steam\\userdata\\<id_usuario>\\760\\remote\\<id_app>\\screenshots
`carpetas_steam()` lista las que existan. Ojo: tras verificar las lecturas se
borran las imágenes de esa carpeta (es lo que se quiere para no acumular); si
prefieres conservarlas, cambia en Steam la carpeta a `capturas/pendientes`.
"""
from __future__ import annotations

import glob
import os
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image

from . import parser, temporales
from .grabacion import procesar_imagen

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_POR_DEFECTO = RAIZ / "capturas" / "pendientes"
EXTENSIONES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def carpeta_configurada(carpeta=None) -> Path:
    return Path(carpeta or os.environ.get("AION2_CARPETA_CAPTURAS") or CARPETA_POR_DEFECTO)


def carpetas_steam() -> list[str]:
    """Carpetas de capturas de Steam que existen en este PC (solo lectura)."""
    bases = [
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Steam"),
    ]
    salida = []
    for base in bases:
        salida.extend(glob.glob(os.path.join(base, "userdata", "*", "760", "remote", "*", "screenshots")))
    return sorted(set(salida))


class Vigilante:
    """`al_procesar(ruta, filas)` se llama por cada imagen leída;
    `al_error(ruta, excepcion)` si falla."""

    def __init__(self, carpeta=None, cat=None, intervalo: float = 2.0,
                 al_procesar: Callable[[str, list], None] | None = None,
                 al_error: Callable[[str, BaseException], None] | None = None,
                 extensiones=EXTENSIONES, region=None, columnas=None, idioma: str = "es-ES",
                 faccion: str | None = None):
        self.carpeta = carpeta_configurada(carpeta)
        self.indice = parser._indice(cat, faccion)
        self.intervalo = max(0.2, float(intervalo))
        self.al_procesar = al_procesar
        self.al_error = al_error
        self.extensiones = tuple(e.lower() for e in extensiones)
        self.region = region
        self.columnas = columnas
        self.idioma = idioma
        self._vistos: dict[str, tuple] = {}      # ruta -> (tamaño, mtime) ya procesado/fallido
        self._candidatos: dict[str, tuple] = {}  # ruta -> (tamaño, mtime) visto una vez
        self.resultados: dict[str, list] = {}     # ruta -> filas (hasta que se recojan)
        self.errores: dict[str, str] = {}
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()

    # -- una pasada --
    def revisar(self) -> list[tuple[str, list]]:
        """Una pasada de sondeo. Devuelve [(ruta, filas)] de las imágenes leídas ahora."""
        if not self.carpeta.is_dir():
            return []
        leidas = []
        actuales = set()
        for entrada in os.scandir(self.carpeta):
            if not entrada.is_file() or not entrada.name.lower().endswith(self.extensiones):
                continue
            ruta = os.path.abspath(entrada.path)
            actuales.add(ruta)
            try:
                st = entrada.stat()
            except OSError:
                continue
            firma = (st.st_size, st.st_mtime)
            if self._vistos.get(ruta) == firma:
                continue
            if temporales.esta_registrado(ruta):
                self._vistos[ruta] = firma
                continue
            # Esperar a que el archivo deje de crecer (dos sondeos iguales).
            if self._candidatos.get(ruta) != firma or st.st_size == 0:
                self._candidatos[ruta] = firma
                continue
            self._candidatos.pop(ruta, None)
            self._vistos[ruta] = firma
            try:
                filas = self.procesar_archivo(ruta)
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    self.errores[ruta] = str(e)
                if self.al_error:
                    self.al_error(ruta, e)
                continue
            with self._lock:
                self.resultados[ruta] = filas
                self.errores.pop(ruta, None)
            leidas.append((ruta, filas))
            if self.al_procesar:
                self.al_procesar(ruta, filas)
        # Olvidar archivos que ya no existen.
        for ruta in list(self._vistos):
            if ruta not in actuales:
                self._vistos.pop(ruta, None)
                with self._lock:
                    self.resultados.pop(ruta, None)
                    self.errores.pop(ruta, None)
        for ruta in list(self._candidatos):
            if ruta not in actuales:
                self._candidatos.pop(ruta, None)
        return leidas

    def procesar_archivo(self, ruta) -> list[dict]:
        # Se carga en memoria y se cierra el archivo para que luego se pueda borrar.
        with Image.open(ruta) as im:
            img = im.convert("RGB")
        return procesar_imagen(img, self.indice, region=self.region, columnas=self.columnas,
                               idioma=self.idioma)

    def recoger(self) -> dict[str, list]:
        """Devuelve y vacía las filas leídas pendientes de revisar/guardar."""
        with self._lock:
            r, self.resultados = self.resultados, {}
        return r

    # -- hilo --
    def iniciar(self) -> "Vigilante":
        if self._hilo and self._hilo.is_alive():
            return self
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, name="vigilante-capturas", daemon=True)
        self._hilo.start()
        return self

    def detener(self, timeout: float = 10.0):
        self._parar.set()
        if self._hilo:
            self._hilo.join(timeout)

    def _bucle(self):
        while not self._parar.is_set():
            try:
                self.revisar()
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    self.errores["_carpeta"] = str(e)
            self._parar.wait(self.intervalo)

    def estado(self) -> dict:
        with self._lock:
            return {
                "activo": bool(self._hilo and self._hilo.is_alive()),
                "carpeta": str(self.carpeta),
                "existe": self.carpeta.is_dir(),
                "pendientes_de_revisar": len(self.resultados),
                "errores": dict(self.errores),
                "ultima_revision": time.time(),
            }
