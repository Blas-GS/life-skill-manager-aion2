"""Gestión de archivos temporales: nada se acumula y nada se borra sin verificar.

Registro en `capturas/tmp/registro.json`:
{
  "version": 1,
  "archivos": { "<ruta absoluta>": {"tipo": "video"|"captura", "ids": ["uuid", ...], "registrado": "..."} },
  "recortes": { "<ruta absoluta>": {"revisado": false, "objeto_id": 123, "nombre_leido": "...", "registrado": "..."} }
}

Flujo:
  1. Se procesa un vídeo/captura → el usuario revisa → `repo.guardar_lecturas(...)` → ids.
  2. `registrar_temporal(ruta, ids)`.
  3. `limpiar_verificados(repo)` (al arrancar y tras cada guardado): borra un archivo
     SOLO si `repo.verificar_lecturas(ids)` devuelve exactamente True. Si devuelve
     False, lanza una excepción o no hay ids, el archivo se conserva.
  4. Los recortes de filas dudosas (`capturas/tmp/revision/`) se borran cuando
     el usuario las ha revisado (`marcar_revisado` + `limpiar_revisados`).
  5. `aplicar_tope(mb)` avisa si `capturas/tmp/` supera el tope; no borra nada sin verificar.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DIR_TMP = RAIZ / "capturas" / "tmp"


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clave(ruta) -> str:
    return os.path.normcase(os.path.abspath(str(ruta)))


def _tipo_por_extension(ruta: str) -> str:
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"):
        return "video"
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        return "captura"
    return "otro"


class Temporales:
    def __init__(self, dir_tmp: Path | str = DIR_TMP):
        self.dir_tmp = Path(dir_tmp)
        self.ruta_registro = self.dir_tmp / "registro.json"
        self._lock = threading.RLock()

    # -- persistencia --
    def _cargar(self) -> dict:
        try:
            datos = json.loads(self.ruta_registro.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            datos = {}
        datos.setdefault("version", 1)
        datos.setdefault("archivos", {})
        datos.setdefault("recortes", {})
        return datos

    def _guardar(self, datos: dict) -> None:
        self.dir_tmp.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta_registro.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.ruta_registro)

    def registro(self) -> dict:
        with self._lock:
            return self._cargar()

    # -- archivos de origen (vídeos, capturas) --
    def registrar_temporal(self, ruta, lecturas_ids, tipo: str | None = None) -> dict:
        """Asocia un archivo con los ids de las lecturas guardadas a partir de él.
        Se puede llamar varias veces: los ids se acumulan."""
        clave = _clave(ruta)
        with self._lock:
            datos = self._cargar()
            entrada = datos["archivos"].setdefault(
                clave, {"tipo": tipo or _tipo_por_extension(clave), "ids": [], "registrado": _ahora()}
            )
            for i in lecturas_ids or []:
                if i is not None and str(i) not in entrada["ids"]:
                    entrada["ids"].append(str(i))
            if tipo:
                entrada["tipo"] = tipo
            self._guardar(datos)
            return dict(entrada)

    def esta_registrado(self, ruta) -> bool:
        with self._lock:
            return _clave(ruta) in self._cargar()["archivos"]

    def limpiar_verificados(self, repo) -> dict:
        """Borra los archivos cuyas lecturas confirma `repo.verificar_lecturas(ids)`.

        Devuelve {"borrados": [...], "conservados": [...], "errores": {ruta: motivo}}.
        """
        borrados, conservados, errores = [], [], {}
        with self._lock:
            datos = self._cargar()
            for ruta, entrada in list(datos["archivos"].items()):
                ids = entrada.get("ids") or []
                if not ids:
                    conservados.append(ruta)
                    continue
                try:
                    ok = repo.verificar_lecturas(list(ids))
                except Exception as e:  # noqa: BLE001 — sin conexión, etc.
                    errores[ruta] = f"No se pudo verificar: {e}"
                    conservados.append(ruta)
                    continue
                if ok is not True:
                    conservados.append(ruta)
                    continue
                try:
                    if os.path.isfile(ruta):
                        os.remove(ruta)
                except OSError as e:
                    errores[ruta] = f"No se pudo borrar: {e}"
                    conservados.append(ruta)
                    continue
                del datos["archivos"][ruta]
                borrados.append(ruta)
            self._guardar(datos)
        return {"borrados": borrados, "conservados": conservados, "errores": errores}

    # -- recortes de filas dudosas --
    def registrar_recorte(self, ruta, fila: dict | None = None) -> None:
        fila = fila or {}
        with self._lock:
            datos = self._cargar()
            datos["recortes"][_clave(ruta)] = {
                "revisado": False,
                "objeto_id": fila.get("objeto_id"),
                "nombre_leido": fila.get("nombre_leido"),
                "precio": fila.get("precio"),
                "cantidad": fila.get("cantidad"),
                "registrado": _ahora(),
            }
            self._guardar(datos)

    def recortes_pendientes(self) -> dict[str, dict]:
        with self._lock:
            return {r: e for r, e in self._cargar()["recortes"].items() if not e.get("revisado")}

    def marcar_revisado(self, ruta) -> bool:
        with self._lock:
            datos = self._cargar()
            entrada = datos["recortes"].get(_clave(ruta))
            if entrada is None:
                return False
            entrada["revisado"] = True
            self._guardar(datos)
            return True

    def _dentro_de_tmp(self, ruta: str) -> bool:
        try:
            Path(ruta).resolve().relative_to(self.dir_tmp.resolve())
            return True
        except ValueError:
            return False

    def limpiar_revisados(self) -> list[str]:
        """Borra los recortes ya revisados (solo dentro de capturas/tmp)."""
        borrados = []
        with self._lock:
            datos = self._cargar()
            for ruta, entrada in list(datos["recortes"].items()):
                if not entrada.get("revisado"):
                    continue
                if self._dentro_de_tmp(ruta):
                    try:
                        if os.path.isfile(ruta):
                            os.remove(ruta)
                    except OSError:
                        continue
                del datos["recortes"][ruta]
                borrados.append(ruta)
            self._guardar(datos)
        return borrados

    # -- tamaño --
    def tamano_mb(self) -> float:
        total = 0
        if self.dir_tmp.is_dir():
            for raiz, _, archivos in os.walk(self.dir_tmp):
                for a in archivos:
                    try:
                        total += os.path.getsize(os.path.join(raiz, a))
                    except OSError:
                        pass
        return total / (1024 * 1024)

    def aplicar_tope(self, mb: float = 500, repo=None) -> dict:
        """Comprueba el tamaño de capturas/tmp. Si lo supera y hay `repo`, intenta
        antes limpiar lo verificado y los recortes revisados. Nunca borra nada sin
        verificar: si sigue por encima, solo avisa."""
        tamano = self.tamano_mb()
        limpieza = None
        if tamano > mb:
            self.limpiar_revisados()
            if repo is not None:
                limpieza = self.limpiar_verificados(repo)
            tamano = self.tamano_mb()
        excedido = tamano > mb
        aviso = None
        if excedido:
            pendientes = len(self.recortes_pendientes())
            aviso = (
                f"La carpeta de temporales ocupa {tamano:.0f} MB (tope {mb:.0f} MB). "
                f"Hay {pendientes} recortes sin revisar y archivos cuyas lecturas aún no "
                "se han podido verificar en la base de datos. Revísalos o sube la cola "
                "pendiente; no se borra nada sin verificar."
            )
        return {
            "tamano_mb": round(tamano, 2),
            "tope_mb": mb,
            "excedido": excedido,
            "aviso": aviso,
            "limpieza": limpieza,
        }


# --------------------------------------------------------------------------
# Funciones de módulo sobre la instancia por defecto (capturas/tmp)
# --------------------------------------------------------------------------
_por_defecto = Temporales()


def configurar(dir_tmp) -> Temporales:
    """Cambia la carpeta de temporales por defecto (útil en tests)."""
    global _por_defecto
    _por_defecto = Temporales(dir_tmp)
    return _por_defecto


def instancia() -> Temporales:
    return _por_defecto


def registrar_temporal(ruta, lecturas_ids, tipo=None):
    return _por_defecto.registrar_temporal(ruta, lecturas_ids, tipo)


def esta_registrado(ruta) -> bool:
    return _por_defecto.esta_registrado(ruta)


def limpiar_verificados(repo) -> dict:
    return _por_defecto.limpiar_verificados(repo)


def registrar_recorte(ruta, fila=None):
    return _por_defecto.registrar_recorte(ruta, fila)


def recortes_pendientes() -> dict:
    return _por_defecto.recortes_pendientes()


def marcar_revisado(ruta) -> bool:
    return _por_defecto.marcar_revisado(ruta)


def limpiar_revisados() -> list[str]:
    return _por_defecto.limpiar_revisados()


def aplicar_tope(mb: float = 500, repo=None) -> dict:
    return _por_defecto.aplicar_tope(mb, repo)
