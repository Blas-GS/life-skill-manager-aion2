"""REST API + web dashboard (FastAPI). Start: `uvicorn app.main:app --port 8000` or iniciar.bat.

Prefix /api; the frontend lives in app/static/. The logic is in app/servicios.py.
Security: the app only reads the screen (passive captures); it never sends clicks or keys to the game.
The Supabase key stays in the backend (.env) and is never sent to the browser.
"""
from __future__ import annotations

import logging
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.categorias import mapa_categorias
from app.db import ErrorBaseDatos
from app.iconos import DescargaIconos, ruta_icono
from app.servicios import DIR_TMP, NoDisponible, Servicios, limpio

log = logging.getLogger("aion2.api")
DIR_STATIC = Path(__file__).resolve().parent / "static"
MAX_SUBIDA = 8 * 1024 ** 3  # 8 GB


def crear_app(servicios: Servicios | None = None, arrancar: bool = True,
              iconos: DescargaIconos | None = None) -> FastAPI:
    serv = servicios or Servicios()
    descarga_iconos = iconos or DescargaIconos()

    @asynccontextmanager
    async def ciclo(app_: FastAPI):
        if arrancar:
            # in the background: uploading the queue to Supabase can take a while when offline
            threading.Thread(target=serv.arranque, name="arranque", daemon=True).start()
        yield
        if serv.grabacion is not None:
            try:
                serv.detener_grabacion()
            except Exception:  # noqa: BLE001
                pass

    app = FastAPI(title="Life Skill Manager - Aion 2", lifespan=ciclo,
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.servicios = serv

    @app.exception_handler(NoDisponible)
    async def _no_disponible(_: Request, e: NoDisponible):
        return JSONResponse(status_code=503, content={"detail": str(e), "componente": e.componente})

    @app.exception_handler(ValueError)
    async def _valor(_: Request, e: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(e)})

    @app.exception_handler(LookupError)
    async def _no_existe(_: Request, e: LookupError):
        return JSONResponse(status_code=404, content={"detail": str(e).strip("'\"")})

    @app.exception_handler(ErrorBaseDatos)
    async def _base_datos(_: Request, e: ErrorBaseDatos):
        return JSONResponse(status_code=503, content={"detail": f"Base de datos: {e}"})

    @app.exception_handler(Exception)
    async def _otro(_: Request, e: Exception):
        log.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": f"Error interno: {type(e).__name__}: {e}"})

    # --- status -----------------------------------------------------------------
    @app.get("/api/estado")
    def estado():
        return serv.estado()

    @app.post("/api/estado/subir-cola")
    def subir_cola():
        return {"subidas": serv.repo.subir_pendientes(), **serv.estado()}

    # --- servers and profiles -------------------------------------------------------
    @app.get("/api/servidores")
    def servidores():
        return serv.servidores()

    @app.post("/api/servidores")
    def guardar_servidor(datos: dict = Body(...)):
        return serv.guardar_servidor(datos)

    @app.get("/api/perfiles")
    def perfiles():
        return serv.perfiles()

    @app.post("/api/perfiles")
    def guardar_perfil(datos: dict = Body(...)):
        return serv.guardar_perfil(datos)

    @app.get("/api/perfiles/{perfil_id}/contexto")
    def contexto(perfil_id: str):
        ctx = serv.contexto(perfil_id)
        ctx["inventario"] = {str(k): v for k, v in ctx["inventario"].items()}
        return limpio(ctx)

    @app.get("/api/perfiles/{perfil_id}/niveles")
    def niveles(perfil_id: str):
        return serv.niveles(perfil_id)

    @app.put("/api/perfiles/{perfil_id}/niveles")
    def guardar_niveles(perfil_id: str, datos: dict = Body(...)):
        return serv.guardar_niveles(perfil_id, datos)

    @app.get("/api/perfiles/{perfil_id}/inventario")
    def inventario(perfil_id: str):
        return serv.inventario(perfil_id)

    @app.put("/api/perfiles/{perfil_id}/inventario")
    def guardar_inventario(perfil_id: str, datos: dict | list = Body(...)):
        filas = datos if isinstance(datos, list) else datos.get("filas") or [datos]
        return serv.guardar_inventario(perfil_id, filas)

    @app.post("/api/perfiles/{perfil_id}/inventario/pegar")
    def pegar_inventario(perfil_id: str, datos: dict = Body(...)):
        filas = serv.interpretar_pegado(datos.get("texto") or "")
        if datos.get("aplicar"):
            ubic = datos.get("ubicacion") or "inventario"
            buenas = [{"objeto_id": f["objeto_id"], "cantidad": f["cantidad"], "ubicacion": ubic}
                      for f in filas if not f["dudosa"]]
            serv.guardar_inventario(perfil_id, buenas)
            return {"filas": filas, "guardadas": len(buenas)}
        return {"filas": filas}

    # --- settings and NPC ---------------------------------------------------------------
    @app.get("/api/ajustes")
    def ajustes():
        return serv.ajustes()

    @app.put("/api/ajustes")
    def guardar_ajustes(datos: dict = Body(...)):
        return serv.guardar_ajustes(datos)

    @app.get("/api/precios-npc")
    def precios_npc():
        return serv.precios_npc()

    @app.put("/api/precios-npc")
    def guardar_precio_npc(datos: dict = Body(...)):
        return serv.guardar_precio_npc(datos.get("objeto_id"), datos.get("precio"))

    # --- catalog -------------------------------------------------------------------------
    @app.get("/api/catalogo")
    def catalogo_info():
        c = serv.cat
        return {"profesiones": c.profesiones, "recetas": len(c.recetas), "objetos": len(c.objetos), **c.meta}

    @app.get("/api/catalogo/buscar")
    def buscar(q: str = "", limite: int = Query(10, ge=1, le=50)):
        return serv.buscar(q, limite)

    @app.get("/api/catalogo/iconos")
    def iconos():
        """Icon category and Spanish/English name of every object, plus the official icons the user
        downloaded (local only)."""
        objetos = serv.cat.objetos
        nombres = {str(oid): [o.get("nombre"), o.get("nombre_en")] for oid, o in objetos.items()}
        return {"categorias": mapa_categorias(objetos), "nombres": nombres,
                "oficiales": descarga_iconos.mapa(objetos), "descarga": dict(descarga_iconos.estado)}

    @app.post("/api/catalogo/iconos/descargar")
    def descargar_iconos():
        return descarga_iconos.iniciar(serv.cat.objetos)

    @app.get("/api/iconos/{nombre}")
    def icono_local(nombre: str):
        ruta = ruta_icono(nombre, descarga_iconos.carpeta)
        if ruta is None:
            raise HTTPException(404, "Icono no descargado.")
        return FileResponse(ruta, headers={"Cache-Control": "max-age=604800"})

    @app.get("/api/catalogo/objeto/{objeto_id}")
    def objeto(objeto_id: int):
        c = serv.cat
        o = c.objeto(objeto_id)
        if not o:
            raise HTTPException(404, "Ese objeto no está en el catálogo.")
        return {"id": objeto_id, **o, "nombre": c.nombre(objeto_id),
                "recetas": [r["id"] for r in c.recetas_que_producen(objeto_id, con_combo=True)]}

    # --- recipes and opportunities ------------------------------------------------------
    @app.get("/api/recetas")
    def recetas(perfil_id: str | None = None, q: str | None = None, profesion: str | None = None,
                solo_desbloqueadas: bool = False, limite: int = Query(300, ge=1, le=1000)):
        return serv.recetas(perfil_id, q, profesion, solo_desbloqueadas, limite)

    @app.get("/api/recetas/{receta_id}")
    def receta(receta_id: int, perfil_id: str | None = None, intentos: int = Query(1, ge=1, le=10000)):
        return serv.detalle_receta(receta_id, perfil_id, intentos)

    @app.get("/api/recetas/{receta_id}/lista-compra")
    def lista_compra(receta_id: int, perfil_id: str | None = None,
                     intentos: int | None = Query(None, ge=1, le=10000)):
        return serv.lista_compra(receta_id, perfil_id, intentos)

    @app.get("/api/oportunidades")
    def oportunidades(perfil_id: str | None = None, profesion: str | None = None,
                      inversion_max: float | None = Query(None, ge=0), margen_min: float | None = None,
                      incluir_intermedios: bool = True, usar_inventario: bool = True,
                      limite: int = Query(50, ge=1, le=500)):
        # margen_min arrives in % from the dashboard (10 = 10%)
        margen = margen_min / 100.0 if margen_min is not None else None
        return serv.oportunidades(perfil_id, profesion or None, inversion_max, margen, incluir_intermedios,
                                  usar_inventario, limite)

    # --- market -----------------------------------------------------------------------------
    @app.get("/api/mercado/ultimas")
    def ultimas(servidor_id: str, q: str | None = None, limite: int = Query(200, ge=1, le=5000)):
        return serv.ultimas_mercado(servidor_id, q, limite)

    @app.get("/api/mercado/objeto/{objeto_id}")
    def mercado_objeto(objeto_id: int, servidor_id: str, dias: int = Query(30, ge=1, le=3650)):
        return serv.mercado_objeto(servidor_id, objeto_id, dias)

    @app.post("/api/mercado/manual")
    def manual(datos: dict = Body(...)):
        return serv.guardar_manual(datos)

    @app.post("/api/operaciones")
    def operacion(datos: dict = Body(...)):
        return serv.registrar_operacion(datos)

    # --- capture ------------------------------------------------------------------------------
    @app.get("/api/captura/estado")
    def estado_captura():
        return serv.estado_captura()

    @app.post("/api/captura/grabacion/iniciar")
    def iniciar_grabacion(datos: dict = Body(default={})):
        return serv.iniciar_grabacion(datos.get("servidor_id"), datos.get("fps") or 3)

    @app.post("/api/captura/grabacion/detener")
    def detener_grabacion():
        return serv.detener_grabacion()

    @app.post("/api/captura/subir")
    async def subir(request: Request, nombre: str, servidor_id: str):
        """Body = file bytes (video or image). Saved to capturas/tmp and processed in the background."""
        nombre_seguro = Path(nombre).name or "archivo"
        DIR_TMP.mkdir(parents=True, exist_ok=True)
        ruta = DIR_TMP / f"{uuid.uuid4().hex[:12]}_{nombre_seguro}"
        total = 0
        try:
            with open(ruta, "wb") as f:
                async for trozo in request.stream():
                    total += len(trozo)
                    if total > MAX_SUBIDA:
                        raise ValueError("El archivo es demasiado grande (máx. 8 GB).")
                    f.write(trozo)
            if total == 0:
                raise ValueError("El archivo está vacío.")
            return serv.procesar_archivo(ruta, nombre_seguro, servidor_id)
        except Exception:
            ruta.unlink(missing_ok=True)
            raise

    @app.get("/api/captura/sesiones")
    def sesiones():
        return serv.listar_sesiones()

    @app.get("/api/captura/sesiones/{sesion_id}")
    def sesion(sesion_id: str):
        return serv.sesion(sesion_id)

    @app.post("/api/captura/sesiones/{sesion_id}/filas/{idx}")
    def corregir(sesion_id: str, idx: int, datos: dict = Body(...)):
        return serv.corregir_fila(sesion_id, idx, datos)

    @app.post("/api/captura/sesiones/{sesion_id}/guardar")
    def guardar_sesion(sesion_id: str):
        return serv.guardar_sesion(sesion_id)

    @app.get("/api/captura/sesiones/{sesion_id}/filas/{idx}/recorte")
    def recorte(sesion_id: str, idx: int):
        return FileResponse(serv.ruta_recorte(sesion_id, idx))

    @app.get("/api/captura/calibracion")
    def calibracion():
        return serv.calibracion()

    @app.put("/api/captura/calibracion")
    def guardar_calibracion(datos: dict = Body(...)):
        return serv.guardar_calibracion(datos)

    @app.delete("/api/captura/calibracion")
    def borrar_calibracion(ancho: int, alto: int):
        return serv.borrar_calibracion(ancho, alto)

    @app.post("/api/captura/calibracion/pantalla")
    def pantalla(espera: float = Query(0, ge=0, le=10)):
        jpeg, ancho, alto = serv.captura_pantalla(espera)
        return Response(jpeg, media_type="image/jpeg",
                        headers={"X-Ancho": str(ancho), "X-Alto": str(alto), "Cache-Control": "no-store",
                                 "Access-Control-Expose-Headers": "X-Ancho, X-Alto"})

    @app.api_route("/api/{resto:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def no_encontrado(resto: str):
        raise HTTPException(404, f"Ruta de la API desconocida: /api/{resto}")

    # --- frontend --------------------------------------------------------------------------------
    if DIR_STATIC.exists():
        app.mount("/", StaticFiles(directory=DIR_STATIC, html=True), name="static")
    return app


app = crear_app()
