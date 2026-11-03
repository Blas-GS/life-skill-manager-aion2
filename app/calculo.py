"""Crafting profitability engine (AION 2).

Public interface:
    coste_adquisicion(objeto_id, cat, precios, ...) -> (coste, origen, receta_id | None)
    analizar_receta(receta, cat, precios, ajustes, nivel, inventario=None, intentos=1, ...) -> dict
    mejores_oportunidades(cat, precios, ajustes, niveles, faccion, inventario=None, filtros=None, ...) -> list[dict]

`cat` can be the raw dict from data/catalogo.json or a Catalogo object (app/catalogo.py).
`precios` is {objeto_id: InfoPrecio}; InfoPrecio can be a dict or a Lectura
(fields precio_min, ofertas, fecha, cantidad_total, num_anuncios; optional precio_npc, volumen_dia).
All probabilities are returned as fractions (0–1); the catalog curves are in %.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from app.precio_objetivo import a_utc, campo, fmt

INF = math.inf

AJUSTES_POR_DEFECTO = {
    "comision_registro": 0.02,       # paid when listing (on the listing price)
    "impuesto_venta": 0.10,          # paid when selling
    "rebaja_listado": 1,             # Kinah below the cheapest listing
    "combo_fallido": "pierde_todo",  # "pierde_todo" | "queda_base"
    "valorar_inventario": "mercado", # "mercado" (opportunity cost) | "cero"
    "horas_precio_antiguo": 24,
    "max_anuncios": 10,
    "unidades_por_anuncio": 1,       # units that fit in one listing (to be confirmed in game)
    "anuncios_saturado": 50,         # number of product listings from which a warning is shown
    "dias_saturado": 7,              # saturated if on offer > N days of sales (when volumen_dia exists)
    "tope_intentos": 100,            # maximum recommended attempts in the dashboard
    "nivel_por_defecto": 1,          # level used when the profile lacks that profession
}

ORDEN_ORIGEN = {"inventario": 0, "mercado": 1, "npc": 2, "fabricar": 3}


def ajustes_completos(ajustes=None) -> dict:
    resultado = dict(AJUSTES_POR_DEFECTO)
    for clave, valor in (ajustes or {}).items():
        if valor is not None:
            resultado[clave] = valor
    return resultado


# --- catalog -----------------------------------------------------------------

class _Cat:
    """Adapter: accepts the catalogo.json dict or a Catalogo object."""

    def __init__(self, cat):
        self._cat = cat
        raw = cat if isinstance(cat, dict) else None
        if raw is None:
            for nombre in ("datos", "data", "raw"):
                candidato = getattr(cat, nombre, None)
                if isinstance(candidato, dict):
                    raw = candidato
                    break
        if raw is not None:
            self.objetos = raw.get("objetos", {}) or {}
            self.curvas = raw.get("curvas", {}) or {}
            recetas = raw.get("recetas", []) or []
        else:
            self.objetos = getattr(cat, "objetos", None) or {}
            self.curvas = getattr(cat, "curvas", None) or {}
            recetas = getattr(cat, "recetas", None)
            if recetas is None or callable(recetas):
                vistas, recetas = set(), []
                for faccion in ("elyos", "asmodian"):
                    for r in cat.recetas_de(faccion):
                        if r["id"] not in vistas:
                            vistas.add(r["id"])
                            recetas.append(r)
        self.recetas = list(recetas)
        self._productores = {}
        self._ingredientes = set()
        for r in self.recetas:
            self._productores.setdefault(int(r["producto"]), []).append(r)
            for ing, _ in r.get("ingredientes", []):
                self._ingredientes.add(int(ing))

    def objeto(self, oid) -> dict:
        obj = self.objetos.get(str(oid)) or self.objetos.get(oid)
        if obj is None and not isinstance(self._cat, dict) and hasattr(self._cat, "objeto"):
            try:
                obj = self._cat.objeto(oid)
            except Exception:
                obj = None
        return obj or {}

    def nombre(self, oid) -> str:
        return self.objeto(oid).get("nombre") or str(oid)

    def recetas_que_producen(self, oid) -> list:
        return self._productores.get(int(oid), [])

    def recetas_de(self, faccion) -> list:
        if faccion is None:
            return list(self.recetas)
        return [r for r in self.recetas if r.get("faccion") in (faccion, "ambas", None)]

    def es_intermedio(self, oid) -> bool:
        return int(oid) in self._ingredientes

    def valor_curva(self, curva, indice):
        """Probability (0–1) of the curve at the index, clamped to the last value.
        Returns (prob, known)."""
        if curva is None:
            return 1.0, True
        valores = curva if isinstance(curva, (list, tuple)) else self.curvas.get(curva)
        if not valores:
            return 1.0, False
        return float(valores[min(max(indice, 0), len(valores) - 1)]) / 100.0, True


# --- probabilities -----------------------------------------------------------

def probabilidades(receta, nivel, cat, ajustes=None) -> dict:
    """P(success), combos and expected units per attempt of each product."""
    cat = cat if isinstance(cat, _Cat) else _Cat(cat)
    aj = ajustes_completos(ajustes)
    diferencia = int(nivel) - int(receta.get("nivel") or 1)
    p, curva_ok = cat.valor_curva(receta.get("curva"), diferencia)
    combo_pct = float(receta.get("combo_pct") or 0) / 100.0
    p_combo_curva, combo_ok = (cat.valor_curva(receta.get("curva_combo"), diferencia)
                               if combo_pct > 0 else (0.0, True))
    p_simple = p * (1 - combo_pct)
    p_combo = p * combo_pct * p_combo_curva
    p_combo_fallido = p * combo_pct * (1 - p_combo_curva)

    producto = int(receta["producto"])
    cantidad = receta.get("cantidad") or 1
    producto_combo = receta.get("producto_combo")
    if producto_combo is None:
        cantidad_combo = receta.get("cantidad_combo") or 2 * cantidad
        producto_combo = producto
    else:
        producto_combo = int(producto_combo)
        cantidad_combo = receta.get("cantidad_combo") or cantidad

    base = cantidad * p_simple
    if aj["combo_fallido"] == "queda_base":
        base += cantidad * p_combo_fallido
    salidas = {producto: base}
    salidas[producto_combo] = salidas.get(producto_combo, 0.0) + cantidad_combo * p_combo
    return {
        "desbloqueada": diferencia >= 0,
        "p_exito": p,
        "p_exito_simple": p_simple,
        "p_combo_activado": p * combo_pct,
        "p_combo": p_combo,
        "p_combo_fallido": p_combo_fallido,
        "salidas": salidas,
        "items_esperados": sum(salidas.values()),
        "curvas_conocidas": curva_ok and combo_ok,
    }


# --- calculation context (cost memo) -----------------------------------------

class _Contexto:
    def __init__(self, cat, precios, ajustes, niveles, faccion=None, precios_npc=None, ahora=None):
        self.cat = cat if isinstance(cat, _Cat) else _Cat(cat)
        self.precios = precios or {}
        self.aj = ajustes_completos(ajustes)
        self.niveles = dict(niveles or {})
        self.faccion = faccion
        self.npc = precios_npc or {}
        self.ahora = a_utc(ahora) if ahora else datetime.now(timezone.utc)
        self._memo = {}

    def info(self, oid):
        return self.precios.get(int(oid), self.precios.get(str(oid)))

    def precio_mercado(self, oid):
        valor = campo(self.info(oid), "precio_min")
        return float(valor) if valor is not None and float(valor) > 0 else None

    def precio_npc(self, oid):
        valor = self.npc.get(int(oid), self.npc.get(str(oid)))
        if valor is None:
            valor = campo(self.info(oid), "precio_npc")
        if valor is None:
            valor = self.cat.objeto(oid).get("precio_npc")
        return float(valor) if valor is not None and float(valor) > 0 else None

    def nivel(self, profesion):
        return int(self.niveles.get(profesion, self.aj["nivel_por_defecto"]))

    def receta_disponible(self, receta):
        if self.faccion and receta.get("faccion") not in (self.faccion, "ambas", None):
            return False
        return self.nivel(receta["profesion"]) >= int(receta.get("nivel") or 1)

    def coste_fabricar(self, oid, pila=frozenset()):
        """Best unit cost of crafting `oid`: (coste|None, receta_id|None, completo)."""
        mejor, mejor_id, completo = None, None, True
        pila = pila | {int(oid)}
        for r in self.cat.recetas_que_producen(oid):
            if not self.receta_disponible(r):
                continue
            probs = probabilidades(r, self.nivel(r["profesion"]), self.cat, self.aj)
            unidades = probs["salidas"].get(int(oid), 0.0)
            if unidades <= 0:
                continue
            total = 0.0
            for ing, cantidad in r["ingredientes"]:
                coste, _, _, ok = self.coste(ing, pila)
                completo = completo and ok
                if coste is None:
                    total = None
                    break
                total += coste * cantidad
            if total is None:
                continue
            unitario = total / unidades
            if mejor is None or unitario < mejor:
                mejor, mejor_id = unitario, r["id"]
        return mejor, mejor_id, completo

    def coste(self, oid, pila=frozenset()):
        """(coste, origen, receta_id, completo). `completo`=False if a cycle was cut
        (then it is not memoized, because the value depends on the branch)."""
        oid = int(oid)
        if oid in self._memo:
            return self._memo[oid] + (True,)
        if oid in pila:
            return None, None, None, False
        opciones = []
        precio = self.precio_mercado(oid)
        if precio is not None:
            opciones.append((precio, "mercado", None))
        precio = self.precio_npc(oid)
        if precio is not None:
            opciones.append((precio, "npc", None))
        fabricar, receta_id, completo = self.coste_fabricar(oid, pila)
        if fabricar is not None:
            opciones.append((fabricar, "fabricar", receta_id))
        mejor = min(opciones, key=lambda o: (o[0], ORDEN_ORIGEN[o[1]])) if opciones else (None, None, None)
        if completo:
            self._memo[oid] = mejor
        return mejor + (completo,)

    def antiguedad_horas(self, oid):
        fecha = campo(self.info(oid), "fecha")
        if fecha is None:
            return None
        return (self.ahora - a_utc(fecha)).total_seconds() / 3600.0


def coste_adquisicion(objeto_id, cat, precios, ajustes=None, niveles=None, faccion=None,
                      inventario=None, precios_npc=None, _ctx=None):
    """Cheapest unit cost of getting an item: market, NPC or crafting it.

    With inventory and valorar_inventario="cero" owned units cost 0; with "mercado"
    they are valued at their market price (opportunity cost). Returns (coste, origen, receta_id).
    """
    ctx = _ctx or _Contexto(cat, precios, ajustes, niveles, faccion, precios_npc)
    if inventario and inventario.get(int(objeto_id), inventario.get(str(objeto_id), 0)) > 0:
        if ctx.aj["valorar_inventario"] == "cero":
            return 0.0, "inventario", None
        precio = ctx.precio_mercado(objeto_id)
        if precio is None:
            precio = ctx.coste(objeto_id)[0]
        return precio, "inventario", None
    coste, origen, receta_id, _ = ctx.coste(objeto_id)
    return coste, origen, receta_id


# --- tiered supply -----------------------------------------------------------

def _tramos(ctx, oid, en_inventario, pila):
    """Sources of an ingredient sorted by cost: [(precio, cantidad, origen, receta_id)].
    Returns (tramos, stock_conocido)."""
    tramos = []
    precio_mercado = ctx.precio_mercado(oid)
    if en_inventario > 0:
        if ctx.aj["valorar_inventario"] == "cero":
            coste_inv = 0.0
        else:
            coste_inv = precio_mercado if precio_mercado is not None else ctx.coste(oid, pila)[0]
        tramos.append((coste_inv if coste_inv is not None else 0.0, en_inventario, "inventario", None))

    resto, stock_conocido = [], True
    info = ctx.info(oid)
    ofertas = [(float(p), int(c)) for p, c in (campo(info, "ofertas") or [])
               if p is not None and c and int(c) > 0]
    if ofertas:
        resto += [(p, c, "mercado", None) for p, c in ofertas]
    elif precio_mercado is not None:
        total = campo(info, "cantidad_total")
        if total:
            resto.append((precio_mercado, int(total), "mercado", None))
        else:
            resto.append((precio_mercado, INF, "mercado", None))
            stock_conocido = False
    precio_npc = ctx.precio_npc(oid)
    if precio_npc is not None:
        resto.append((precio_npc, INF, "npc", None))
    fabricar, receta_id, _ = ctx.coste_fabricar(oid, pila)
    if fabricar is not None:
        resto.append((fabricar, INF, "fabricar", receta_id))
    resto.sort(key=lambda t: (t[0], ORDEN_ORIGEN[t[2]]))
    # after the first unlimited source, the rest are not needed
    recortado = []
    for t in resto:
        recortado.append(t)
        if t[1] == INF:
            break
    return tramos + recortado, stock_conocido


def _comprar(tramos, unidades):
    """Cost of getting `unidades` by walking through the tiers.
    Returns (coste, {origen: unidades}, faltan_en_mercado, receta_id_fabricar)."""
    coste, por_origen, restantes, receta_id = 0.0, {}, unidades, None
    for precio, cantidad, origen, rid in tramos:
        if restantes <= 0:
            break
        tomar = min(cantidad, restantes)
        coste += precio * tomar
        por_origen[origen] = por_origen.get(origen, 0) + tomar
        if origen == "fabricar":
            receta_id = rid
        restantes -= tomar
    if restantes > 0 and tramos:
        # no more supply: the rest is estimated at the last tier's price
        coste += tramos[-1][0] * restantes
    return coste, por_origen, max(restantes, 0), receta_id


def _max_intentos(lista, ingreso, tope=1_000_000):
    """Profitable attempts with the available supply (marginal cost by tiers).
    lista = [(tramos, cantidad_por_intento)]. None = no known limit."""
    estado = [[0, t[0][1] if t else 0] for t, _ in lista]
    if any(not t for t, _ in lista):
        return 0
    n = 0
    while n < tope:
        # how many consecutive attempts at a constant marginal cost?
        bloque, marginal, lento = INF, 0.0, False
        for (tramos, q), st in zip(lista, estado):
            while st[0] < len(tramos) and st[1] <= 0:
                st[0] += 1
                st[1] = tramos[st[0]][1] if st[0] < len(tramos) else 0
            if st[0] >= len(tramos):
                return n
            if st[1] >= q:
                bloque = min(bloque, st[1] // q if st[1] != INF else INF)
                marginal += tramos[st[0]][0] * q
            else:
                lento = True
        if lento:
            # an attempt that crosses tiers: simulated on a copy
            marginal, copia = 0.0, [list(s) for s in estado]
            for (tramos, q), st in zip(lista, copia):
                falta = q
                while falta > 0:
                    if st[0] >= len(tramos):
                        return n
                    tomar = min(st[1], falta)
                    marginal += tramos[st[0]][0] * tomar
                    st[1] -= tomar
                    falta -= tomar
                    if st[1] <= 0:
                        st[0] += 1
                        st[1] = tramos[st[0]][1] if st[0] < len(tramos) else 0
            if ingreso is not None and marginal >= ingreso:
                return n
            estado = copia
            n += 1
            continue
        if ingreso is not None and marginal >= ingreso:
            return n
        if bloque == INF:
            return None
        bloque = min(bloque, tope - n)
        for (tramos, q), st in zip(lista, estado):
            st[1] -= bloque * q
        n += bloque
    return n


# --- recipe analysis ---------------------------------------------------------

def analizar_receta(receta, cat, precios, ajustes, nivel, inventario=None, intentos=1, *,
                    niveles=None, faccion=None, precios_npc=None, ahora=None, _ctx=None) -> dict:
    """Expected profitability of `intentos` attempts of a recipe."""
    if _ctx is None:
        niveles = dict(niveles or {})
        niveles.setdefault(receta["profesion"], nivel)
        if faccion is None and receta.get("faccion") not in ("ambas", None):
            faccion = receta.get("faccion")
        _ctx = _Contexto(cat, precios, ajustes, niveles, faccion, precios_npc, ahora)
    ctx, aj, c = _ctx, _ctx.aj, _ctx.cat
    inventario = inventario or {}
    intentos = max(1, int(intentos))
    avisos = []

    probs = probabilidades(receta, nivel, c, aj)
    producto = int(receta["producto"])
    if not probs["desbloqueada"]:
        avisos.append(f"Receta bloqueada: requiere nivel {receta.get('nivel')} (tienes {nivel}).")
    if not probs["curvas_conocidas"]:
        avisos.append("Curva de éxito desconocida en el catálogo: se asume 100%.")

    # ingredients
    pila = frozenset(probs["salidas"].keys())
    desglose, lista_tramos, edades = [], [], []
    coste_total, coste_faltante, sin_precio = 0.0, 0.0, False
    intentos_con_inventario = INF
    for ing, q in receta["ingredientes"]:
        ing = int(ing)
        tengo = int(inventario.get(ing, inventario.get(str(ing), 0)) or 0)
        necesarias = q * intentos
        tramos, _ = _tramos(ctx, ing, tengo, pila)
        intentos_con_inventario = min(intentos_con_inventario, tengo // q if q else INF)
        fila = {"id": ing, "nombre": c.nombre(ing), "cantidad": q, "unidades_necesarias": necesarias,
                "en_inventario": tengo, "faltan": max(0, necesarias - tengo)}
        if not tramos:
            sin_precio = True
            avisos.append(f"Sin precio para {c.nombre(ing)}: no se puede calcular el coste.")
            fila.update(origen=None, origenes={}, coste_unit=None, coste_total=None,
                        coste_faltante=None, receta_id=None)
            desglose.append(fila)
            continue
        lista_tramos.append((tramos, q))
        coste, por_origen, sin_stock, receta_id = _comprar(tramos, necesarias)
        coste_inv = _comprar(tramos, min(tengo, necesarias))[0] if tengo else 0.0
        if sin_stock:
            avisos.append(f"No hay suficientes {c.nombre(ing)} en el mercado para {intentos} intentos "
                          f"(faltan {sin_stock}); se estiman al último precio visto.")
        if por_origen.get("mercado"):
            edad = ctx.antiguedad_horas(ing)
            if edad is not None:
                edades.append((edad, ing))
        origen = max(por_origen, key=lambda o: (por_origen[o], -ORDEN_ORIGEN[o])) if por_origen else None
        coste_total += coste
        coste_faltante += coste - coste_inv
        fila.update(origen=origen, origenes=por_origen, coste_unit=coste / necesarias,
                    coste_total=coste, coste_faltante=coste - coste_inv, receta_id=receta_id)
        desglose.append(fila)

    coste_intento = None if sin_precio else coste_total / intentos
    if sin_precio:
        coste_total = coste_faltante = None

    # sale
    neto = 1 - float(aj["comision_registro"]) - float(aj["impuesto_venta"])
    rebaja = float(aj["rebaja_listado"])
    precio_base = ctx.precio_mercado(producto)
    precio_venta = precio_base - rebaja if precio_base is not None else None
    ingreso = None
    if precio_venta is None:
        avisos.append(f"Sin precio de venta para {c.nombre(producto)}.")
    else:
        ingreso = 0.0
        for pid, unidades in probs["salidas"].items():
            if unidades <= 0:
                continue
            precio_pid = ctx.precio_mercado(pid)
            if precio_pid is None:
                avisos.append(f"Sin precio para {c.nombre(pid)} (combo): se valora como {c.nombre(producto)}.")
                precio_pid = precio_base
            ingreso += unidades * (precio_pid - rebaja) * neto
        for pid in probs["salidas"]:
            edad = ctx.antiguedad_horas(pid)
            if edad is not None:
                edades.append((edad, pid))

    beneficio_intento = margen = beneficio_total = precio_equilibrio = coste_por_objeto = None
    items = probs["items_esperados"]
    if coste_intento is not None and items > 0:
        coste_por_objeto = coste_intento / items
        precio_equilibrio = coste_por_objeto / neto if neto > 0 else None
    if coste_intento is not None and ingreso is not None:
        beneficio_intento = ingreso - coste_intento
        beneficio_total = ingreso * intentos - coste_total
        margen = beneficio_intento / coste_intento if coste_intento > 0 else None

    max_intentos = None if sin_precio else _max_intentos(lista_tramos, ingreso)

    # market warnings
    limite = float(aj["horas_precio_antiguo"])
    for edad, oid in sorted(set(edades), reverse=True):
        if edad > limite:
            avisos.append(f"Precio de {c.nombre(oid)} antiguo ({edad:.0f} h).")
    antiguedad = max((e for e, _ in edades), default=None)

    info_producto = ctx.info(producto)
    anuncios = campo(info_producto, "num_anuncios")
    en_oferta = campo(info_producto, "cantidad_total")
    volumen_dia = campo(info_producto, "volumen_dia")
    if anuncios is not None and anuncios >= int(aj["anuncios_saturado"]):
        avisos.append(f"Producto saturado: {anuncios} anuncios activos de {c.nombre(producto)}.")
    elif volumen_dia and en_oferta and en_oferta > float(aj["dias_saturado"]) * float(volumen_dia):
        avisos.append(f"Producto saturado: {en_oferta} en oferta y se venden ~{float(volumen_dia):.1f}/día.")
    unidades_venta = math.ceil(items * intentos - 1e-9)
    anuncios_necesarios = math.ceil(unidades_venta / max(1, int(aj["unidades_por_anuncio"])))
    if anuncios_necesarios > int(aj["max_anuncios"]):
        avisos.append(f"Producirás ~{unidades_venta} unidades: necesitarás {anuncios_necesarios} anuncios "
                      f"y el máximo es {aj['max_anuncios']} a la vez.")

    # inventory
    intentos_con_inventario = 0 if intentos_con_inventario == INF else int(intentos_con_inventario)
    faltan = [{"id": f["id"], "nombre": f["nombre"], "faltan": f["faltan"], "coste": f["coste_faltante"]}
              for f in desglose if f["faltan"] > 0]
    mensaje = None
    if inventario:
        mensaje = f"Puedes hacer {intentos_con_inventario} intento(s) ya con tu inventario."
        if faltan:
            partes = ", ".join(f"{f['faltan']}× {f['nombre']}" for f in faltan)
            coste_txt = f" (coste {fmt(coste_faltante)} Kinah)" if coste_faltante is not None else ""
            mensaje += f" Para {intentos} intento(s) te faltan: {partes}{coste_txt}."

    return {
        "receta_id": receta.get("id"),
        "producto": producto,
        "nombre": c.nombre(producto),
        "profesion": receta.get("profesion"),
        "nivel_receta": receta.get("nivel"),
        "nivel": nivel,
        "desbloqueada": probs["desbloqueada"],
        "intentos": intentos,
        "p_exito": probs["p_exito"],
        "p_exito_simple": probs["p_exito_simple"],
        "p_combo_activado": probs["p_combo_activado"],
        "p_combo": probs["p_combo"],
        "p_combo_fallido": probs["p_combo_fallido"],
        "items_esperados": items,
        "salidas_esperadas": probs["salidas"],
        "coste_intento": coste_intento,
        "coste_total": coste_total,
        "coste_por_objeto": coste_por_objeto,
        "precio_venta": precio_venta,
        "ingreso_esperado": ingreso,
        "beneficio_intento": beneficio_intento,
        "beneficio_total": beneficio_total,
        "margen": margen,
        "precio_equilibrio": precio_equilibrio,
        "desglose_ingredientes": desglose,
        "max_intentos_mercado": max_intentos,
        "intentos_con_inventario": intentos_con_inventario,
        "faltan": faltan,
        "coste_faltante": coste_faltante,
        "mensaje_inventario": mensaje,
        "avisos": avisos,
        "antiguedad_precios_horas": antiguedad,
    }


# --- panel -------------------------------------------------------------------

FILTROS_POR_DEFECTO = {
    "profesion": None,            # str or list of keys
    "inversion_max": None,        # Kinah to spend (what you don't have in inventory)
    "margen_min": None,           # fraction (0.10 = 10%)
    "incluir_intermedios": True,  # products that are ingredients of other recipes
    "solo_desbloqueadas": True,
    "solo_rentables": True,
    "incluir_sin_precio": False,
    "tope_intentos": None,        # defaults to ajustes["tope_intentos"]
    "ordenar_por": "beneficio_total",  # | "beneficio_intento" | "margen"
    "limite": None,
}


def mejores_oportunidades(cat, precios, ajustes, niveles, faccion, inventario=None, filtros=None, *,
                          precios_npc=None, ahora=None) -> list:
    """Faction recipes sorted by expected profit, with recommended attempts."""
    f = dict(FILTROS_POR_DEFECTO)
    f.update({k: v for k, v in (filtros or {}).items() if v is not None})
    ctx = _Contexto(cat, precios, ajustes, niveles, faccion, precios_npc, ahora)
    tope = int(f["tope_intentos"] or ctx.aj["tope_intentos"])
    profesiones = f["profesion"]
    if isinstance(profesiones, str):
        profesiones = [profesiones]

    def analizar(r, n):
        return analizar_receta(r, ctx.cat, precios, ajustes, ctx.nivel(r["profesion"]), inventario,
                               n, _ctx=ctx)

    def inversion(a):
        return a["coste_faltante"] if inventario else a["coste_total"]

    resultado = []
    for r in ctx.cat.recetas_de(faccion):
        if profesiones and r["profesion"] not in profesiones:
            continue
        if f["solo_desbloqueadas"] and not ctx.receta_disponible(r):
            continue
        intermedio = ctx.cat.es_intermedio(r["producto"])
        if intermedio and not f["incluir_intermedios"]:
            continue
        a = analizar(r, 1)
        if a["beneficio_intento"] is None:
            if f["incluir_sin_precio"]:
                a.update(intentos_recomendados=0, inversion=None, es_intermedio=intermedio)
                resultado.append(a)
            continue
        if f["solo_rentables"] and a["beneficio_intento"] <= 0:
            continue
        if f["margen_min"] is not None and (a["margen"] is None or a["margen"] < f["margen_min"]):
            continue
        if f["inversion_max"] is not None and inversion(a) > f["inversion_max"]:
            continue

        n = tope if a["max_intentos_mercado"] is None else min(tope, a["max_intentos_mercado"])
        n = max(n, 1)
        if f["inversion_max"] is not None and n > 1:
            bajo, alto = 1, n  # largest n with investment <= maximum
            while bajo < alto:
                medio = (bajo + alto + 1) // 2
                if inversion(analizar(r, medio)) <= f["inversion_max"]:
                    bajo = medio
                else:
                    alto = medio - 1
            n = bajo
        if n > 1:
            a = analizar(r, n)
        a.update(intentos_recomendados=n, inversion=inversion(a), es_intermedio=intermedio)
        resultado.append(a)

    clave = f["ordenar_por"]
    resultado.sort(key=lambda a: a.get(clave) if a.get(clave) is not None else -INF, reverse=True)
    if f["limite"]:
        resultado = resultado[: int(f["limite"])]
    return resultado
