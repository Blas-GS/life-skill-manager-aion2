"""Iconos oficiales del juego, opcionales y solo en local.

Los iconos de AION 2 son de NCSOFT: no se publican con el proyecto. Si el usuario lo pide (Ajustes),
se descargan de metabot.gg a data/iconos/ (carpeta ignorada por git), con pausa entre peticiones,
y la API los sirve desde ahí. Sin ellos la interfaz usa los iconos propios por categoría.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
DIR_ICONOS = RAIZ / "data" / "iconos"
CABECERAS = {
    "User-Agent": "life-skill-manager-aion2/0.1 (personal non-commercial crafting calculator; "
    "icons cached locally, 1 request per second; credits metabot.gg)",
}
_NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_.-]+\.(webp|png|jpg)$")
_ORIGEN = "https://metabot.gg/"


def nombre_archivo(url: str | None) -> str | None:
    """Nombre local del icono (último tramo de la URL de metabot.gg), o None si no vale."""
    if not url or not url.startswith(_ORIGEN):
        return None
    nombre = url.rsplit("/", 1)[-1].split("?")[0]
    return nombre if _NOMBRE_VALIDO.match(nombre) else None


def ruta_icono(nombre: str, carpeta: Path = DIR_ICONOS) -> Path | None:
    """Ruta de un icono descargado; None si el nombre no es válido o no existe."""
    if not _NOMBRE_VALIDO.match(nombre or ""):
        return None
    ruta = carpeta / nombre
    return ruta if ruta.is_file() else None


class DescargaIconos:
    """Descarga en segundo plano los iconos que falten. Una sola descarga a la vez."""

    def __init__(self, carpeta: Path = DIR_ICONOS, pausa: float = 1.0,
                 transport: httpx.BaseTransport | None = None):
        self.carpeta = carpeta
        self.pausa = pausa
        self.transport = transport
        self._hilo: threading.Thread | None = None
        self._cerrojo = threading.Lock()
        self.estado = {"activa": False, "hechos": 0, "total": 0, "errores": 0, "mensaje": ""}

    def presentes(self) -> set[str]:
        if not self.carpeta.is_dir():
            return set()
        return {p.name for p in self.carpeta.iterdir() if _NOMBRE_VALIDO.match(p.name)}

    def mapa(self, objetos: dict) -> dict[str, str]:
        """{id de objeto: nombre de archivo} de los iconos que ya están en local."""
        hay = self.presentes()
        salida = {}
        for oid, o in (objetos or {}).items():
            n = nombre_archivo((o or {}).get("icono"))
            if n and n in hay:
                salida[str(oid)] = n
        return salida

    def iniciar(self, objetos: dict) -> dict:
        with self._cerrojo:
            if self.estado["activa"]:
                return dict(self.estado)
            urls = {}
            for o in (objetos or {}).values():
                url = (o or {}).get("icono")
                n = nombre_archivo(url)
                if n:
                    urls[n] = url
            hay = self.presentes()
            faltan = [(n, u) for n, u in sorted(urls.items()) if n not in hay]
            self.estado = {"activa": bool(faltan), "hechos": 0, "total": len(faltan), "errores": 0,
                           "mensaje": "" if faltan else "Ya tienes todos los iconos."}
            if faltan:
                self._hilo = threading.Thread(target=self._descargar, args=(faltan,), name="iconos", daemon=True)
                self._hilo.start()
            return dict(self.estado)

    def esperar(self, segundos: float = 30) -> None:
        if self._hilo is not None:
            self._hilo.join(segundos)

    def _descargar(self, faltan: list[tuple[str, str]]) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(headers=CABECERAS, follow_redirects=True, timeout=30,
                              transport=self.transport) as cliente:
                for i, (nombre, url) in enumerate(faltan):
                    if i and self.pausa:
                        time.sleep(self.pausa)
                    try:
                        r = cliente.get(url)
                        if r.status_code == 200 and r.content:
                            tmp = self.carpeta / (nombre + ".part")
                            tmp.write_bytes(r.content)
                            tmp.replace(self.carpeta / nombre)
                        else:
                            self.estado["errores"] += 1
                    except httpx.HTTPError:
                        self.estado["errores"] += 1
                    self.estado["hechos"] = i + 1
            fallos = self.estado["errores"]
            self.estado["mensaje"] = (f"Descargados {self.estado['hechos'] - fallos} iconos"
                                      + (f"; {fallos} no se pudieron bajar." if fallos else "."))
        finally:
            self.estado["activa"] = False
