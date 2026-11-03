# Contratos compartidos entre módulos

Documento de referencia para todas las sesiones de trabajo. Si un módulo necesita cambiar un contrato, lo anota al final en "Cambios propuestos" en vez de cambiarlo en silencio.

Plan completo: `docs/plan.md`.

## Entorno
- Python 3.14.5 en `.venv` (ya creado). Ejecutar siempre con `.\.venv\Scripts\python.exe`.
- Paquetes instalados: fastapi, uvicorn[standard], httpx, python-dotenv, mss, pillow, rapidfuzz, openpyxl, pytest, numpy, opencv-python-headless (cv2 5.0), winrt-runtime + winrt-Windows.Media.Ocr / Graphics.Imaging / Storage.Streams / Foundation / Foundation.Collections / Globalization.
- OCR de Windows disponible con idiomas `en-US` y `es-ES` (ya instalados).
- No hay Node ni Git. Proyecto no versionado: cada sesión toca **solo sus archivos**.
- Si añades un paquete, añádelo también a `requirements.txt` (solo añadir líneas).
- Todo el texto visible para el usuario en **español**. Código e identificadores en español o inglés, pero coherentes dentro de cada módulo.

## 1. Catálogo — `data/catalogo.json` (lo genera `tools/importar_metabot.py`)
```json
{
  "fuente": "metabot.gg",
  "version_cliente": "0.0.4387.0",
  "generado": "2026-11-02T12:00:00Z",
  "profesiones": {"herreria": "Herrería", "armadura": "Armadura", "orfebreria": "Orfebrería", "alquimia": "Alquimia", "cocina": "Cocina"},
  "objetos": {
    "610620013": {
      "nombre": "Mineral de orichalcum",      // nombre oficial ES del cliente
      "nombre_en": "Orichalcum Ore",
      "grado": "common",                      // tal cual venga de la fuente
      "icono": "https://...",                 // opcional
      "comerciable": true,                    // null si desconocido
      "vinculado": false,                     // "(vinculado)"/"(Bound)" en el nombre → true
      "precio_npc": null,                     // precio de tienda NPC en Kinah si se conoce
      "slug": "orichalcum-ore"                // opcional
    }
  },
  "curvas": { "c9": [95.2, 95.4, 95.6] },     // % de éxito; índice = nivel_personaje − nivel_receta (saturar al último)
  "recetas": [
    {
      "id": 115016001,
      "faccion": "elyos",                     // "elyos" | "asmodian" | "ambas"
      "profesion": "herreria",                // clave de "profesiones"
      "nivel": 1,                             // maestría requerida (1–100)
      "producto": 610710001,
      "cantidad": 1,
      "ingredientes": [[610620013, 2], [630541001, 1]],
      "curva": "c9",                          // null = sin curva (100% / herramientas / transferencias)
      "combo_pct": 0,                         // 0–100
      "curva_combo": null,
      "producto_combo": null,                 // id del producto si hay combo (versión espléndida), si se conoce
      "cantidad_combo": null
    }
  ]
}
```
Los ids de objeto son strings en `objetos` (claves JSON) y enteros en `recetas`. `app/catalogo.py` expone:
- `cargar_catalogo(ruta=None) -> Catalogo`
- `Catalogo.objeto(id) -> dict`, `Catalogo.nombre(id) -> str`, `Catalogo.recetas_de(faccion) -> list`, `Catalogo.recetas_que_producen(id) -> list`, `Catalogo.buscar(texto, limite=10) -> list[(id, nombre, puntuacion)]` (rapidfuzz, ignorando tildes/mayúsculas).

## 2. Datos — `app/db.py`
Dos backends con la misma interfaz: **Supabase** (PostgREST vía httpx, si `.env` tiene `SUPABASE_URL` y `SUPABASE_KEY`) y **SQLite local** (`data/aion2.db`, si no). Con Supabase, si falla la red, las escrituras van a `data/pendientes.jsonl` y se reintentan.

```python
repo = obtener_repositorio()          # elige backend según .env
repo.backend -> "supabase" | "local"

# servidores / perfiles
repo.listar_servidores() -> list[dict]           # {id, nombre, faccion, region, comision_registro, impuesto_venta}
repo.guardar_servidor(dict) -> dict
repo.listar_perfiles() -> list[dict]             # {id, nombre, servidor_id}
repo.guardar_perfil(dict) -> dict
repo.niveles(perfil_id) -> dict[str, int]        # {"herreria": 12, ...}
repo.guardar_nivel(perfil_id, profesion, nivel)
repo.inventario(perfil_id) -> dict[int, int]     # objeto_id -> cantidad total (inventario + almacén)
repo.inventario_detalle(perfil_id) -> list[dict] # {objeto_id, cantidad, ubicacion}
repo.guardar_inventario(perfil_id, objeto_id, cantidad, ubicacion="inventario")

# mercado
repo.guardar_lecturas(lecturas: list[Lectura], sesion_id: str|None) -> ResultadoGuardado
repo.verificar_lecturas(ids: list[str]) -> bool   # relee y confirma que existen completas
repo.ultimas_lecturas(servidor_id) -> dict[int, Lectura]           # la más reciente por objeto
repo.historico(servidor_id, objeto_id, desde: datetime) -> list[Lectura]
repo.subir_pendientes() -> int                    # vacía la cola offline; devuelve nº subidas

# otros
repo.precios_npc() -> dict[int, float]; repo.guardar_precio_npc(objeto_id, precio)
repo.ajustes() -> dict; repo.guardar_ajustes(dict)
repo.registrar_operacion(perfil_id, tipo: "venta"|"compra", objeto_id, cantidad, precio, fecha)
```
```python
@dataclass
class Lectura:
    servidor_id: str
    objeto_id: int
    fecha: datetime                 # UTC
    precio_min: float | None
    cantidad_total: int | None      # unidades en oferta
    num_anuncios: int | None
    ofertas: list[tuple[float, int]]  # libro de ofertas [(precio, cantidad)] ordenado por precio
    fuente: str                     # "grabacion" | "video" | "captura" | "manual" | "excel"
    id: str | None = None           # uuid asignado al guardar
```
`ResultadoGuardado`: `{ids: list[str], en_cola: bool}` (en_cola=True si quedó en la cola offline).

Ajustes por defecto: `{"comision_registro": 0.02, "impuesto_venta": 0.10, "rebaja_listado": 1, "combo_fallido": "pierde_todo", "valorar_inventario": "mercado", "tope_tmp_mb": 500}`.

## 3. Motor — `app/calculo.py` y `app/precio_objetivo.py`
```python
analizar_receta(receta, cat, precios, ajustes, nivel, inventario=None, intentos=1) -> dict
# precios: dict[int, InfoPrecio]  InfoPrecio = {precio_min, ofertas, fecha, cantidad_total, num_anuncios} (de ultimas_lecturas) + precios_npc
# devuelve: coste_intento, ingreso_esperado, beneficio_intento, margen, precio_equilibrio,
#           p_exito, p_combo, items_esperados, desbloqueada, desglose_ingredientes[{id, nombre, cantidad, origen: mercado|npc|fabricar|inventario, coste_unit}],
#           max_intentos_mercado, avisos[list[str]], antiguedad_precios_horas
mejores_oportunidades(cat, precios, ajustes, niveles, faccion, inventario=None, filtros=None) -> list[dict]  # ordenadas por beneficio
coste_adquisicion(objeto_id, ...) -> (coste, origen, receta_id|None)   # recursivo, memoizado, anti-ciclos

precio_objetivo_venta(historico: list[Lectura], actual: Lectura|None, ajustes) -> dict
#   {precio_recomendado, rango_p25, mediana, rango_p75, estado: "normal"|"hundido"|"saturado"|"sin_datos", velocidad_dia, dias_para_vender, aviso}
precio_objetivo_compra(historico, actual) -> dict   # {comprar_por_debajo_de, estado}
volumen_estimado(historico) -> float   # unidades/día estimadas por caídas de cantidad_total entre lecturas consecutivas
```

## 4. Captura y OCR — `app/captura/`
```python
# ocr.py
leer_imagen(img: PIL.Image, region: tuple|None, idioma="es-ES") -> list[LineaOCR]  # LineaOCR = {texto, x, y, w, h, palabras[...]}
# parser.py
interpretar_pantalla(lineas, cat) -> list[FilaMercado]
# FilaMercado = {objeto_id|None, nombre_leido, precio|None, cantidad|None, confianza: 0–1, dudosa: bool}
# grabacion.py  — SesionGrabacion(fps=3).iniciar()/detener() -> list[FilaMercado]; fotogramas solo en memoria
# video.py      — procesar_video(ruta, cat) -> list[FilaMercado]
# vigilante.py  — vigila una carpeta de capturas sueltas
# temporales.py — registrar_temporal(ruta, lecturas_ids); limpiar_verificados(repo); aplicar_tope(mb)
```
Las filas se convierten a `Lectura` y se guardan con `repo.guardar_lecturas`; los archivos solo se borran tras `repo.verificar_lecturas(ids) == True`.

## 5. API — `app/main.py` (integración, se hace al final)
Prefijo `/api`. Sirve `app/static/`. Puerto 8000.

## Cambios propuestos
- **[datos, 2026-11-02] Ampliaciones compatibles de `app/db.py`** (lo del contrato funciona igual):
  - `ResultadoGuardado` tiene además `error: str | None` (motivo si quedó en cola).
  - `historico(servidor_id, objeto_id, desde=None, con_ofertas=True)`: `desde=None` = todo; `con_ofertas=False` evita descargar el libro de ofertas (más rápido para `volumen_estimado`).
  - `guardar_lecturas` asigna `lectura.id` (uuid) en el propio objeto y ordena `lectura.ofertas` por precio. Valida `fuente`; si es inválida lanza `ValueError` (no encola).
  - `verificar_lecturas([])` devuelve True. Devuelve False (no lanza) si alguna lectura está en cola, no existe, le faltan ofertas o no hay conexión.
  - `registrar_operacion(..., fecha=None)` → `dict` con el `id`; `precio` es **por unidad**. Sin red, en Supabase va a la cola (`"en_cola": True`).
  - Extras: `repo.operaciones(perfil_id=None, desde=None) -> list[dict]`, `repo.num_pendientes() -> int`, `repo.pendientes() -> list[dict]` (solo Supabase: resumen de la cola con errores), `repo.sincronizar_catalogo(datos_catalogo_json) -> dict` (copia el catálogo a las tablas `objetos`/`recetas`/…), `repo.cerrar()`.
  - `guardar_inventario(..., cantidad<=0)` borra la fila; `guardar_precio_npc(id, None)` borra el precio.
  - `guardar_servidor` / `guardar_perfil` sin `id` generan un uuid; con `id` actualizan solo los campos pasados. `faccion` se normaliza a minúsculas y debe ser `elyos` | `asmodian`. `comision_registro`/`impuesto_venta` del servidor pueden ser null (= usar ajuste global).
  - Errores: `app.db.ErrorBaseDatos` (y su subclase `ErrorRed` para falta de conexión).
  - Seguridad (para la API): el panel nunca habla con Supabase directamente; la clave secreta solo vive en el backend. Recomendado que uvicorn escuche en `127.0.0.1`, no en `0.0.0.0`.
- **[motor, 2026-11-02] Ampliaciones compatibles de `app/calculo.py` / `app/precio_objetivo.py`** (las firmas del contrato funcionan igual):
  - **Para el catálogo**: el motor acepta el `dict` crudo de `catalogo.json` o un objeto `Catalogo`. Del objeto necesita leer las curvas y la lista completa de recetas: por favor, que `Catalogo` exponga `.datos` (el dict crudo) **o** `.curvas` (dict) + `.recetas` (list) + `.objetos` (dict). Sin eso, solo puede usar `recetas_de("elyos"/"asmodian")` y asumirá 100% en las curvas.
  - `precios[id]` (InfoPrecio) puede ser dict o `Lectura`; campos opcionales extra: `precio_npc`, `volumen_dia` (de `volumen_estimado`, para avisar de saturación). Los precios NPC también se pueden pasar como kwarg `precios_npc={id: precio}` o tomarse de `objetos[id].precio_npc` del catálogo.
  - `analizar_receta(..., *, niveles=None, faccion=None, precios_npc=None, ahora=None)`: `niveles` hace falta para valorar ingredientes que se fabrican con **otra** profesión; `ahora` (UTC) para tests.
  - `coste_adquisicion(objeto_id, cat, precios, ajustes=None, niveles=None, faccion=None, inventario=None, precios_npc=None)`.
  - `mejores_oportunidades(..., *, precios_npc=None, ahora=None)`; `filtros`: `profesion` (str|list), `inversion_max`, `margen_min` (fracción), `incluir_intermedios` (True), `solo_desbloqueadas` (True), `solo_rentables` (True), `incluir_sin_precio` (False), `tope_intentos`, `ordenar_por` ("beneficio_total"|"beneficio_intento"|"margen"), `limite`. Cada resultado añade `intentos_recomendados`, `inversion` (Kinah a desembolsar), `es_intermedio`.
  - Claves extra en `analizar_receta`: `receta_id, producto, nombre, profesion, nivel_receta, nivel, intentos, p_exito_simple, p_combo_activado, p_combo_fallido, salidas_esperadas {id: unidades}, coste_total, coste_por_objeto, precio_venta, beneficio_total, intentos_con_inventario, faltan [{id, nombre, faltan, coste}], coste_faltante, mensaje_inventario`. En `desglose_ingredientes` además: `unidades_necesarias, en_inventario, faltan, origenes {origen: unidades}, coste_total, coste_faltante, receta_id`. `p_combo` = P(combo **exitoso**). Probabilidades como fracción 0–1. `max_intentos_mercado=None` = sin límite conocido (no hay libro ni cantidad).
  - Ajustes nuevos (con defecto): `horas_precio_antiguo` 24, `max_anuncios` 10, `unidades_por_anuncio` 1, `anuncios_saturado` 50, `dias_saturado` 7, `tope_intentos` 100, `nivel_por_defecto` 1, `rebaja_saturado_pct` 0.03, `min_lecturas_historico` 3, `horas_min_volumen` 12.
  - `precio_objetivo_venta(historico, actual=None, ajustes=None, *, unidades=1, ventana_dias=None, ahora=None)`; devuelve además `precio_actual, cantidad_en_oferta, n_lecturas`. `precio_objetivo_compra(historico, actual=None, ajustes=None)`; `estado`: "oportunidad"|"normal"|"caro"|"sin_datos"; devuelve además `mediana, precio_actual, aviso`.
- **[catálogo, 2026-11-02] Ampliaciones compatibles de `data/catalogo.json` y `app/catalogo.py`** (todo lo del contrato está y funciona igual):
  - **`nivel` puede ser 0** (190 recetas, `"tipo": "mejora"`): metabot las etiqueta "Mejora"/"Upgrade"; no tienen curva (`curva: null`). El rango real es 0–100.
  - Facción: 2º dígito del id de receta, `1 = elyos`, `2 = asmodian` (verificado: 129 filas de las tablas de metabot y 81 recetas con ingredientes de facción, 0 contradicciones). No se usa `"ambas"`: las recetas espejo se guardan por separado porque sus productos tienen **ids distintos por facción** (116 nombres de objeto están repetidos con un id por facción). El OCR debe desambiguar nombres con la facción del servidor → `buscar(texto, faccion=...)`.
  - Campos extra en `objetos[id]`: `faccion` ("elyos"|"asmodian"|"ambas"|null, según las recetas que lo usan/producen), `precio_venta_npc` (lo que paga el mercader), `comercio` (texto de metabot: "Comerciable", "No comerciable", "Ligado al alma"…), `tienda_npc`, `recoleccion` (nodo de recolección, si aplica).
  - `comerciable`: true = "Comerciable" (132), false = "No comerciable" (58). **Todo el equipo fabricado (456 objetos) es "Ligado al alma"** (EN "Soul-bound"): no está claro si se puede vender antes de ligarlo, así que va como `null`. Pendiente de confirmar en el juego; el motor no debería descartar esas recetas solo por `null`.
  - Campos extra en `recetas[]`: `tipo` ("normal"|"mejora"). Raíz: `atribucion`, `notas` (list[str]), `evidencia_faccion`, `max_maestria`.
  - `producto_combo`/`cantidad_combo`: **inferidos** (metabot no los publica) solo para equipo: la versión "brillante"/"Splendent" del producto (228 recetas; esos objetos no tienen receta normal). Comida, pociones y piedras (52 recetas con combo) → null. Las 114 versiones brillante de rey dragón además tienen receta "mejora" propia.
  - `app/catalogo.py` extras: `Catalogo.datos/objetos/recetas/curvas/profesiones`, `receta(id)`, `recetas_que_usan(id)`, `buscar(texto, limite=10, faccion=None)` (ids `int`, puntuación 0–100), `prob_exito(receta, nivel) -> float|None` (None = bloqueada; curva null = 1.0), `prob_combo(receta, nivel)` = éxito × combo_pct × éxito combo (cuadra con metabot: 13,51% en el ejemplo de su web). `objeto(id)` devuelve `None` si no existe; `nombre(id)` devuelve `"#id"`. `recetas_de(None)` = todas; acepta alias "Asmodianos", "elios"…
- **[captura, 2026-11-02] Ampliaciones compatibles de `app/captura/`** (las firmas del contrato funcionan igual; todo lo nuevo son kwargs opcionales o claves extra):
  - `FilaMercado` lleva además: `nombre` (nombre oficial del catálogo), `total` (precio total del anuncio si se leyó), `motivos: list[str]` (por qué es dudosa, en español), `caja: [x, y, w, h]` (zona de la fila en la imagen) y, en grabación/vídeo, `recorte` (ruta del PNG de la fila dudosa en `capturas/tmp/revision/`). `precio`/`cantidad` son `int`.
  - **Facción**: como hay nombres repetidos con un id por facción, todas las entradas aceptan `faccion="elyos"|"asmodian"` (la del servidor) y la pasan a `cat.buscar(..., faccion=)`. Sin facción, esas filas salen dudosas con el motivo "existe en las dos facciones". La integración debe pasar la facción del servidor elegido.
  - `ocr.leer_imagen(img, region=None, idioma="es-ES", escala=None, invertir=None, umbral=None)`; extras `ocr.reconocer(img)`, `ocr.preprocesar(img)`, `ocr.idiomas_disponibles()`. Es seguro llamarlo desde hilos y desde código async (bucle propio de winrt; las llamadas se serializan porque un `OcrEngine` no admite dos a la vez).
  - `parser.interpretar_pantalla(lineas, cat, columnas=None, orden_numeros=("precio","cantidad"), faccion=None)`. `cat` puede ser `Catalogo`, el dict de `catalogo.json`, `{id: nombre}` o un `parser.IndiceNombres(cat, faccion)` ya construido (más rápido para muchas pantallas). Extras: `parser.agrupar_libro(filas, incluir_dudosas=False) -> {objeto_id: {ofertas, precio_min, cantidad_total, num_anuncios, nombre}}`, `parser.consolidar(lista_de_filas_por_fotograma)`, `parser.a_lecturas(filas, servidor_id, fuente, fecha=None, incluir_dudosas=False) -> list[Lectura]` (usa `app.db.Lectura`; excluye dudosas por defecto).
  - `grabacion.SesionGrabacion(fps=3, cat=None, region=None, columnas=None, fuente=None, monitor=None, guardar_recortes=True, al_leer=None, idioma="es-ES", faccion=None)`: `.iniciar()`, `.detener() -> list[FilaMercado]` (lanza `RuntimeError` si el hilo falló), `.estado() -> dict` (para sondear desde la interfaz), `.activa`. Extra `grabacion.procesar_imagen(img, cat, region=None, columnas=None, escala=None, faccion=None)` (una captura suelta; la usa también el vigilante).
  - `video.procesar_video(ruta, cat, region=None, columnas=None, fps_muestreo=3, guardar_recortes=True, progreso=None, faccion=None, devolver_estadisticas=False)`.
  - `vigilante.Vigilante(carpeta=None, cat=None, intervalo=2, al_procesar=None, al_error=None, faccion=None)`: `.iniciar()/.detener()/.revisar()/.recoger()/.estado()`. Carpeta: parámetro → variable de entorno `AION2_CARPETA_CAPTURAS` → `capturas/pendientes`. `vigilante.carpetas_steam()` lista las carpetas de capturas de Steam existentes. No reprocesa archivos ya registrados en temporales.
  - `temporales`: además de `registrar_temporal(ruta, ids, tipo=None)`, `limpiar_verificados(repo) -> {borrados, conservados, errores}` y `aplicar_tope(mb=500, repo=None) -> {tamano_mb, tope_mb, excedido, aviso, limpieza}`: `esta_registrado(ruta)`, `registrar_recorte(ruta, fila)`, `recortes_pendientes()`, `marcar_revisado(ruta)`, `limpiar_revisados()`, `configurar(dir_tmp)`. Solo borra si `verificar_lecturas(ids)` devuelve exactamente `True`; una entrada sin ids **no** se borra (aunque `verificar_lecturas([])` devuelva True).
  - `calibracion` (`data/calibracion.json`, por resolución): `configuracion_para(w, h) -> {lista, columnas, escala, calibrada}`, `region_para(w, h)` (pantalla completa si no hay calibración), `guardar_region(w, h, region, columnas=None, escala=None)`, `borrar_region(w, h)`, `resolucion_pantalla()`. `columnas` = `{"nombre"|"precio"|"cantidad"|"total": [x0, x1]}` en píxeles absolutos.
