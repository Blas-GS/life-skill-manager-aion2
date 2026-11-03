from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from app.precio_objetivo import (precio_objetivo_compra, precio_objetivo_venta,
                                 volumen_estimado)

INICIO = datetime(2026, 10, 1, tzinfo=timezone.utc)


@dataclass
class Lectura:  # copia local compatible con app/db.py (contrato §2)
    servidor_id: str
    objeto_id: int
    fecha: datetime
    precio_min: float | None
    cantidad_total: int | None
    num_anuncios: int | None
    ofertas: list = field(default_factory=list)
    fuente: str = "manual"
    id: str | None = None


def lectura(horas, precio, cantidad=None, ofertas=None):
    return Lectura("s1", 1, INICIO + timedelta(hours=horas), precio, cantidad, None, ofertas or [])


def historico_normal():
    """30 días, precio entre 900 y 1100, 100 en oferta y ~10 ventas/día (repone cada día)."""
    precios = [900, 950, 1000, 1050, 1100]
    lecturas = []
    for dia in range(30):
        lecturas.append(lectura(dia * 24, precios[dia % 5], 100))
        lecturas.append(lectura(dia * 24 + 12, precios[dia % 5], 90))
    return lecturas


def test_volumen_estimado():
    hist = [lectura(0, 10, 100), lectura(24, 10, 90), lectura(36, 10, 95), lectura(48, 10, 80)]
    assert volumen_estimado(hist) == pytest.approx((10 + 15) / 2)
    assert volumen_estimado([]) == 0.0
    assert volumen_estimado(historico_normal()) == pytest.approx(10 * 30 / (29.5), rel=1e-6)


def test_precio_normal():
    actual = lectura(30 * 24, 1000, 20, ofertas=[(1000, 5), (1010, 15)])
    r = precio_objetivo_venta(historico_normal(), actual, {"rebaja_listado": 1}, unidades=5)
    assert r["estado"] == "normal"
    assert r["precio_recomendado"] == 999
    assert r["rango_p25"] == pytest.approx(950)
    assert r["mediana"] == pytest.approx(1000)
    assert r["rango_p75"] == pytest.approx(1050)
    assert r["dias_para_vender"] == pytest.approx(5 / r["velocidad_dia"])


def test_precio_hundido():
    actual = lectura(30 * 24, 700, 20, ofertas=[(700, 5), (1010, 15)])
    r = precio_objetivo_venta(historico_normal() + [actual], actual, None, unidades=2)
    assert r["estado"] == "hundido"
    assert r["precio_recomendado"] == 1000  # mediana
    assert "esperar" in r["aviso"]
    # para vender a 1000 hay 5 unidades más baratas por delante
    assert r["dias_para_vender"] == pytest.approx((5 + 2) / r["velocidad_dia"])


def test_precio_saturado():
    actual = lectura(30 * 24, 1000, 5000)
    r = precio_objetivo_venta(historico_normal(), actual, {"rebaja_listado": 1}, unidades=10)
    assert r["estado"] == "saturado"
    assert r["precio_recomendado"] == 970  # 3% por debajo
    assert "saturado" in r["aviso"].lower()
    assert r["dias_para_vender"] is not None


def test_sin_datos():
    r = precio_objetivo_venta([], None, None)
    assert r["estado"] == "sin_datos" and r["precio_recomendado"] is None
    r = precio_objetivo_venta([], lectura(0, 500, 3), {"rebaja_listado": 1})
    assert r["estado"] == "sin_datos" and r["precio_recomendado"] == 499


def test_ventana_dias():
    hist = historico_normal()
    r = precio_objetivo_venta(hist, hist[-1], None, ventana_dias=7)
    assert r["n_lecturas"] == 14 or r["n_lecturas"] == 15


def test_acepta_dicts():
    hist = [{"fecha": (INICIO + timedelta(days=d)).isoformat(), "precio_min": 100 + d,
             "cantidad_total": 50 - 5 * d} for d in range(5)]
    r = precio_objetivo_venta(hist, None, None)
    assert r["estado"] == "normal" and r["precio_recomendado"] == 103
    assert r["velocidad_dia"] == pytest.approx(5)
    # sin ninguna venta detectada en 4 días → saturado
    for l in hist:
        l["cantidad_total"] = 50
    assert precio_objetivo_venta(hist, None, None)["estado"] == "saturado"


def test_precio_objetivo_compra():
    hist = historico_normal()
    assert precio_objetivo_compra(hist, lectura(999, 900))["estado"] == "oportunidad"
    assert precio_objetivo_compra(hist, lectura(999, 1000))["estado"] == "normal"
    assert precio_objetivo_compra(hist, lectura(999, 1200))["estado"] == "caro"
    assert precio_objetivo_compra(hist, None)["comprar_por_debajo_de"] == pytest.approx(950)
    assert precio_objetivo_compra([], None)["estado"] == "sin_datos"
