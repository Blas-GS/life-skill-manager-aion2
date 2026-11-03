"""Imports the AION 2 recipe catalog from metabot.gg and generates data/catalogo.json.

Data source: https://metabot.gg/es_ES/aion-2/crafting (attribution requested at
https://metabot.gg/llms.txt). The page embeds in its Next.js payload
(`self.__next_f`) an object with `recipes`, `items`, `gather`, `curves` and `maxMastery`.

Usage:
    .\\.venv\\Scripts\\python.exe tools\\importar_metabot.py              # recipes + ingredient pages
    .\\.venv\\Scripts\\python.exe tools\\importar_metabot.py --productos  # also product pages (tradeable)
    .\\.venv\\Scripts\\python.exe tools\\importar_metabot.py --sin-objetos  # recipes only (no item pages)
    .\\.venv\\Scripts\\python.exe tools\\importar_metabot.py --refrescar  # ignore the cache

All downloads are stored compressed in data/cache_metabot/ and are not repeated.

Decisions (see also "notas" inside the catalog):
- Faction: 2nd digit of the recipe id. 1 = Elyos, 2 = Asmodian. Verified against the
  "Elyos"/"Asmodianos" labels in metabot's tables and against faction ingredients.
  Mirror recipes are kept separate ("ambas" is not used) because their products
  have different ids per faction.
- Combo: metabot doesn't publish the combo product. For equipment the "brillante"
  (EN "Splendent") version of the product is inferred; it exists as an item without
  a normal recipe. For food, potions and stones it cannot be known → null.
- Recipes with mastery 0 (no curve of their own): metabot labels them "Mejora"/"Upgrade";
  they are saved with nivel 0 and "tipo": "mejora".
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import html as html_mod
import json
import re
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "data" / "cache_metabot"
SALIDA = RAIZ / "data" / "catalogo.json"

BASE = "https://metabot.gg"
URL_CRAFTEO = {"es": f"{BASE}/es_ES/aion-2/crafting", "en": f"{BASE}/en/aion-2/crafting"}
ATRIBUCION = "Datos de recetas y objetos: MetaBot.GG (https://metabot.gg/es_ES/aion-2/crafting) — https://metabot.gg/llms.txt"
VERSION_POR_DEFECTO = "0.0.4387.0"

# We identify ourselves as what we are (not as a browser): a personal tool
# that downloads the catalog once, pausing between requests and caching locally.
CABECERAS = {
    "User-Agent": "life-skill-manager-aion2/0.1 (personal non-commercial crafting calculator; "
    "1 request every 2s, cached; credits metabot.gg)",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

PROFESIONES = {
    "herreria": "Herrería",
    "armadura": "Armadura",
    "orfebreria": "Orfebrería",
    "alquimia": "Alquimia",
    "cocina": "Cocina",
}
# Categories as they come from metabot (ES and EN) → profession key.
CATEGORIAS = {
    "herreria": "herreria", "weaponsmithing": "herreria",
    "armadura": "armadura", "armorsmithing": "armadura",
    "orfebreria": "orfebreria", "handicrafting": "orfebreria",
    "alquimia": "alquimia", "alchemy": "alquimia",
    "cocina": "cocina", "cooking": "cocina",
}
FACCION_POR_DIGITO = {"1": "elyos", "2": "asmodian"}

# Faction-specific ingredients (to verify the faction digit).
INGREDIENTES_FACCION = {
    "yggdrasil": "elyos", "aria": "elyos", "targena": "elyos", "inina": "elyos",
    "asvata": "asmodian", "azpha": "asmodian", "okra": "asmodian", "pujery": "asmodian",
    "conide": "asmodian", "morfa": "asmodian", "raydam": "asmodian",
}


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Cached download
# ---------------------------------------------------------------------------
class Descargador:
    def __init__(self, pausa: float = 2.0, refrescar: bool = False):
        self.pausa = pausa
        self.refrescar = refrescar
        self._ultima = 0.0
        self._cliente: httpx.Client | None = None
        self.descargas = 0

    def _cliente_http(self) -> httpx.Client:
        if self._cliente is None:
            self._cliente = httpx.Client(headers=CABECERAS, follow_redirects=True, timeout=60)
        return self._cliente

    def obtener(self, url: str, archivo_cache: Path, transformar=None) -> str | None:
        """Returns the text of `url`, using `archivo_cache` (.gz) if it exists.

        `transformar(html) -> str` lets you store only the useful part of the page.
        Returns None if the page does not exist (404).
        """
        if archivo_cache.exists() and not self.refrescar:
            return gzip.decompress(archivo_cache.read_bytes()).decode("utf-8")
        espera = self.pausa - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        texto = None
        for intento in range(4):
            self._ultima = time.monotonic()
            try:
                r = self._cliente_http().get(url)
            except httpx.HTTPError as e:
                log(f"  ! network error on {url}: {e}; retrying")
                time.sleep(5 * (intento + 1))
                continue
            if r.status_code == 404:
                log(f"  ! 404 on {url}")
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                log(f"  ! HTTP {r.status_code} on {url}; retrying")
                time.sleep(10 * (intento + 1))
                continue
            r.raise_for_status()
            texto = r.text
            break
        if texto is None:
            raise RuntimeError(f"Could not download {url}")
        self.descargas += 1
        if transformar:
            texto = transformar(texto)
        archivo_cache.parent.mkdir(parents=True, exist_ok=True)
        archivo_cache.write_bytes(gzip.compress(texto.encode("utf-8")))
        return texto

    def cerrar(self):
        if self._cliente:
            self._cliente.close()


# ---------------------------------------------------------------------------
# Crafting page: Next.js payload
# ---------------------------------------------------------------------------
def extraer_flight(html: str) -> str:
    """Concatenates the strings of all `self.__next_f.push([1, "..."])` calls."""
    partes = []
    for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            partes.append(arr[1])
    return "".join(partes)


def _buscar_objeto(o):
    if isinstance(o, dict):
        if "recipes" in o and "curves" in o and "items" in o:
            return o
        valores = o.values()
    elif isinstance(o, list):
        valores = o
    else:
        return None
    for v in valores:
        encontrado = _buscar_objeto(v)
        if encontrado is not None:
            return encontrado
    return None


def extraer_datos_crafteo(html: str) -> dict:
    flight = extraer_flight(html)
    for linea in flight.split("\n"):
        m = re.match(r"^([0-9a-f]+):(.*)$", linea)
        if not m or '"maxMastery"' not in linea:
            continue
        try:
            datos = _buscar_objeto(json.loads(m.group(2)))
        except json.JSONDecodeError:
            continue
        if datos:
            return datos
    raise RuntimeError("Recipe block not found in the metabot page (did the format change?)")


def cuerpo_html(html: str) -> str:
    """HTML rendered before the payload scripts."""
    i = html.find("self.__next_f")
    return html[:i] if i > 0 else html


def texto_plano(html: str) -> str:
    cuerpo = cuerpo_html(html)
    t = re.sub(r"<script.*?</script>", " ", cuerpo, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "|", t)
    t = html_mod.unescape(t)
    return re.sub(r"\|[\s|]*", " | ", t)


def filas_tablas_faccion(html_es: str) -> list[dict]:
    """Rows of the per-profession tables of the ES page: product, faction label,
    mastery and visible ingredients."""
    filas = []
    for fila in re.findall(r'<tr><th scope="row">(.*?)</tr>', cuerpo_html(html_es), re.S):
        slug = re.search(r'href="/es_ES/aion-2/items/([^"]+)"', fila)
        chip = re.search(r'_chip"[^>]*>([^<]+)<', fila)
        maestria = re.search(r'_numC">([^<]+)<', fila)
        if not (slug and chip and maestria):
            continue
        mats = re.findall(r'_mat">(?:<b>(\d+)<!-- -->×</b>)?.*?<span style="color:[^"]+">([^<]+)</span>', fila, re.S)
        filas.append({
            "slug": slug.group(1),
            "faccion": chip.group(1).strip(),
            "maestria": int(maestria.group(1)) if maestria.group(1).isdigit() else 0,
            "mats": [(html_mod.unescape(n), int(q) if q else 1) for q, n in mats],
        })
    return filas


# ---------------------------------------------------------------------------
# Item pages
# ---------------------------------------------------------------------------
def _num(s: str) -> int:
    return int(s.replace(".", "").replace(",", ""))


def parsear_pagina_objeto(texto: str) -> dict:
    """Extracts trade info and prices from the item page (ES, plain text)."""
    info: dict = {"comercio": None, "precio_tienda": None, "precio_venta": None, "tienda": None}
    m = re.search(r"según los datos del juego: ([^.|]+?)\.", texto)
    if m:
        info["comercio"] = m.group(1).strip()
    else:
        m = re.search(r"\| Intercambio \| ([^|]+?) \|", texto)
        if m:
            info["comercio"] = m.group(1).strip()
    m = re.search(r"\| Precio en tienda \| ([\d.]+) Kinah", texto)
    if m:
        info["precio_tienda"] = _num(m.group(1))
    m = re.search(r"\| Precio de venta \| ([\d.]+) Kinah", texto) or re.search(
        r"Los mercaderes lo compran por ([\d.]+) kinah", texto)
    if m:
        info["precio_venta"] = _num(m.group(1))
    m = re.search(r"lo vende (.+?) por ([\d.]+) Kinah", texto)
    if m:
        info["tienda"] = m.group(1).strip()
        if info["precio_tienda"] is None:
            info["precio_tienda"] = _num(m.group(2))
    return info


def comerciable_de(comercio: str | None) -> bool | None:
    if not comercio:
        return None
    c = comercio.lower()
    if c == "comerciable":
        return True
    if "ligado al alma" in c:
        # EN "Soul-bound": metabot says the item rolls its skill option "when soul-bound",
        # so it looks like a bind-on-use, not "not tradeable". Unconfirmed → None.
        return None
    if "no comerciable" in c or "vinculad" in c or "cuenta" in c or "no se puede" in c:
        return False
    return None


def obtener_info_objetos(desc: Descargador, slugs: list[str]) -> dict[str, dict]:
    info = {}
    total = len(slugs)
    for n, slug in enumerate(slugs, 1):
        archivo = CACHE / "objetos" / f"{slug}.txt.gz"
        ya = archivo.exists() and not desc.refrescar
        texto = desc.obtener(f"{BASE}/es_ES/aion-2/items/{slug}", archivo, transformar=texto_plano)
        if texto is None:
            continue
        info[slug] = parsear_pagina_objeto(texto)
        if not ya:
            log(f"  [{n}/{total}] {slug}: {info[slug]}")
    return info


# ---------------------------------------------------------------------------
# Building the catalog
# ---------------------------------------------------------------------------
def _sin_tildes(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def faccion_receta(rid: int) -> str:
    return FACCION_POR_DIGITO[str(rid)[1]]


def profesion_de(categoria: str) -> str:
    clave = _sin_tildes(categoria).strip()
    if clave not in CATEGORIAS:
        raise ValueError(f"Unknown category: {categoria!r}")
    return CATEGORIAS[clave]


def verificar_faccion(datos_es: dict, html_es: str) -> dict:
    """Cross-checks the faction digit against metabot's labels and faction ingredients."""
    items = datos_es["items"]
    gather = datos_es.get("gather", {})

    def nombre(i):
        return (items.get(str(i)) or gather.get(str(i)) or {}).get("name", "?")

    def slug(i):
        return items.get(str(i), {}).get("href", "").rsplit("/", 1)[-1]

    etiqueta = {"Elyos": "elyos", "Asmodianos": "asmodian"}
    tablas = collections.Counter()
    ambiguas = 0
    for fila in filas_tablas_faccion(html_es):
        cands = [r for r in datos_es["recipes"]
                 if slug(r["product"]) == fila["slug"] and r["mastery"] == fila["maestria"]
                 and [(nombre(p), q) for p, q in r["parts"]][:len(fila["mats"])] == fila["mats"]]
        facs = {faccion_receta(r["id"]) for r in cands}
        if len(facs) != 1:
            ambiguas += 1
            continue
        f = facs.pop()
        tablas["coinciden" if etiqueta.get(fila["faccion"]) == f else "contradicen"] += 1

    ingred = collections.Counter()
    for r in datos_es["recipes"]:
        marcas = {v for p, _ in r["parts"] for k, v in INGREDIENTES_FACCION.items() if k in _sin_tildes(nombre(p))}
        if len(marcas) == 1:
            ingred["coinciden" if marcas.pop() == faccion_receta(r["id"]) else "contradicen"] += 1
        elif len(marcas) > 1:
            ingred["mixtas"] += 1
    return {
        "regla": "2º dígito del id de receta: 1 = elyos, 2 = asmodian",
        "tablas_metabot": {"coinciden": tablas["coinciden"], "contradicen": tablas["contradicen"],
                           "filas_ambiguas": ambiguas},
        "ingredientes_de_faccion": {"coinciden": ingred["coinciden"], "contradicen": ingred["contradicen"],
                                    "mixtas": ingred["mixtas"]},
    }


def construir_catalogo(datos_es: dict, datos_en: dict, info_objetos: dict[str, dict],
                       version: str, evidencia: dict) -> dict:
    items_es, items_en = datos_es["items"], datos_en["items"]
    gather_es = datos_es.get("gather", {})
    gather_en = datos_en.get("gather", {})
    recetas_es = datos_es["recipes"]

    # faction that uses each item
    uso = collections.defaultdict(set)
    for r in recetas_es:
        f = faccion_receta(r["id"])
        uso[r["product"]].add(f)
        for p, _ in r["parts"]:
            uso[p].add(f)

    ids = set(int(k) for k in items_es) | set(uso)
    objetos = {}
    for i in sorted(ids):
        k = str(i)
        ies = items_es.get(k) or {}
        ien = items_en.get(k) or {}
        nombre = ies.get("name") or (gather_es.get(k) or {}).get("name") or f"#{i}"
        nombre_en = ien.get("name") or (gather_en.get(k) or {}).get("name")
        href = ies.get("href") or ""
        slug = href.rsplit("/", 1)[-1] if href else None
        info = info_objetos.get(slug or "", {})
        facs = uso.get(i, set())
        objetos[k] = {
            "nombre": nombre,
            "nombre_en": nombre_en,
            "grado": ies.get("grade"),
            "icono": (BASE + ies["icon"]) if ies.get("icon") else None,
            "comerciable": comerciable_de(info.get("comercio")),
            "vinculado": "(vinculado)" in nombre.lower() or "(bound)" in (nombre_en or "").lower(),
            "precio_npc": info.get("precio_tienda"),
            "slug": slug,
            # --- extra fields ---
            "faccion": "ambas" if len(facs) == 2 else (facs.pop() if facs else None),
            "precio_venta_npc": info.get("precio_venta"),
            "comercio": info.get("comercio"),
            "tienda_npc": info.get("tienda"),
            "recoleccion": (gather_es.get(k) or {}).get("name"),
        }

    # combo product: "Splendent"/"brillante" version of the product, same faction
    por_nombre_en = collections.defaultdict(list)
    for k, o in objetos.items():
        if o["nombre_en"]:
            por_nombre_en[o["nombre_en"]].append(int(k))

    def version_brillante(producto: int, faccion: str) -> int | None:
        base = objetos[str(producto)]["nombre_en"] or ""
        if not base or "Splendent" in base:
            return None
        if base.startswith("Artisan's ") or base.startswith("Expert's "):
            pref, resto = base.split(" ", 1)
            cand = f"{pref} Splendent {resto}"
        else:
            cand = f"Splendent {base}"
        opciones = [i for i in por_nombre_en.get(cand, []) if objetos[str(i)]["faccion"] in (faccion, "ambas")]
        return opciones[0] if len(opciones) == 1 else None

    recetas = []
    for r in sorted(recetas_es, key=lambda r: r["id"]):
        faccion = faccion_receta(r["id"])
        rate = r.get("rate") or [None, None]
        combo = int(r.get("combo") or 0)
        prod_combo = version_brillante(r["product"], faccion) if combo > 0 else None
        recetas.append({
            "id": r["id"],
            "faccion": faccion,
            "profesion": profesion_de(r["category"]),
            "nivel": int(r["mastery"]),
            "producto": r["product"],
            "cantidad": int(r["qty"]),
            "ingredientes": [[int(p), int(q)] for p, q in r["parts"]],
            "curva": rate[0],
            "combo_pct": combo,
            "curva_combo": rate[1] if len(rate) > 1 else None,
            "producto_combo": prod_combo,
            "cantidad_combo": int(r["qty"]) if prod_combo else None,
            # extra: "mejora" = mastery 0, labeled "Mejora"/"Upgrade" by metabot
            "tipo": "mejora" if int(r["mastery"]) == 0 else "normal",
        })

    con_combo = sum(1 for r in recetas if r["combo_pct"] > 0)
    con_prod_combo = sum(1 for r in recetas if r["producto_combo"])
    return {
        "atribucion": ATRIBUCION,
        "fuente": "metabot.gg",
        "version_cliente": version,
        "generado": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "profesiones": PROFESIONES,
        "notas": [
            "Facción: 2º dígito del id de receta (1 = elyos, 2 = asmodian), verificado en 'evidencia_faccion'. "
            "Las recetas de ambas facciones se guardan por separado: sus productos tienen ids distintos.",
            "objetos[].faccion: facción de las recetas que usan/producen el objeto ('ambas' si las dos). "
            "Hay nombres repetidos con un id por facción.",
            f"Combo: {con_combo} recetas tienen combo. metabot no publica el producto del combo; "
            f"en {con_prod_combo} recetas de equipo se infiere la versión 'brillante' ('Splendent') del producto "
            "(objetos que solo aparecen como ingrediente, sin receta normal). En el resto (comida, pociones, piedras) "
            "producto_combo = null. metabot indica que el combo da 'más objetos o un grado mayor' y que la "
            "fabricación combo tiene su propia curva (curva_combo).",
            "Recetas con nivel 0 (tipo 'mejora'): metabot las etiqueta 'Mejora'/'Upgrade'; no tienen curva propia.",
            "curva null: el cliente no trae curva de éxito (herramientas de avance, mejoras).",
            "precio_npc = precio de compra en tienda NPC (Kinah); precio_venta_npc = lo que paga el mercader.",
            "comerciable: true = 'Comerciable', false = 'No comerciable'. Todo el equipo fabricado figura como "
            "'Ligado al alma' (EN 'Soul-bound'); no está claro si se puede vender antes de ligarlo, así que queda "
            "comerciable = null (texto original en 'comercio'). Confirmar en el juego.",
        ],
        "evidencia_faccion": evidencia,
        "objetos": objetos,
        "curvas": datos_es["curves"],
        "max_maestria": datos_es.get("maxMastery", 100),
        "recetas": recetas,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generates data/catalogo.json from metabot.gg")
    ap.add_argument("--productos", action="store_true", help="also download the product pages")
    ap.add_argument("--sin-objetos", action="store_true", help="don't download item pages")
    ap.add_argument("--refrescar", action="store_true", help="ignore the cache and download again")
    ap.add_argument("--pausa", type=float, default=2.0, help="seconds between requests (default 2)")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    desc = Descargador(pausa=args.pausa, refrescar=args.refrescar)
    try:
        log("Downloading crafting pages (ES and EN)...")
        html_es = desc.obtener(URL_CRAFTEO["es"], CACHE / "crafting_es.html.gz")
        html_en = desc.obtener(URL_CRAFTEO["en"], CACHE / "crafting_en.html.gz")
        datos_es = extraer_datos_crafteo(html_es)
        datos_en = extraer_datos_crafteo(html_en)
        if {r["id"] for r in datos_es["recipes"]} != {r["id"] for r in datos_en["recipes"]}:
            log("  ! ES and EN recipes don't match; using ES as the reference")
        m = re.search(r"build (\d+\.\d+\.\d+\.\d+)", html_es)
        version = m.group(1) if m else VERSION_POR_DEFECTO
        log(f"  {len(datos_es['recipes'])} recipes, {len(datos_es['items'])} items, "
            f"{len(datos_es['curves'])} curves (client {version})")

        evidencia = verificar_faccion(datos_es, html_es)
        log(f"  Faction: {evidencia}")

        info_objetos: dict[str, dict] = {}
        if not args.sin_objetos:
            items = datos_es["items"]
            productos = {r["product"] for r in datos_es["recipes"]}
            ingredientes = {p for r in datos_es["recipes"] for p, _ in r["parts"]}
            elegidos = set(ingredientes)
            elegidos |= {int(k) for k, v in items.items() if "(vinculado)" in v["name"].lower()}
            if args.productos:
                elegidos |= productos
            slug_de = {i: items[str(i)]["href"].rsplit("/", 1)[-1] for i in map(int, items)}
            # whatever is already cached is always used (no download)
            elegidos |= {i for i, s in slug_de.items() if (CACHE / "objetos" / f"{s}.txt.gz").exists()}
            slugs = sorted({slug_de[i] for i in elegidos if i in slug_de})
            pendientes = sum(1 for s in slugs if not (CACHE / "objetos" / f"{s}.txt.gz").exists())
            log(f"Item pages: {len(slugs)} ({pendientes} not cached, ~{pendientes * args.pausa / 60:.1f} min)")
            info_objetos = obtener_info_objetos(desc, slugs)

        cat = construir_catalogo(datos_es, datos_en, info_objetos, version, evidencia)
    finally:
        desc.cerrar()

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")

    # summary
    c = collections.Counter((r["profesion"], r["faccion"]) for r in cat["recetas"])
    log(f"\nGenerated {args.salida} ({len(cat['recetas'])} recipes, {len(cat['objetos'])} items, "
        f"{desc.descargas} new downloads)")
    for p in PROFESIONES:
        log(f"  {PROFESIONES[p]:<11} elyos={c[(p, 'elyos')]:>3}  asmodian={c[(p, 'asmodian')]:>3}")
    precios = sum(1 for o in cat["objetos"].values() if o["precio_npc"] is not None)
    comer = collections.Counter(o["comerciable"] for o in cat["objetos"].values())
    log(f"  precio_npc known: {precios} items; comerciable: {dict(comer)}")
    log(f"  producto_combo inferred in {sum(1 for r in cat['recetas'] if r['producto_combo'])} recipes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
