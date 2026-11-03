# Plan: Life Skill Manager - Aion 2 (crafting profitability tool)

## Context
You want to know, at any moment, which AION 2 recipes (EU client in Spanish, both factions) are worth crafting by buying the ingredients on the market and selling the product, taking into account your crafting level, your inventory/warehouse, the fees and the success/combo probability. Today you have an HTML file (made-up/incomplete data, unverified names, wrongly modeled tax) and an Excel file in English with ~12 recipes and prices from 09/10/2026. The goal is a local app with real data, price history and a clear "best opportunities right now" dashboard.

### Research findings (basis of the design)
- **Recipes**: metabot.gg embeds in its crafting page the **512 recipes of the global client** as JSON (`self.__next_f`): product, quantity, required level (`mastery`), profession, ingredients+quantities, combo % and success curves (`curves` c1…c31, index = levels above the recipe). The `/es/` (or `/es_ES/`) version gives the **official Spanish names** (e.g. "Mineral de orichalcum", "Okra", "Od", "Esencia de Balaur", "Solomillo wellington de dragón oscuro"). Item pages give the NPC shop price and whether the item is tradeable. They ask for an attribution link → we will put it in the app.
- **Faction**: the 2nd digit of the recipe id separates Elyos/Asmodian (256 each). Which is which must be confirmed with the stations (Altgard/Morheim = Asmodian).
- **Professions**: Herrería (Weaponsmithing), Armadura (Armorsmithing), Orfebrería (Jewelcrafting), Alquimia (Alchemy), Cocina (Cooking). Level 1–100 (Beginner 1–50, Specialist 51–100).
- **Market**: one per server (each server = one faction). Listing fee ≈2% (paid when listing, not refunded) + sales tax ≈10% on settlement → net ≈88%. Max. ~10 active listings. Both % will be configurable (the real value is shown in the Market window).
- **Combo**: after a success, 20–30% chance of a combo with its own curve; it gives the "Espléndida" (Splendent) version/a larger quantity. The Excel file assumes a failed combo loses everything → configurable.
- **Game access**: there is no official market API. The anti-cheat (NCGuard) detects simulated input and NC's policy forbids reading memory, modifying the client or capturing traffic (permanent ban). The safe option is **passive screen capture + OCR**: you browse the market by hand, the app only reads images, without touching the game's process, memory or network. No automatic clicks/keys.
- **Environment**: Python 3.14.5 at `%LOCALAPPDATA%\Programs\Python\Python314\python.exe` (not on PATH; the launcher will use that path). No Node or Git.

## Approach: local Python app + personal Supabase database + web dashboard on `localhost`

### Architecture
```
[AION 2 game]  ← the screen is only looked at, never touched
      │ (recorded video / continuous passive capture / single screenshot)
      ▼
[Local Python app (FastAPI)]  — OCR, catalog matching, profitability engine, web dashboard
      │ HTTPS (key stored only in the local .env, never in the browser)
      ▼
[Supabase (cloud Postgres, free plan)]  — price history, quantities, estimated volume,
                                          servers, profiles, levels, inventory, own sales
```
- **Supabase** is the personal database: the history stays in the cloud, survives PC changes and can be queried from anywhere (and in the future, the dashboard could be viewed from a phone).
- **Local queue**: if there is no connection, readings are saved to `data/pendientes.jsonl` and uploaded on reconnect. The recipe catalog lives in `data/catalogo.json` (and is also uploaded to Supabase to allow cross queries).
- **Configuration**: you create the project on supabase.com and paste the URL and key into `.env` (I don't enter keys). The app creates the tables with an SQL migration script (`supabase/esquema.sql`) that you paste into the Supabase SQL editor or the app applies.
- Note: the free plan pauses the project after ~1 week without use (reactivated with one click) and has 500 MB, more than enough for years of history.

### Structure
```
Life Skill Manager - Aion 2/
  iniciar.bat               creates .venv with the Python 3.14 path, installs deps, starts the app and opens the browser
  .env                      SUPABASE_URL, SUPABASE_KEY (local only)
  requirements.txt          fastapi, uvicorn, httpx, supabase, python-dotenv, mss, pillow, opencv-python (or imageio-ffmpeg),
                            winrt-Windows.Media.Ocr (+winrt deps), rapidfuzz, openpyxl, pytest
  supabase/esquema.sql      tables, indexes and views (daily price, percentiles)
  app/
    main.py                 FastAPI: REST API + serves the frontend
    db.py                   Supabase access + local offline queue
    precio_objetivo.py      recommended sell/buy price from the history
    catalogo.py             loads data/catalogo.json (items, recipes, curves)
    calculo.py              profitability engine (core, with tests)
    captura/
      grabacion.py          recording mode: passive screen capture at 2–4 fps while you browse the market
      video.py              import a video (OBS / Xbox Game Bar Win+Alt+R): extracts frames, discards repeats
      vigilante.py          watches a folder of loose screenshots (Steam F12 / Print Screen)
      temporales.py         deletes images/videos after verifying the save in Supabase; cleanup and size cap
      ocr.py                Windows.Media.Ocr (es-ES), crop/scale/threshold per calibrated region
      parser.py             rows → (item via fuzzy match against the ES catalog, price, quantity)
    static/ index.html, app.js, estilos.css   (vanilla JS SPA + Chart.js from a CDN; dark style like the current HTML)
  tools/
    importar_metabot.py     downloads /es/ and /en/ from metabot, parses the payload → data/catalogo.json
    importar_excel.py       seeds prices from the Excel file (EN names → id) as the initial history of 09/10/2026
  data/catalogo.json, data/aion2.db, capturas/
  tests/test_calculo.py, tests/test_parser.py
```

### Data (Supabase / Postgres)
- `servidores` (name, faction, region, listing fee %, sales tax %) — each server has its own market.
- `perfiles` (character, server) → to play both factions with separate prices.
- `objetos`, `recetas`, `receta_ingredientes`, `curvas` — catalog (copy of `catalogo.json`).
- `lecturas_mercado` (server, item, date, min price, total quantity on offer, number of listings, source: video/recording/screenshot/manual/excel, reading session id).
- `ofertas` (reading, price, quantity) — the full order book of each reading.
- `ventas_propias` / `compras_propias` (profile, item, quantity, price, date) — your real operations (from the settlement tab), to measure your real profit against the estimate.
- `niveles` (profile, profession, level), `inventario` (profile, item, quantity, location: inventory/warehouse).
- `precios_npc` (item, price) — seeded from metabot, editable.
- `ajustes` (listing undercut, failed-combo rule, value inventory at market price or at cost 0).
- Views: `precio_diario` (min/mean/percentiles per day), `volumen_estimado` (drops in quantity on offer between readings = units probably sold).

### Profitability engine (`calculo.py`)
1. **Acquisition cost** of each item = minimum of: buying on the market (latest price, with its age), NPC shop (bound items), or **crafting it** with the best unlocked recipe (recursive, memoized, with cycle protection). This way it detects chains like "buy ore → ingot → weapon" vs "buy ingot".
2. **Probabilities**: `p_éxito = curva[min(nivel − nivel_receta, len−1)]`; combo: `p_éxito × %combo × curva_combo`. Expected result per attempt = base quantity × P(success without combo) + combo product × P(combo ok) (+ configurable rule if the combo fails).
3. **Net sale** = sell price × (1 − 2% − 10%), sell price = current minimum − configurable undercut.
4. **Per-recipe metrics**: cost/attempt, expected income, profit/attempt, margin %, break-even price, profit with N attempts.
5. **Market depth**: with the captured order book, it calculates how many attempts you can make buying through price tiers (the cost rises as the cheap offers run out) and warns about product saturation (many listings) and the 10-listing limit.
6. **Inventory**: subtracts what you already have; "you can make X now, you're missing Y (cost Z)".

### Target price (`precio_objetivo.py`)
- **Recommended sell price** per item, using the server's history (last 7/30 days):
  - "Normal" range = P25–P75 percentiles of the minimum price; sales speed = estimated volume/day.
  - If the current price is within or above the range → list just below the cheapest listing (configurable undercut).
  - If the current price is abnormally low (< P25, someone is "dumping" prices) → recommend listing around the median and waiting, or not crafting yet; a warning is shown.
  - If there are many units on offer compared with daily sales → saturation warning and a more aggressive price.
  - It also shows the estimated time to sell your units at that price.
- **Target buy price** for ingredients: "buy below X" (≈P25), with an alert when a reading meets it.
- The dashboard calculates profit under two scenarios: **sell now** (current price) and **sell at target price**.

### Screens (Spanish)
1. **Dashboard** (main): "Best opportunities right now" table, only recipes unlocked at your level. Columns: recipe, profession, profit/attempt, margin %, recommended attempts, investment, total expected profit, price age (traffic light), "shopping list" button. Filters: profession, maximum investment, minimum margin, include intermediates.
2. **Market**: item search, latest price/quantity, history chart (min price and quantity on offer), estimated volume (drops in quantity between captures), quick manual entry.
3. **Capture**: watcher status, latest image with the recognized rows to confirm/correct before saving, calibration of the list region (once per resolution).
4. **Recipes**: explorer with ingredient tree, "buy vs craft" chain and detailed calculator.
5. **Character**: profiles, levels of the 5 professions, inventory/warehouse (quick editing and pasting "name: quantity" text).
6. **Settings**: fees, combo rules, NPC prices, JSON import/export, attribution to metabot.gg.

### Reading prices from the game (read-only, without touching the game)
You browse the market with your mouse and keyboard; the app **only looks at the screen**. Three ways, from most to least convenient:
1. **Recording mode (recommended)**: you press "Empezar lectura" (Start reading) in the app, go through the market tabs/categories at your own pace and press "Terminar" (Finish). The app captures the screen 2–4 times per second, discards repeated frames, runs OCR on each distinct screen and merges everything into one reading session (a full pass ≈ a few minutes).
2. **Import video**: you record with OBS or the Xbox Game Bar (Win+Alt+R) while browsing the market and drag the video into the app; it does the same with the video's frames.
3. **Single screenshot**: Steam F12 / Print Screen for a specific item.
In every case: crop of the calibrated area → Windows OCR in Spanish → matching the name against the catalog (fuzzy match) → prices/quantities. A review screen highlights doubtful rows before saving to Supabase.
- One-time requirement: install the Windows Spanish OCR package (an administrator command I will give you; `Get-WindowsCapability ... Language.OCR~~~es-ES`). Numbers are what matters most and the English OCR also works for them.
- Fallback alternative: leave screenshots in `capturas/pendientes` and ask me in Claude Code to read them (I can see images) and load them.
- **No image buildup** (`captura/temporales.py`):
  - Recording mode: frames are processed **in memory** and never written to disk; only the small crop of a doubtful row is saved in `capturas/tmp/` while it waits for your review.
  - Videos and single screenshots: they are processed, the readings are saved to Supabase, the app **reads those rows back from Supabase to verify** they are complete and only then deletes the file. If the upload fails, the file is kept until the next successful attempt (without a connection the data goes to the local queue; the file is deleted once the queue has been uploaded and verified).
  - On startup, the app cleans up orphaned temporary files that are already verified and applies a size cap to `capturas/tmp/` (e.g. 500 MB), warning if it is exceeded.
  - Only numbers and names are stored in Supabase, never images.
- **Why I don't suggest that I (or the app) control the game directly**: going through the tabs would require sending simulated clicks/keys to the game. AION 2's anti-cheat (NCGuard) detects virtual input and the EULA forbids automated access; NC permanently bans the account (across all its games). That is why you do the browsing and the automation starts at the image. Also out of scope: reading memory, capturing network traffic or modifying the client.

## Implementation phases
1. **Catalog**: `tools/importar_metabot.py` → `catalogo.json` (512 recipes, ES/EN names, curves, faction, NPC prices of bound items, tradeable yes/no). Verify the faction mapping and the combo product by inspecting the real payload.
2. **Supabase + engine**: `esquema.sql`, `db.py` (with offline queue), `calculo.py` with tests that reproduce the Excel figures (e.g. Okra frita: cost 8,864, break-even ≈8,899 with the same probabilities). Requires you to create the Supabase project and fill in `.env`.
3. **API + web dashboard** (Dashboard, Recipes, Character, Market with manual entry, Settings). Seeding prices from the Excel file.
4. **Market reading**: single screenshot → recording mode → video import; calibration, review and saving.
5. **Target price + polish**: percentiles, estimated volume, sell now / at target price scenarios, charts, shopping list, alerts, `iniciar.bat`.

## Verification
- `pytest`: calculation engine against the Excel values; curves/combos with known metabot cases; OCR parser with sample screenshots; target price with synthetic histories (normal, crashed price, saturation).
- Supabase: insert a reading session, cut the connection and check that the local queue uploads on reconnect.
- Temporary files: after processing a video and a screenshot, check that the files disappear only after the rows are verified in Supabase, and that with the connection cut they are kept until the upload.
- Start with `iniciar.bat`, open `http://localhost:8000` in the built-in browser and check: Spanish names, recipes filtered by faction and level, dashboard sorted by profit, history after entering prices.
- OCR: with your first real recording/video of the Market, compare read values vs the screen and adjust crops and deduplication; if many fail, recalibrate.
- Check in the game (required level, ingredients) a few of the recipes that metabot marks as doubtful.
