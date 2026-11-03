"""Turns OCR lines into market rows and groups them into order books.

FilaMercado (dict):
    objeto_id      int | None    catalog id (None if it could not be matched)
    nombre_leido   str           name text exactly as read by the OCR
    precio         int | None    unit price in Kinah
    cantidad       int | None    units in the listing
    confianza      float 0–1
    dudosa         bool          needs user review
  Extra fields (they don't break the contract):
    nombre         str | None    official catalog name
    total          int | None    total listing price, if it was read
    motivos        list[str]     why it is doubtful (text in Spanish)
    caja           [x, y, w, h]  area of the row in the image (for crops)
"""
from __future__ import annotations

import re
import unicodedata
from itertools import permutations
from statistics import median
from typing import Any, Iterable

from rapidfuzz import fuzz, process

FilaMercado = dict[str, Any]

UMBRAL_DUDOSA = 0.80       # confidence below this → doubtful
UMBRAL_NOMBRE = 72         # minimum score (0–100) to accept a match
UMBRAL_CONTEXTO = 88       # header without numbers that sets the item of the following rows
MARGEN_AMBIGUO = 4         # two candidates closer than this → ambiguous

# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
_NO_ALNUM = re.compile(r"[^0-9a-z]+")


def normalizar(texto: str) -> str:
    """Lowercase, no accents or punctuation, single spaces."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return _NO_ALNUM.sub(" ", t).strip()


# Typical OCR confusions. Only applied to numeric fields.
_A_DIGITO = {
    "O": "0", "o": "0", "D": "0", "Q": "0", "U": "0",
    "l": "1", "I": "1", "i": "1", "|": "1", "!": "1", "L": "1", "j": "1", "J": "1",
    "S": "5", "s": "5",
    "B": "8",
    "Z": "2", "z": "2",
    "G": "6", "b": "6",
    "g": "9", "q": "9",
    "T": "7",
}
# The other way round, for names read with digits ("0kra" → "okra").
_A_LETRA = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "2": "z", "6": "g"})
_SEPARADORES = ".,'’   "
_ADORNOS = "xX×*:;()[]"


def _limpiar_token_numerico(texto: str) -> str:
    t = texto.strip().strip(_ADORNOS).strip()
    return t


def es_numerico(texto: str) -> bool:
    """Does it look like a number (even with some O/0, l/1... confusion)?"""
    t = _limpiar_token_numerico(texto)
    if not t or t == "0":
        # A lone "0" is usually the currency (Kinah) icon misread.
        return False
    digitos = sum(c.isdigit() for c in t)
    if digitos == 0:
        return False
    confusos = 0
    for c in t:
        if c.isdigit() or c in _SEPARADORES:
            continue
        if c in _A_DIGITO:
            confusos += 1
        else:
            return False
    if confusos <= digitos:
        return True
    # Many confusions: only if it clearly looks like a number with thousands ("l2.5OO").
    mapeado = "".join(_A_DIGITO.get(c, c) if not c.isdigit() else c for c in t)
    return re.fullmatch(r"\d{1,3}([.,]\d{3})+", mapeado) is not None


def parsear_numero(texto: str) -> tuple[int | None, bool, bool]:
    """Reads an integer with Spanish thousands separators ("12.500", "1.234.567").

    Returns (valor, coherente, corregido):
      coherente = the thousands groups have 3 digits (otherwise it may be a misread)
      corregido = some letter was replaced by a digit (O→0, l→1, S→5, B→8...)
    """
    t = _limpiar_token_numerico(texto)
    if not t:
        return None, False, False
    corregido = False
    chars = []
    for c in t:
        if c in _A_DIGITO and not c.isdigit():
            chars.append(_A_DIGITO[c])
            corregido = True
        else:
            chars.append(c)
    t = "".join(chars)
    if any(not (c.isdigit() or c in _SEPARADORES) for c in t):
        return None, False, corregido
    grupos = [g for g in re.split(r"[.,'’   ]+", t) if g != ""]
    if not grupos:
        return None, False, corregido
    coherente = True
    if len(grupos) > 1:
        if not (1 <= len(grupos[0]) <= 3) or any(len(g) != 3 for g in grupos[1:]):
            coherente = False
    elif len(grupos[0]) > 4:
        # A large number without a separator is unusual in the Spanish UI
        # (the OCR may have swallowed a dot). It is accepted with a warning.
        coherente = False
    if t[0] in _SEPARADORES or t[-1] in _SEPARADORES:
        coherente = False
    return int("".join(grupos)), coherente, corregido


# --------------------------------------------------------------------------
# Catalog name index
# --------------------------------------------------------------------------
class IndiceNombres:
    """Fuzzy search of item names.

    Accepts: a `Catalogo` with `buscar(texto, limite)` (used to get candidates),
    a catalog with an `objetos` attribute/key ({id: {"nombre": ...}}),
    or a plain dict {id: nombre}. Building it once and reusing it is faster.
    """

    def __init__(self, cat, faccion: str | None = None):
        self.cat = cat
        self.faccion = faccion
        self._buscar = getattr(cat, "buscar", None) if not isinstance(cat, dict) else None
        self.nombres: dict[int, str] = {}
        objetos = None
        if cat is None:
            objetos = {}
        elif isinstance(cat, dict):
            objetos = cat.get("objetos", cat)
        else:
            objetos = getattr(cat, "objetos", None)
        if isinstance(objetos, dict):
            f = (faccion or "").lower() or None
            for k, v in objetos.items():
                nombre = v.get("nombre") if isinstance(v, dict) else v
                if f and f != "ambas" and isinstance(v, dict):
                    fo = v.get("faccion")
                    if fo and fo not in (f, "ambas"):
                        continue  # item exclusive to the other faction
                if isinstance(nombre, str) and nombre:
                    try:
                        self.nombres[int(k)] = nombre
                    except (TypeError, ValueError):
                        continue
        self._ids = list(self.nombres)
        self._norm = [normalizar(self.nombres[i]) for i in self._ids]

    def __bool__(self):
        return bool(self._ids) or self._buscar is not None

    @staticmethod
    def _puntuar(leido: str, candidato: str) -> float:
        if not leido or not candidato:
            return 0.0
        if leido == candidato:
            return 100.0
        p = max(fuzz.ratio(leido, candidato), fuzz.token_sort_ratio(leido, candidato))
        return float(p)

    def _candidatos(self, texto: str, limite: int) -> list[tuple[int, str]]:
        if self._buscar is not None:
            try:
                if self.faccion:
                    try:
                        res = self._buscar(texto, limite=limite, faccion=self.faccion) or []
                    except TypeError:  # catalog without a faccion parameter
                        res = self._buscar(texto, limite=limite) or []
                else:
                    res = self._buscar(texto, limite=limite) or []
                return [(int(r[0]), r[1]) for r in res]
            except Exception:
                pass
        if not self._ids:
            return []
        q = normalizar(texto)
        res = process.extract(q, self._norm, scorer=fuzz.WRatio, limit=limite)
        return [(self._ids[i], self.nombres[self._ids[i]]) for _, _, i in res]

    def buscar(self, texto: str, limite: int = 5) -> list[tuple[int, str, float]]:
        """[(id, nombre, score 0–100)] sorted from best to worst."""
        truncado = texto.rstrip().endswith(("...", "…"))
        base = normalizar(texto)
        variantes = {base, normalizar(texto.translate(_A_LETRA))}
        consultas = {texto, texto.translate(_A_LETRA)}
        candidatos: dict[int, str] = {}
        for c in consultas:
            for i, n in self._candidatos(c, max(limite, 10)):
                candidatos[i] = n
        puntuados = []
        for i, nombre in candidatos.items():
            nn = normalizar(nombre)
            p = max(self._puntuar(v, nn) for v in variantes)
            if truncado and len(base) >= 6:
                p = max(p, self._puntuar(base, nn[: len(base)]) - 2)
            puntuados.append((i, nombre, p))
        puntuados.sort(key=lambda t: (-t[2], len(t[1])))
        return puntuados[:limite]


def _indice(cat, faccion: str | None = None) -> IndiceNombres:
    return cat if isinstance(cat, IndiceNombres) else IndiceNombres(cat, faccion)


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------
def _palabras(lineas: Iterable[dict]) -> list[dict]:
    salida = []
    for linea in lineas:
        palabras = linea.get("palabras") or []
        if not palabras:
            palabras = [{k: linea[k] for k in ("texto", "x", "y", "w", "h")}]
        for p in palabras:
            if str(p.get("texto", "")).strip():
                salida.append(dict(p))
    return salida


def _agrupar_en_filas(palabras: list[dict]) -> list[list[dict]]:
    """Groups words by their vertical center (the OCR may split a row into
    several lines if the columns are far apart)."""
    if not palabras:
        return []
    alto_tipico = median(p["h"] for p in palabras) or 1
    palabras = sorted(palabras, key=lambda p: p["y"] + p["h"] / 2)
    filas: list[list[dict]] = []
    centro = None
    for p in palabras:
        c = p["y"] + p["h"] / 2
        if centro is not None and abs(c - centro) <= 0.55 * alto_tipico:
            filas[-1].append(p)
            centro = sum(q["y"] + q["h"] / 2 for q in filas[-1]) / len(filas[-1])
        else:
            filas.append([p])
            centro = c
    return [sorted(f, key=lambda p: p["x"]) for f in filas]


def _caja(palabras: list[dict]) -> list[float]:
    x0 = min(p["x"] for p in palabras)
    y0 = min(p["y"] for p in palabras)
    x1 = max(p["x"] + p["w"] for p in palabras)
    y1 = max(p["y"] + p["h"] for p in palabras)
    return [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]


def _unir_numeros(tokens: list[dict]) -> list[dict]:
    """Joins numbers the OCR split: "12." + "500", "1" + "234.567", "12 500"."""
    salida: list[dict] = []
    for t in tokens:
        if salida and t["num"] and salida[-1]["num"]:
            a = salida[-1]
            hueco = t["x"] - (a["x"] + a["w"])
            alto = max(a["h"], t["h"], 1)
            ta, tb = _limpiar_token_numerico(a["texto"]), _limpiar_token_numerico(t["texto"])
            pegados = hueco < 0.6 * alto
            sep_borde = ta[-1:] in _SEPARADORES or tb[:1] in _SEPARADORES
            tres = re.fullmatch(r"[.,]?\d{3}([.,]\d{3})*", tb) is not None
            if pegados and (sep_borde or (tres and len(re.sub(r"\D", "", ta)) <= 3)):
                union = ta + tb if sep_borde else ta + "." + tb
                if parsear_numero(union)[1]:
                    a["texto"] = union
                    a["w"] = t["x"] + t["w"] - a["x"]
                    continue
        salida.append(dict(t))
    return salida


def _asignar_por_columnas(tokens, columnas) -> dict[str, list[dict]]:
    asignado: dict[str, list[dict]] = {k: [] for k in columnas}
    asignado["_resto"] = []
    for t in tokens:
        cx = t["x"] + t["w"] / 2
        destino = "_resto"
        for nombre, (x0, x1) in columnas.items():
            if x0 <= cx <= x1:
                destino = nombre
                break
        asignado[destino].append(t)
    return asignado


def _decidir_por_separador(a: dict, b: dict):
    """(precio, cantidad) if only one has a thousands separator (and is ≥ 1000)."""
    if a["sep"] != b["sep"] and max(a["valor"], b["valor"]) >= 1000:
        p = a if a["sep"] else b
        return p, (b if p is a else a)
    return None


def _decidir_por_ratio(a: dict, b: dict):
    """(precio, cantidad) if one is ≥ 10 times the other (weak hint)."""
    grande, chico = (a, b) if a["valor"] >= b["valor"] else (b, a)
    if chico["valor"] == 0 or grande["valor"] / max(chico["valor"], 1) >= 10:
        return grande, chico
    return None


def _inferir_disposicion(filas_nums: list[list[dict]]) -> dict | None:
    """Learns at which horizontal position price and quantity are on THIS
    screen, from the unambiguous rows (thousands separator). If there are none,
    uses the weak ratio hint. Returns {"precio": x, "cantidad": x, "factor"}."""
    for decisor, factor in ((_decidir_por_separador, 0.97), (_decidir_por_ratio, 0.88)):
        xs_p, xs_q = [], []
        for nums in filas_nums:
            if len(nums) != 2:
                continue
            r = decisor(nums[0], nums[1])
            if r:
                xs_p.append(r[0]["x"])
                xs_q.append(r[1]["x"])
        if not xs_p:
            continue
        xp, xq = median(xs_p), median(xs_q)
        if abs(xp - xq) < 20:
            continue
        coherentes = sum((p > q) == (xp > xq) for p, q in zip(xs_p, xs_q))
        if coherentes / len(xs_p) < 0.8:
            continue
        if len(xs_p) == 1:
            factor = min(factor, 0.88)
        return {"precio": xp, "cantidad": xq, "factor": factor, "muestras": len(xs_p)}
    return None


def _elegir_precio_cantidad(nums: list[dict], orden: tuple[str, str], disposicion: dict | None = None):
    """Heuristic without column calibration.

    Returns (precio, cantidad, total, factor_confianza, motivos).
    """
    motivos: list[str] = []
    valores = [n["valor"] for n in nums]
    if len(nums) == 1:
        n = nums[0]
        if disposicion and abs(n["x"] - disposicion["cantidad"]) < abs(n["x"] - disposicion["precio"]):
            return None, n["valor"], None, 0.6, ["Solo se leyó un número"]
        return n["valor"], None, None, 0.6, ["Solo se leyó un número"]

    def precio_de_pareja(i: int, j: int):
        a, b = nums[i], nums[j]
        por_sep = _decidir_por_separador(a, b)
        if disposicion:
            directo = abs(a["x"] - disposicion["precio"]) + abs(b["x"] - disposicion["cantidad"])
            cruzado = abs(b["x"] - disposicion["precio"]) + abs(a["x"] - disposicion["cantidad"])
            p, q = (a, b) if directo <= cruzado else (b, a)
            if por_sep is not None and por_sep[0] is not p:
                motivos.append("El precio no está en la columna habitual de esta pantalla")
                return por_sep[0], por_sep[1], 0.6
            return p, q, 1.0 if por_sep is not None else disposicion["factor"]
        if por_sep is not None:
            return por_sep[0], por_sep[1], 1.0
        por_ratio = _decidir_por_ratio(a, b)
        if por_ratio is not None:
            return por_ratio[0], por_ratio[1], 0.85
        # Ambiguous: use the configured order (left → right).
        primero, segundo = (a, b) if a["x"] <= b["x"] else (b, a)
        if orden[0] == "precio":
            return primero, segundo, 0.7
        return segundo, primero, 0.7

    # Are there three numbers that fit price × quantity = total?
    if len(nums) >= 3:
        for i, j, k in permutations(range(len(nums)), 3):
            if i > j:
                continue
            a, b, c = valores[i], valores[j], valores[k]
            if c >= max(a, b) and a * b > 0 and abs(a * b - c) <= max(1, 0.01 * c):
                p, q, f = precio_de_pareja(i, j)
                if len(nums) > 3:
                    motivos.append("Hay más números de los esperados en la fila")
                    f *= 0.85
                return p["valor"], q["valor"], c, min(1.0, f + 0.05), motivos
        motivos.append("Precio × cantidad no cuadra con ningún total")
        # Keep the first two numbers (by position).
        p, q, f = precio_de_pareja(0, 1)
        return p["valor"], q["valor"], None, f * 0.75, motivos

    p, q, f = precio_de_pareja(0, 1)
    if f < 0.8:
        motivos.append("No está claro cuál es el precio y cuál la cantidad")
    return p["valor"], q["valor"], None, f, motivos


def interpretar_pantalla(
    lineas: list[dict],
    cat,
    columnas: dict | None = None,
    orden_numeros: tuple[str, str] = ("precio", "cantidad"),
    faccion: str | None = None,
) -> list[FilaMercado]:
    """Turns the OCR lines of one screen into market rows.

    - `cat`: Catalogo, dict {id: nombre} or IndiceNombres (see IndiceNombres).
    - `columnas`: {"nombre": [x0, x1], "precio": [...], "cantidad": [...], "total": [...]}
      in image coordinates (from the calibration). Without columns a heuristic is
      used: price = number with thousands separator / the largest; if there are
      three numbers, price × quantity = total is looked for.
    - A line with a catalog name and no numbers (header of an item's order book)
      assigns that item to the following rows without a name.
    - `faccion` ("elyos"|"asmodian"): some items share a name with a different
      id per faction; the server's faction picks the right one.
      Without it, those rows come out doubtful.
    """
    indice = _indice(cat, faccion)
    filas: list[FilaMercado] = []
    borradores: list[dict] = []
    contexto: tuple[int, str, float] | None = None

    # ---- 1st pass: split name and numbers of each row ----
    for palabras in _agrupar_en_filas(_palabras(lineas)):
        tokens = [dict(p, num=es_numerico(p["texto"])) for p in palabras]
        tokens = _unir_numeros(tokens)
        motivos: list[str] = []
        factor = 1.0
        nums_por_col: dict[str, str] = {}
        numericos: list[dict] = []

        if columnas:
            asig = _asignar_por_columnas(tokens, columnas)
            texto_nombre = " ".join(t["texto"] for t in asig.get("nombre", []))
            for col in ("precio", "cantidad", "total"):
                ts = [t for t in asig.get(col, []) if t["num"]]
                if ts:
                    nums_por_col[col] = "".join(t["texto"] for t in ts) if len(ts) > 1 else ts[0]["texto"]
            hay_numeros = bool(nums_por_col)
        else:
            # Name = the longest run of consecutive non-numeric words.
            tramos: list[list[dict]] = [[]]
            for t in tokens:
                if t["num"]:
                    tramos.append([])
                else:
                    tramos[-1].append(t)
            nombre_tokens = max(tramos, key=lambda tr: sum(len(t["texto"]) for t in tr))
            texto_nombre = " ".join(t["texto"] for t in nombre_tokens)
            numericos = [t for t in tokens if t["num"]]
            hay_numeros = bool(numericos)

        # ---- name ----
        candidato = None
        if texto_nombre.strip() and indice:
            res = indice.buscar(texto_nombre, limite=3)
            if res:
                candidato = res[0]
                if len(res) > 1 and res[1][0] != candidato[0]:
                    mismo_nombre = normalizar(res[1][1]) == normalizar(candidato[1])
                    if mismo_nombre and res[1][2] >= candidato[2] - MARGEN_AMBIGUO:
                        motivos.append(f"«{candidato[1]}» existe en las dos facciones: indica la facción del servidor")
                        factor *= 0.5
                    elif candidato[2] < 100 and res[1][2] >= candidato[2] - MARGEN_AMBIGUO:
                        motivos.append(f"Nombre ambiguo: «{res[0][1]}» o «{res[1][1]}»")
                        factor *= 0.8

        if not hay_numeros:
            # Header / title: sets the context if it matches the catalog well.
            if candidato and candidato[2] >= UMBRAL_CONTEXTO:
                contexto = candidato
            continue

        nums = []
        for t in numericos:
            v, coh, corr = parsear_numero(t["texto"])
            if v is None:
                continue
            tiene_sep = any(c in t["texto"] for c in ".,") and coh
            nums.append({"valor": v, "sep": tiene_sep, "x": t["x"] + t["w"] / 2,
                         "coh": coh, "corr": corr, "texto": t["texto"]})
        borradores.append({
            "palabras": palabras, "texto_nombre": texto_nombre, "candidato": candidato,
            "contexto": contexto, "motivos": motivos, "factor": factor,
            "nums": nums, "nums_por_col": nums_por_col,
        })

    disposicion = None if columnas else _inferir_disposicion([b["nums"] for b in borradores])

    # ---- 2nd pass: decide price/quantity and match ----
    for b in borradores:
        palabras, texto_nombre, candidato = b["palabras"], b["texto_nombre"], b["candidato"]
        contexto, motivos, factor = b["contexto"], b["motivos"], b["factor"]
        nums_por_col = b["nums_por_col"]

        precio = cantidad = total = None
        if columnas:
            lecturas = {}
            for col, texto in nums_por_col.items():
                v, coh, corr = parsear_numero(texto)
                lecturas[col] = v
                if v is not None and not coh:
                    motivos.append(f"Separadores de miles raros en {col}: «{texto}»")
                    factor *= 0.75
                if corr:
                    factor *= 0.9
            precio, cantidad, total = lecturas.get("precio"), lecturas.get("cantidad"), lecturas.get("total")
            if precio is None and total is not None and cantidad:
                if total % cantidad == 0:
                    precio = total // cantidad
                    motivos.append("Precio unitario calculado a partir del total")
                    factor *= 0.9
            if total is not None and precio is not None and cantidad:
                if abs(precio * cantidad - total) > max(1, 0.01 * total):
                    motivos.append("Precio × cantidad no cuadra con el total")
                    factor *= 0.6
        else:
            nums = b["nums"]
            for n in nums:
                if not n["coh"]:
                    motivos.append(f"Separadores de miles raros: «{n['texto']}»")
                    factor *= 0.75
                if n["corr"]:
                    factor *= 0.9
            if nums:
                precio, cantidad, total, f, m = _elegir_precio_cantidad(nums, orden_numeros, disposicion)
                factor *= f
                motivos.extend(m)

        # ---- matching / context ----
        objeto_id = nombre = None
        p_nombre = 0.0
        if candidato and candidato[2] >= UMBRAL_NOMBRE:
            objeto_id, nombre, p_nombre = candidato
        elif not texto_nombre.strip() and contexto:
            objeto_id, nombre, p_nombre = contexto
        elif texto_nombre.strip():
            if candidato:
                motivos.append(f"Nombre no reconocido (¿«{candidato[1]}»?)")
            else:
                motivos.append("Nombre no reconocido")
        else:
            motivos.append("Fila sin nombre")

        if precio is None:
            motivos.append("Falta el precio")
        elif precio <= 0:
            motivos.append("Precio no válido")
            factor *= 0.3
        if cantidad is None:
            motivos.append("Falta la cantidad")
        elif cantidad <= 0:
            motivos.append("Cantidad no válida")
            factor *= 0.3

        confianza = round(max(0.0, min(1.0, (p_nombre / 100.0) * factor)), 3)
        dudosa = (
            confianza < UMBRAL_DUDOSA
            or objeto_id is None
            or not precio
            or not cantidad
            or precio <= 0
            or cantidad <= 0
        )
        filas.append(
            {
                "objeto_id": objeto_id,
                "nombre_leido": texto_nombre.strip(),
                "nombre": nombre,
                "precio": precio,
                "cantidad": cantidad,
                "total": total,
                "confianza": confianza,
                "dudosa": bool(dudosa),
                "motivos": motivos,
                "caja": _caja(palabras),
            }
        )
    return filas


# --------------------------------------------------------------------------
# Order book and consolidation
# --------------------------------------------------------------------------
def agrupar_libro(filas: Iterable[FilaMercado], incluir_dudosas: bool = False) -> dict[int, dict]:
    """{objeto_id: {"ofertas": [(precio, cantidad)], "precio_min", "cantidad_total",
    "num_anuncios", "nombre"}} with offers sorted by price."""
    libros: dict[int, dict] = {}
    for f in filas:
        if f.get("objeto_id") is None or not f.get("precio") or not f.get("cantidad"):
            continue
        if f.get("dudosa") and not incluir_dudosas:
            continue
        lib = libros.setdefault(f["objeto_id"], {"ofertas": [], "nombre": f.get("nombre")})
        lib["ofertas"].append((float(f["precio"]), int(f["cantidad"])))
    for lib in libros.values():
        lib["ofertas"].sort()
        lib["precio_min"] = lib["ofertas"][0][0]
        lib["cantidad_total"] = sum(c for _, c in lib["ofertas"])
        lib["num_anuncios"] = len(lib["ofertas"])
    return libros


def _clave_objeto(f: FilaMercado):
    if f.get("objeto_id") is not None:
        return ("id", f["objeto_id"])
    return ("txt", normalizar(f.get("nombre_leido", "")))


def consolidar(fotogramas: Iterable[list[FilaMercado]]) -> list[FilaMercado]:
    """Merges the rows of several frames of the same session.

    For each item and each offer (precio, cantidad) it keeps the maximum number
    of times it appears in a single frame: this way the overlap when scrolling
    the list doesn't duplicate listings, but two identical listings visible at
    once do count twice. For each offer the most reliable reading is kept.
    Doubtful rows are kept (without repeats) for review.
    """
    mejores: dict[tuple, dict[tuple, list[FilaMercado]]] = {}
    dudosas: dict[tuple, FilaMercado] = {}
    orden: list[tuple] = []

    for filas in fotogramas:
        conteo: dict[tuple, dict[tuple, list[FilaMercado]]] = {}
        for f in filas:
            ko = _clave_objeto(f)
            if f.get("dudosa"):
                kd = (ko, f.get("precio"), f.get("cantidad"))
                previa = dudosas.get(kd)
                if previa is None or f.get("confianza", 0) > previa.get("confianza", 0):
                    if previa is not None and previa.get("recorte") and not f.get("recorte"):
                        f = dict(f, recorte=previa["recorte"])
                    dudosas[kd] = f
                continue
            conteo.setdefault(ko, {}).setdefault((f["precio"], f["cantidad"]), []).append(f)
        for ko, ofertas in conteo.items():
            if ko not in mejores:
                mejores[ko] = {}
                orden.append(ko)
            for kof, lista in ofertas.items():
                actual = mejores[ko].get(kof, [])
                if len(lista) > len(actual):
                    mejores[ko][kof] = lista
                elif len(lista) == len(actual):
                    # Same quantity: keep the one with the highest confidence.
                    if sum(x["confianza"] for x in lista) > sum(x["confianza"] for x in actual):
                        mejores[ko][kof] = lista

    salida: list[FilaMercado] = []
    claves_buenas = set()
    for ko in orden:
        for kof in sorted(mejores[ko], key=lambda k: (k[0], k[1])):
            salida.extend(mejores[ko][kof])
            claves_buenas.add((ko, kof[0], kof[1]))
    for kd, f in dudosas.items():
        # A doubtful row that was read correctly in another frame is no longer needed.
        if kd not in claves_buenas:
            salida.append(f)
    return salida


def a_lecturas(
    filas: Iterable[FilaMercado],
    servidor_id: str,
    fuente: str,
    fecha=None,
    incluir_dudosas: bool = False,
    clase_lectura=None,
):
    """Turns (already reviewed) rows into `Lectura` objects (from app.db) or dicts."""
    from datetime import datetime, timezone

    fecha = fecha or datetime.now(timezone.utc)
    if clase_lectura is None:
        try:
            from app.db import Lectura as clase_lectura  # type: ignore
        except Exception:
            clase_lectura = None
    salida = []
    for oid, lib in agrupar_libro(filas, incluir_dudosas=incluir_dudosas).items():
        datos = dict(
            servidor_id=servidor_id,
            objeto_id=int(oid),
            fecha=fecha,
            precio_min=lib["precio_min"],
            cantidad_total=lib["cantidad_total"],
            num_anuncios=lib["num_anuncios"],
            ofertas=lib["ofertas"],
            fuente=fuente,
        )
        salida.append(clase_lectura(**datos) if clase_lectura else datos)
    return salida
