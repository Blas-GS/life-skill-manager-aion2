# Plan: Life Skill Manager - Aion 2 (herramienta de rentabilidad de artesanía)

## Contexto
Quieres saber, en cada momento, qué recetas de AION 2 (cliente EU en español, ambas facciones) te conviene fabricar comprando los ingredientes en el mercado y vendiendo el producto, teniendo en cuenta tu nivel de artesanía, tu inventario/almacén, las comisiones y la probabilidad de éxito/combo. Hoy tienes un HTML (datos inventados/incompletos, nombres sin verificar, impuesto mal modelado) y un Excel en inglés con ~12 recetas y precios del 09/10/2026. El objetivo es una app local con datos reales, histórico de precios y un panel claro de "mejores oportunidades ahora".

### Hallazgos de la investigación (base del diseño)
- **Recetas**: metabot.gg incrusta en su página de crafteo las **512 recetas del cliente global** como JSON (`self.__next_f`): producto, cantidad, nivel requerido (`mastery`), profesión, ingredientes+cantidades, % combo y curvas de éxito (`curves` c1…c31, índice = niveles por encima de la receta). La versión `/es/` (o `/es_ES/`) da los **nombres oficiales en español** (p.ej. "Mineral de orichalcum", "Okra", "Od", "Esencia de Balaur", "Solomillo wellington de dragón oscuro"). Las páginas de objeto dan precio de tienda NPC y si es comerciable. Piden un enlace de atribución → lo pondremos en la app.
- **Facción**: el 2º dígito del id de receta separa Elyos/Asmodian (256 c/u). Hay que confirmar cuál es cuál con las estaciones (Altgard/Morheim = Asmodian).
- **Profesiones**: Herrería, Armadura, Orfebrería, Alquimia, Cocina. Nivel 1–100 (Principiante 1–50, Especialista 51–100).
- **Mercado**: uno por servidor (cada servidor = una facción). Comisión de registro ≈2% (se paga al listar, no se devuelve) + impuesto de venta ≈10% al liquidar → neto ≈88%. Máx. ~10 anuncios activos. Ambos % serán configurables (el valor real aparece en la ventana del Mercado).
- **Combo**: tras un éxito, 20–30% de probabilidad de combo con su propia curva; da la versión "Espléndida"/mayor cantidad. El Excel asume que un combo fallido pierde todo → configurable.
- **Acceso al juego**: no existe API oficial del mercado. El anticheat (NCGuard) detecta entrada simulada y la política de NC prohíbe leer memoria, modificar el cliente o capturar tráfico (baneo permanente). La opción segura es **captura pasiva de pantalla + OCR**: tú navegas el mercado a mano, la app solo lee imágenes, sin tocar el proceso, la memoria ni la red del juego. Nada de clics/teclas automáticas.
- **Entorno**: Python 3.14.5 en `%LOCALAPPDATA%\Programs\Python\Python314\python.exe` (no está en PATH; el lanzador usará esa ruta). No hay Node ni Git.

## Enfoque: app local Python + base de datos personal en Supabase + panel web en `localhost`

### Arquitectura
```
[Juego AION 2]  ← solo se mira la pantalla, nunca se toca
      │ (vídeo grabado / captura continua pasiva / captura suelta)
      ▼
[App local Python (FastAPI)]  — OCR, emparejado con catálogo, motor de rentabilidad, panel web
      │ HTTPS (clave guardada solo en .env local, nunca en el navegador)
      ▼
[Supabase (Postgres en la nube, plan gratuito)]  — histórico de precios, cantidades, volumen estimado,
                                                    servidores, perfiles, niveles, inventario, ventas propias
```
- **Supabase** es la base de datos personal: el histórico queda en la nube, sobrevive a cambios de PC y permite consultarlo desde cualquier sitio (y en el futuro, ver el panel desde el móvil).
- **Cola local**: si no hay conexión, las lecturas se guardan en `data/pendientes.jsonl` y se suben al reconectar. El catálogo de recetas vive en `data/catalogo.json` (y se sube también a Supabase para poder hacer consultas cruzadas).
- **Configuración**: tú creas el proyecto en supabase.com y pegas la URL y la clave en `.env` (yo no introduzco claves). La app crea las tablas con un script SQL de migración (`supabase/esquema.sql`) que pegas en el editor SQL de Supabase o aplica la app.
- Nota: el plan gratuito pausa el proyecto tras ~1 semana sin uso (se reactiva con un clic) y tiene 500 MB, de sobra para años de histórico.

### Estructura
```
Life Skill Manager - Aion 2/
  iniciar.bat               crea .venv con la ruta de Python 3.14, instala deps, arranca y abre el navegador
  .env                      SUPABASE_URL, SUPABASE_KEY (solo local)
  requirements.txt          fastapi, uvicorn, httpx, supabase, python-dotenv, mss, pillow, opencv-python (o imageio-ffmpeg),
                            winrt-Windows.Media.Ocr (+deps winrt), rapidfuzz, openpyxl, pytest
  supabase/esquema.sql      tablas, índices y vistas (precio diario, percentiles)
  app/
    main.py                 FastAPI: API REST + sirve el frontend
    db.py                   acceso a Supabase + cola local offline
    precio_objetivo.py      precio recomendado de venta/compra a partir del histórico
    catalogo.py             carga data/catalogo.json (objetos, recetas, curvas)
    calculo.py              motor de rentabilidad (núcleo, con tests)
    captura/
      grabacion.py          modo grabación: captura pasiva de pantalla a 2–4 fps mientras navegas el mercado
      video.py              importar un vídeo (OBS / Xbox Game Bar Win+Alt+R): extrae fotogramas, descarta repetidos
      vigilante.py          vigila carpeta de capturas sueltas (Steam F12 / Impr Pant)
      temporales.py         borrado de imágenes/vídeos tras verificar el guardado en Supabase; limpieza y tope de tamaño
      ocr.py                Windows.Media.Ocr (es-ES), recorte/escala/umbral por región calibrada
      parser.py             filas → (objeto por coincidencia difusa con catálogo ES, precio, cantidad)
    static/ index.html, app.js, estilos.css   (SPA vanilla JS + Chart.js por CDN; estilo oscuro como el HTML actual)
  tools/
    importar_metabot.py     descarga /es/ y /en/ de metabot, parsea el payload → data/catalogo.json
    importar_excel.py       siembra precios del Excel (nombres EN → id) como histórico inicial del 09/10/2026
  data/catalogo.json, data/aion2.db, capturas/
  tests/test_calculo.py, tests/test_parser.py
```

### Datos (Supabase / Postgres)
- `servidores` (nombre, facción, región, comisión registro %, impuesto venta %) — cada servidor tiene su mercado.
- `perfiles` (personaje, servidor) → para jugar ambas facciones con precios separados.
- `objetos`, `recetas`, `receta_ingredientes`, `curvas` — catálogo (copia de `catalogo.json`).
- `lecturas_mercado` (servidor, objeto, fecha, precio_mín, cantidad total en oferta, nº anuncios, fuente: video/grabación/captura/manual/excel, id de sesión de lectura).
- `ofertas` (lectura, precio, cantidad) — el libro de ofertas completo de cada lectura.
- `ventas_propias` / `compras_propias` (perfil, objeto, cantidad, precio, fecha) — tus operaciones reales (desde la pestaña de liquidación), para medir tu beneficio real frente al estimado.
- `niveles` (perfil, profesión, nivel), `inventario` (perfil, objeto, cantidad, ubicación: inventario/almacén).
- `precios_npc` (objeto, precio) — sembrado desde metabot, editable.
- `ajustes` (rebaja al listar, regla de combo fallido, valorar inventario a precio de mercado o a coste 0).
- Vistas: `precio_diario` (mín/medio/percentiles por día), `volumen_estimado` (caídas de cantidad en oferta entre lecturas = unidades probablemente vendidas).

### Motor de rentabilidad (`calculo.py`)
1. **Coste de adquisición** de cada objeto = mínimo entre: comprar en mercado (último precio, con antigüedad), tienda NPC (objetos vinculados), o **fabricarlo** con la mejor receta desbloqueada (recursivo, memoizado, con protección de ciclos). Así detecta cadenas tipo "comprar mineral → lingote → arma" vs "comprar lingote".
2. **Probabilidades**: `p_éxito = curva[min(nivel − nivel_receta, len−1)]`; combo: `p_éxito × %combo × curva_combo`. Resultado esperado por intento = cantidad base × P(éxito sin combo) + producto combo × P(combo ok) (+ regla configurable si el combo falla).
3. **Venta neta** = precio de venta × (1 − 2% − 10%), precio de venta = mínimo actual − rebaja configurable.
4. **Métricas por receta**: coste/intento, ingreso esperado, beneficio/intento, margen %, precio de equilibrio, beneficio con N intentos.
5. **Profundidad de mercado**: con el libro de ofertas capturado, calcula cuántos intentos puedes hacer comprando por tramos de precio (el coste sube al agotar las ofertas baratas) y avisa de saturación del producto (muchos anuncios) y del límite de 10 anuncios.
6. **Inventario**: descuenta lo que ya tienes; "puedes hacer X ya, te faltan Y (coste Z)".

### Precio objetivo (`precio_objetivo.py`)
- **Precio de venta recomendado** por objeto, usando el histórico del servidor (últimos 7/30 días):
  - Rango "normal" = percentiles P25–P75 del precio mínimo; velocidad de venta = volumen estimado/día.
  - Si el precio actual está dentro o por encima del rango → listar justo por debajo del más barato (rebaja configurable).
  - Si el precio actual está anormalmente bajo (< P25, alguien está "tirando" precios) → recomendar listar en torno a la mediana y esperar, o no fabricar todavía; se muestra el aviso.
  - Si hay muchas unidades en oferta frente a lo que se vende al día → aviso de saturación y precio más agresivo.
  - Muestra también el tiempo estimado para vender tus unidades a ese precio.
- **Precio de compra objetivo** de ingredientes: "compra por debajo de X" (≈P25), con alerta cuando una lectura lo cumpla.
- El panel calcula el beneficio con dos escenarios: **vender ya** (precio actual) y **vender a precio objetivo**.

### Pantallas (español)
1. **Panel** (principal): tabla "Mejores oportunidades ahora", solo recetas desbloqueadas por tu nivel. Columnas: receta, profesión, beneficio/intento, margen %, nº intentos recomendados, inversión, beneficio total esperado, antigüedad de los precios (semáforo), botón "lista de la compra". Filtros: profesión, inversión máxima, margen mínimo, incluir intermedios.
2. **Mercado**: buscador de objetos, último precio/cantidad, gráfico histórico (precio mín. y cantidad en oferta), volumen estimado (caídas de cantidad entre capturas), entrada manual rápida.
3. **Captura**: estado del vigilante, última imagen con las filas reconocidas para confirmar/corregir antes de guardar, calibración de la región de la lista (una vez por resolución).
4. **Recetas**: explorador con árbol de ingredientes, cadena "comprar vs fabricar" y calculadora detallada.
5. **Personaje**: perfiles, niveles de las 5 profesiones, inventario/almacén (edición rápida y pegado de texto "nombre: cantidad").
6. **Ajustes**: comisiones, reglas de combo, precios NPC, importar/exportar JSON, atribución a metabot.gg.

### Lectura de precios del juego (solo lectura, sin tocar el juego)
Tú navegas el mercado con tu ratón y teclado; la app **solo mira la pantalla**. Tres formas, de más a menos cómoda:
1. **Modo grabación (recomendado)**: pulsas "Empezar lectura" en la app, recorres las pestañas/categorías del mercado a tu ritmo y pulsas "Terminar". La app captura la pantalla 2–4 veces por segundo, descarta fotogramas repetidos, hace OCR de cada pantalla distinta y junta todo en una sesión de lectura (un recorrido completo ≈ unos minutos).
2. **Importar vídeo**: grabas con OBS o la Xbox Game Bar (Win+Alt+R) mientras recorres el mercado y arrastras el vídeo a la app; hace lo mismo con los fotogramas del vídeo.
3. **Captura suelta**: F12 de Steam / Impr Pant para un objeto concreto.
En todos los casos: recorte de la zona calibrada → OCR de Windows en español → emparejado del nombre con el catálogo (coincidencia difusa) → precios/cantidades. Pantalla de revisión con las filas dudosas resaltadas antes de guardar en Supabase.
- Requisito una vez: instalar el paquete de OCR en español de Windows (comando de administrador que te daré; `Get-WindowsCapability ... Language.OCR~~~es-ES`). Los números son lo crítico y el OCR en inglés también sirve para ellos.
- Alternativa de respaldo: dejar capturas en `capturas/pendientes` y pedirme en Claude Code que las lea (yo veo imágenes) y las cargue.
- **Sin acumulación de imágenes** (`captura/temporales.py`):
  - Modo grabación: los fotogramas se procesan **en memoria** y nunca se escriben en disco; solo se guarda en `capturas/tmp/` el recorte pequeño de una fila dudosa mientras esperas para revisarla.
  - Vídeos y capturas sueltas: se procesan, se guardan las lecturas en Supabase, la app **vuelve a leer esas filas de Supabase para verificar** que están completas y solo entonces borra el archivo. Si la subida falla, el archivo se conserva hasta el siguiente intento correcto (sin conexión los datos van a la cola local; el archivo se borra cuando la cola se haya subido y verificado).
  - Al arrancar, la app limpia los temporales huérfanos ya verificados y aplica un tope de tamaño de `capturas/tmp/` (p.ej. 500 MB), avisando si se supera.
  - En Supabase solo se guardan números y nombres, nunca imágenes.
- **Por qué no te propongo que yo (o la app) controle el juego directamente**: para recorrer las pestañas habría que enviar clics/teclas simuladas al juego. El anticheat de AION 2 (NCGuard) detecta la entrada virtual y el EULA prohíbe el acceso automatizado; NC banea de forma permanente la cuenta (en todos sus juegos). Por eso la navegación la haces tú y la automatización empieza en la imagen. Fuera de alcance también: leer memoria, capturar tráfico de red o modificar el cliente.

## Fases de implementación
1. **Catálogo**: `tools/importar_metabot.py` → `catalogo.json` (512 recetas, nombres ES/EN, curvas, facción, precios NPC de vinculados, comerciable sí/no). Verificar mapeo de facción y producto de combo inspeccionando el payload real.
2. **Supabase + motor**: `esquema.sql`, `db.py` (con cola offline), `calculo.py` con tests que reproduzcan las cifras del Excel (p.ej. Okra frita: coste 8.864, equilibrio ≈8.899 con las mismas probabilidades). Necesita que crees el proyecto en Supabase y rellenes `.env`.
3. **API + panel web** (Panel, Recetas, Personaje, Mercado con entrada manual, Ajustes). Siembra de precios del Excel.
4. **Lectura del mercado**: captura suelta → modo grabación → importar vídeo; calibración, revisión y guardado.
5. **Precio objetivo + pulido**: percentiles, volumen estimado, escenarios vender ya / a precio objetivo, gráficos, lista de la compra, alertas, `iniciar.bat`.

## Verificación
- `pytest`: motor de cálculo contra los valores del Excel; curvas/combos con casos conocidos de metabot; parser OCR con capturas de ejemplo; precio objetivo con históricos sintéticos (normal, precio hundido, saturación).
- Supabase: insertar una sesión de lectura, cortar la conexión y comprobar que la cola local se sube al reconectar.
- Temporales: tras procesar un vídeo y una captura, comprobar que los archivos desaparecen solo después de verificar las filas en Supabase, y que con la conexión cortada se conservan hasta la subida.
- Arrancar con `iniciar.bat`, abrir `http://localhost:8000` en el navegador integrado y comprobar: nombres en español, recetas filtradas por facción y nivel, panel ordenado por beneficio, histórico tras introducir precios.
- OCR: con tu primera grabación/vídeo real del Mercado, comparar valores leídos vs pantalla y ajustar recortes y deduplicado; si fallan muchas, recalibrar.
- Revisar con algunas recetas en el juego (nivel requerido, ingredientes) las que metabot marque dudosas.
