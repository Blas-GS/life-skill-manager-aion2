"""Target sell/buy price from the history of market readings.

Readings can be `Lectura` objects (app/db.py) or dicts with the same fields:
they are read by duck typing, so this module does not depend on app/db.py.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

AJUSTES_PRECIO_POR_DEFECTO = {
    "rebaja_listado": 1,            # Kinah below the cheapest listing when listing
    "dias_saturado": 7,             # saturated if more than N days of sales are on offer
    "rebaja_saturado_pct": 0.03,    # extra undercut (fraction) when the product is saturated
    "min_lecturas_historico": 3,    # below this, percentiles are not computed
    "horas_min_volumen": 12,        # minimum history span needed to trust the volume
}


# --- shared utilities (also used by app/calculo.py) --------------------------

def fmt(numero, decimales=0) -> str:
    """Spanish number format: 272.565,70"""
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def campo(obj, nombre, defecto=None):
    """Reads a field from a dict or an object (Lectura, InfoPrecio...)."""
    if obj is None:
        return defecto
    if isinstance(obj, dict):
        valor = obj.get(nombre, defecto)
    else:
        valor = getattr(obj, nombre, defecto)
    return defecto if valor is None else valor


def a_utc(fecha):
    """datetime/ISO str -> UTC-aware datetime (naive dates are taken as UTC)."""
    if fecha is None:
        return None
    if isinstance(fecha, str):
        texto = fecha.strip()
        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"
        fecha = datetime.fromisoformat(texto)
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def percentil(valores, p):
    """Percentile with linear interpolation (same as numpy.percentile by default)."""
    datos = sorted(valores)
    if not datos:
        return None
    if len(datos) == 1:
        return float(datos[0])
    pos = (len(datos) - 1) * p / 100.0
    i = math.floor(pos)
    j = min(i + 1, len(datos) - 1)
    return datos[i] + (datos[j] - datos[i]) * (pos - i)


def _ajustes(ajustes):
    resultado = dict(AJUSTES_PRECIO_POR_DEFECTO)
    for clave, valor in (ajustes or {}).items():
        if valor is not None:
            resultado[clave] = valor
    return resultado


def _ordenadas(historico):
    lecturas = [l for l in (historico or []) if campo(l, "fecha") is not None]
    return sorted(lecturas, key=lambda l: a_utc(campo(l, "fecha")))


def _precios(lecturas):
    return [float(campo(l, "precio_min")) for l in lecturas
            if campo(l, "precio_min") is not None and float(campo(l, "precio_min")) > 0]


# --- volume ------------------------------------------------------------------

def _volumen(historico):
    """(units/day, hours covered). Drops in cantidad_total count as sales."""
    lecturas = [l for l in _ordenadas(historico) if campo(l, "cantidad_total") is not None]
    if len(lecturas) < 2:
        return 0.0, 0.0
    vendidas = 0
    for anterior, actual in zip(lecturas, lecturas[1:]):
        caida = int(campo(anterior, "cantidad_total")) - int(campo(actual, "cantidad_total"))
        if caida > 0:
            vendidas += caida
    segundos = (a_utc(campo(lecturas[-1], "fecha")) - a_utc(campo(lecturas[0], "fecha"))).total_seconds()
    if segundos <= 0:
        return 0.0, 0.0
    return vendidas / (segundos / 86400.0), segundos / 3600.0


def volumen_estimado(historico) -> float:
    """Estimated units sold per day = sum of drops in cantidad_total / days covered."""
    return _volumen(historico)[0]


# --- sell price --------------------------------------------------------------

def _unidades_por_delante(actual, precio):
    """Units on offer cheaper than `precio` (they will sell before ours)."""
    ofertas = campo(actual, "ofertas") or []
    if ofertas:
        return sum(int(c) for p, c in ofertas if p is not None and c and float(p) < precio)
    precio_min = campo(actual, "precio_min")
    if precio_min is not None and float(precio_min) < precio:
        return int(campo(actual, "cantidad_total", 0))
    return 0


def precio_objetivo_venta(historico, actual=None, ajustes=None, *, unidades=1,
                          ventana_dias=None, ahora=None) -> dict:
    """Recommended price for listing an item.

    - normal: current price within or above P25–P75 → just below the cheapest listing.
    - hundido (crashed): current < P25 → recommend the median and wait.
    - saturado (saturated): on offer > dias_saturado × sales/day → more aggressive price.
    - sin_datos (no data): not enough history.
    """
    aj = _ajustes(ajustes)
    lecturas = _ordenadas(historico)
    if ventana_dias is not None and lecturas:
        ref = a_utc(ahora) if ahora else a_utc(campo(lecturas[-1], "fecha"))
        desde = ref - timedelta(days=ventana_dias)
        lecturas = [l for l in lecturas if a_utc(campo(l, "fecha")) >= desde]
    if actual is None and lecturas:
        actual = lecturas[-1]

    rebaja = float(aj["rebaja_listado"])
    precios = _precios(lecturas)
    precio_actual = campo(actual, "precio_min")
    precio_actual = float(precio_actual) if precio_actual is not None else None
    en_oferta = campo(actual, "cantidad_total")

    velocidad, horas = _volumen(lecturas)
    velocidad = velocidad if horas >= float(aj["horas_min_volumen"]) else None

    resultado = {
        "precio_recomendado": None, "rango_p25": None, "mediana": None, "rango_p75": None,
        "estado": "sin_datos", "velocidad_dia": velocidad, "dias_para_vender": None,
        "aviso": None, "precio_actual": precio_actual, "cantidad_en_oferta": en_oferta,
        "n_lecturas": len(precios),
    }

    def dias(precio):
        if not velocidad or precio is None:
            return None
        return (_unidades_por_delante(actual, precio) + unidades) / velocidad

    if len(precios) < int(aj["min_lecturas_historico"]):
        if precio_actual is None:
            resultado["aviso"] = "Sin datos de mercado para este objeto."
            return resultado
        recomendado = max(1, math.floor(precio_actual - rebaja))
        resultado.update(precio_recomendado=recomendado, dias_para_vender=dias(recomendado),
                         aviso="Histórico insuficiente: se usa el precio actual.")
        return resultado

    p25, mediana, p75 = percentil(precios, 25), percentil(precios, 50), percentil(precios, 75)
    resultado.update(rango_p25=p25, mediana=mediana, rango_p75=p75)
    if precio_actual is None:
        precio_actual = precios[-1]
        resultado["precio_actual"] = precio_actual

    saturado = (velocidad is not None and en_oferta is not None and en_oferta > 0
                and en_oferta > float(aj["dias_saturado"]) * velocidad)
    texto_saturado = None
    if saturado:
        if velocidad > 0:
            texto_saturado = (f"Mercado saturado: hay {en_oferta} unidades en oferta y se venden "
                              f"~{velocidad:.1f}/día (≈{en_oferta / velocidad:.0f} días para vaciarlo).")
        else:
            texto_saturado = f"Mercado saturado: hay {en_oferta} unidades en oferta y no se ha detectado ninguna venta."

    if precio_actual < p25:
        recomendado = max(1, round(mediana))
        aviso = (f"Precio hundido: el actual ({fmt(precio_actual)}) está por debajo de lo normal "
                 f"(P25 {fmt(p25)}). Mejor listar en torno a la mediana ({fmt(mediana)}) y esperar, "
                 f"o no fabricar todavía.")
        if texto_saturado:
            aviso += " " + texto_saturado
        resultado.update(estado="hundido", precio_recomendado=recomendado,
                         dias_para_vender=dias(recomendado), aviso=aviso)
    elif saturado:
        rebaja_sat = max(rebaja, math.ceil(precio_actual * float(aj["rebaja_saturado_pct"])))
        recomendado = max(1, math.floor(precio_actual - rebaja_sat))
        resultado.update(estado="saturado", precio_recomendado=recomendado,
                         dias_para_vender=dias(recomendado),
                         aviso=texto_saturado + f" Precio más agresivo: {fmt(recomendado)}.")
    else:
        recomendado = max(1, math.floor(precio_actual - rebaja))
        aviso = None
        if precio_actual > p75:
            aviso = "El precio actual está por encima de lo habitual: buen momento para vender."
        resultado.update(estado="normal", precio_recomendado=recomendado,
                         dias_para_vender=dias(recomendado), aviso=aviso)
    return resultado


# --- buy price ---------------------------------------------------------------

def precio_objetivo_compra(historico, actual=None, ajustes=None) -> dict:
    """"Buy below X" (≈P25 of the historical minimum price)."""
    aj = _ajustes(ajustes)
    lecturas = _ordenadas(historico)
    if actual is None and lecturas:
        actual = lecturas[-1]
    precios = _precios(lecturas)
    precio_actual = campo(actual, "precio_min")
    precio_actual = float(precio_actual) if precio_actual is not None else None
    if len(precios) < int(aj["min_lecturas_historico"]):
        return {"comprar_por_debajo_de": None, "estado": "sin_datos", "mediana": None,
                "precio_actual": precio_actual, "aviso": "Histórico insuficiente."}
    p25, mediana, p75 = percentil(precios, 25), percentil(precios, 50), percentil(precios, 75)
    if precio_actual is None:
        estado, aviso = "sin_datos", None
    elif precio_actual <= p25:
        estado, aviso = "oportunidad", f"Buen momento para comprar: {fmt(precio_actual)} ≤ {fmt(p25)}."
    elif precio_actual > p75:
        estado, aviso = "caro", "Precio por encima de lo habitual."
    else:
        estado, aviso = "normal", None
    return {"comprar_por_debajo_de": p25, "estado": estado, "mediana": mediana,
            "precio_actual": precio_actual, "aviso": aviso}
