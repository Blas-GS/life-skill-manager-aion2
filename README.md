# AION 2 · Artesanía rentable

Herramienta local para saber **qué recetas de artesanía de AION 2 te conviene fabricar ahora**, comprando los ingredientes en el mercado de tu servidor y vendiendo el producto. Tiene en cuenta tus niveles de las 5 profesiones, tu inventario/almacén, la comisión de registro e impuesto de venta, la probabilidad de éxito y de combo, la profundidad del mercado y el histórico de precios.

Pestañas: **Panel** (mejores oportunidades, lista de la compra), **Mercado** (precios, histórico, precio objetivo, entrada manual), **Captura** (lectura pasiva del mercado por OCR), **Recetas** (árbol de ingredientes, comprar o fabricar), **Personaje** (perfiles, servidores, niveles, inventario) y **Ajustes**.

## Arrancar

Doble clic en **`iniciar.bat`**. La primera vez crea el entorno de Python (`.venv`, con Python 3.14) e instala las dependencias; después arranca la app y abre `http://localhost:8000`.

A mano:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Primeros pasos:
1. **Personaje** → crea tu servidor (nombre y facción) y tu perfil; pon tus niveles.
2. Siembra precios: lee el mercado (**Captura**), apúntalos a mano (**Mercado**) o importa el Excel:

```bash
.\.venv\Scripts\python.exe tools\importar_excel.py --servidor <id_del_servidor>
```

   (`--simular` muestra el informe sin guardar. Los precios quedan con fecha 09/10/2026.)
3. **Panel** → recetas ordenadas por beneficio.

El catálogo de recetas (`data/catalogo.json`) **no viene en el repositorio**: `iniciar.bat` lo genera la primera vez con `tools\importar_metabot.py`, que lo descarga de metabot.gg a un ritmo pausado (una petición cada 2 s, con caché para no repetir). Tarda unos minutos.

## Base de datos: tu propio Supabase (o local)

**Cada persona usa su propia base de datos.** Este repositorio no incluye ni comparte ninguna base de datos, URL ni clave: tus precios, tu inventario y tu histórico van a **tu** cuenta de Supabase, y nadie más los ve.

- **Sin configurar nada**, todo se guarda en tu PC, en `data/aion2.db` (SQLite). Funciona igual, pero el histórico no sale de ese equipo.
- **Con Supabase** (gratis), el histórico queda en la nube y sobrevive a un cambio de PC. Una sola vez:
  1. Crea una cuenta en [supabase.com](https://supabase.com) y un proyecto nuevo (plan **Free**, región **Central EU (Frankfurt)** o la más cercana).
  2. En tu proyecto: **SQL Editor → New query**, pega todo [`supabase/esquema.sql`](supabase/esquema.sql) y pulsa **Run**. Crea las tablas con acceso bloqueado para las claves públicas.
  3. `iniciar.bat` crea un archivo `.env` a partir de [`.env.example`](.env.example). Ábrelo y pon:
     - `SUPABASE_URL=` la **Project URL** de tu proyecto (`https://<tu-proyecto>.supabase.co`).
     - `SUPABASE_KEY=` tu clave **secreta** (`sb_secret_...`, en **Project Settings → API Keys**).
  4. Reinicia la app. En **Ajustes** debe poner "Base de datos: Supabase".

Guía detallada, seguridad y qué hacer si el proyecto se pausa: [docs/supabase.md](docs/supabase.md).

> `.env` está en `.gitignore`: **nunca** lo subas a GitHub ni compartas tu clave secreta. Solo la usa el programa en tu PC; nunca llega al navegador.

Sin conexión, las lecturas se guardan en una cola (`data/pendientes.jsonl`) y se suben solas al volver.

## Leer el mercado sin riesgo de baneo

AION 2 tiene anticheat (NCGuard) y NCSOFT prohíbe la automatización. Por eso **la app nunca toca el juego**: no envía clics ni teclas, no lee su memoria, no modifica el cliente ni captura su tráfico de red. Solo mira la pantalla, igual que una grabación de vídeo:

- **Modo grabación**: pulsa *Empezar lectura*, recorre tú el mercado con ratón y teclado, y pulsa *Terminar*. Los fotogramas se procesan en memoria.
- **Vídeo**: graba con OBS o la Xbox Game Bar (Win+Alt+R) y arrástralo a *Captura*.
- **Captura suelta**: F12 de Steam o Impr Pant, y súbela.

Calibra una vez la zona de la lista (pestaña *Captura*) y revisa las filas dudosas antes de guardar. Los vídeos y capturas se borran solos cuando sus datos están guardados y verificados.

## Pruebas

```bash
.\.venv\Scripts\python.exe -m pytest
```

## Aviso legal

- **Herramienta no oficial.** No está afiliada, patrocinada ni aprobada por NCSOFT. AION y AION 2 son marcas de NCSOFT Corporation; se nombran solo para indicar con qué juego funciona.
- **No automatiza el juego.** No envía entradas, no lee ni modifica la memoria o los archivos del cliente, no intercepta su tráfico de red y no elude el anticheat. Solo procesa imágenes de tu propia pantalla que tú generas navegando el mercado a mano.
- **Úsala bajo tu responsabilidad.** Las normas de NCSOFT sobre programas de terceros pueden cambiar y no publican una lista de herramientas permitidas. Revisa sus condiciones antes de usarla; el autor no se hace responsable de sanciones sobre tu cuenta.
- **Sin garantías.** Los cálculos de rentabilidad son estimaciones; ver [LICENSE](LICENSE).
- **Uso personal y sin ánimo de lucro.** No vende datos ni servicios, ni comercia con dinero real.
- **Datos del juego.** Los nombres de objetos, recetas y probabilidades pertenecen a NCSOFT. Este repositorio no los redistribuye: cada usuario genera su catálogo en local.

## Atribución

Datos de recetas, objetos y curvas de éxito: [MetaBot.GG — AION 2 Crafting](https://metabot.gg/es_ES/aion-2/crafting), según su [condición de atribución](https://metabot.gg/en/ai). Las condiciones de uso de metabot.gg ([Terms of Service](https://metabot.gg/en/legal/terms-of-service)) permiten el uso personal y no comercial.

## Licencia

Código bajo licencia [MIT](LICENSE). La licencia no cubre los datos del juego ni los de metabot.gg.
