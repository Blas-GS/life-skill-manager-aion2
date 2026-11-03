"""Tests de OCR (Windows.Media.Ocr) + parser con pantallas sintéticas del mercado,
vídeo sintético, modo grabación (con fuente falsa), vigilante y calibración."""
import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("winrt.windows.media.ocr")

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "capturas"))
import sintetico  # noqa: E402

from app.captura import calibracion, ocr, parser, temporales  # noqa: E402
from app.captura.grabacion import Deduplicador, SesionGrabacion, procesar_imagen  # noqa: E402
from app.captura.video import procesar_video  # noqa: E402
from app.captura.vigilante import Vigilante  # noqa: E402

CAT = sintetico.CATALOGO
ID = {v: k for k, v in CAT.items()}
INDICE = parser.IndiceNombres(CAT)

BASICO = [
    ("Mineral de orichalcum", 12500, 35),
    ("Okra", 850, 120),
    ("Esencia de Balaur", 1234567, 2),
    ("Od", 45, 999),
    ("Solomillo wellington de dragón oscuro", 98000, 5),
]


def completa(img):
    return (0, 0, img.width, img.height)


def leidas(filas):
    return {(f["objeto_id"], f["precio"], f["cantidad"]) for f in filas if not f["dudosa"]}


def esperadas(filas):
    return {(ID[n], p, c) for n, p, c in filas}


# ---------------------------------------------------------------- OCR
def test_idiomas_instalados():
    idiomas = ocr.idiomas_disponibles()
    assert "es-ES" in idiomas or "en-US" in idiomas


def test_preprocesado_invierte_fondo_oscuro():
    img = sintetico.pantalla_mercado(BASICO)
    gris, escala = ocr.preprocesar(img)
    assert gris.mode == "L" and escala >= 2
    # Tras invertir, el fondo (mayoría de píxeles) queda claro.
    import numpy as np

    assert float(np.median(np.asarray(gris))) > 128


def test_leer_imagen_devuelve_lineas_y_cajas_en_coordenadas_originales():
    img = sintetico.pantalla_mercado(BASICO)
    lineas = ocr.leer_imagen(img)
    texto = " ".join(l["texto"] for l in lineas).lower()
    assert "orichalcum" in texto and "balaur" in texto
    for l in lineas:
        assert set(l) >= {"texto", "x", "y", "w", "h", "palabras"}
        assert 0 <= l["x"] < img.width and 0 <= l["y"] < img.height
        assert l["x"] + l["w"] <= img.width + 2


def test_region_desplaza_las_coordenadas():
    img = sintetico.pantalla_mercado(BASICO)
    region = (60, 110, 1000, img.height - 130)  # sin título ni cabecera
    lineas = ocr.leer_imagen(img, region=region)
    assert lineas
    assert all(l["y"] >= region[1] - 1 and l["x"] >= region[0] - 1 for l in lineas)
    assert "mercado" not in " ".join(l["texto"] for l in lineas).lower()


def test_ocr_funciona_dentro_de_un_bucle_asyncio_y_en_hilos():
    img = sintetico.pantalla_mercado(BASICO[:2])

    async def dentro_de_bucle():
        return ocr.leer_imagen(img)

    assert asyncio.run(dentro_de_bucle())
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(ocr.leer_imagen(img))) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(60)
    assert len(resultados) == 3 and all(resultados)


# ---------------------------------------------------------------- OCR + parser
def test_pantalla_basica_recupera_todos_los_valores():
    img = sintetico.pantalla_mercado(BASICO)
    filas = procesar_imagen(img, INDICE, region=completa(img))
    assert leidas(filas) == esperadas(BASICO)


CONFIGS = [
    dict(tam_fuente=19, ruta_fuente="C:/Windows/Fonts/segoeui.ttf"),
    dict(tam_fuente=19, ruta_fuente="C:/Windows/Fonts/arial.ttf"),
    dict(tam_fuente=15, alto_fila=34, ruta_fuente="C:/Windows/Fonts/segoeui.ttf"),
    dict(tam_fuente=13, alto_fila=28, ruta_fuente="C:/Windows/Fonts/tahoma.ttf"),
]


def test_precision_sintetica():
    """Varias fuentes y tamaños: ≥ 95 % de filas correctas y NINGUNA fila
    incorrecta sin marcar como dudosa."""
    total = correctas = incorrectas_no_dudosas = 0
    for ci, cfg in enumerate(CONFIGS):
        for semilla in range(3):
            filas = sintetico.filas_aleatorias(12, semilla=semilla * 10 + ci)
            img = sintetico.pantalla_mercado(filas, semilla=semilla, **cfg)
            res = procesar_imagen(img, INDICE, region=completa(img))
            esp = esperadas(filas)
            ok = leidas(res)
            total += len(filas)
            correctas += sum(1 for n, p, c in filas if (ID[n], p, c) in ok)
            incorrectas_no_dudosas += len(ok - esp)
    precision = correctas / total
    print(f"\nPrecisión sintética: {correctas}/{total} = {precision:.1%}; "
          f"incorrectas sin marcar: {incorrectas_no_dudosas}")
    assert precision >= 0.95
    assert incorrectas_no_dudosas == 0


def test_numeros_con_confusiones_reales_de_fuente():
    # Precios con muchos 0/1/5/8, que el OCR suele confundir con O/l/S/B.
    filas = [("Okra frita", 1015008, 11), ("Od", 100, 88), ("Lingote de orichalcum", 50510, 1)]
    img = sintetico.pantalla_mercado(filas)
    res = procesar_imagen(img, INDICE, region=completa(img))
    assert leidas(res) == esperadas(filas)


# ---------------------------------------------------------------- deduplicado
def test_deduplicador_detecta_cambio_de_un_solo_precio():
    a = sintetico.pantalla_mercado(BASICO)
    b = sintetico.pantalla_mercado([BASICO[0], ("Okra", 851, 120)] + BASICO[2:])
    d = Deduplicador()
    assert d.evaluar(a) is False      # primer fotograma: aún no se sabe si es estable
    assert d.evaluar(a) is True       # estable y nuevo → OCR
    assert d.evaluar(a) is False      # repetido
    assert d.evaluar(b) is False      # acaba de cambiar (podría estar en movimiento)
    assert d.evaluar(b) is True       # estable y distinto (solo cambió un dígito)
    assert (d.vistos, d.procesados) == (5, 2)


# ---------------------------------------------------------------- vídeo
def _escribir_video(ruta, pantallas, fps=10):
    import cv2
    import numpy as np

    w, h = pantallas[0][0].size
    vw = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    assert vw.isOpened()
    for img, segundos in pantallas:
        bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        for _ in range(int(segundos * fps)):
            vw.write(bgr)
    vw.release()


def test_procesar_video_sintetico(tmp_path):
    lista = sintetico.filas_aleatorias(14, semilla=3)
    # Dos "pantallas" con scroll: filas 0–7 y 5–12 (se solapan 5,6,7).
    a = sintetico.pantalla_mercado(lista[0:8])
    b = sintetico.pantalla_mercado(lista[5:13])
    ruta = tmp_path / "mercado.avi"
    _escribir_video(ruta, [(a, 2.0), (b, 2.0), (a, 1.0)])
    filas, est = procesar_video(ruta, CAT, region=completa(a), guardar_recortes=False,
                                devolver_estadisticas=True)
    # ~3 fotogramas/s de 5 s → ~15 muestreados; solo 3 pantallas distintas con OCR.
    assert 12 <= est["muestreados"] <= 18
    assert est["procesados"] == 3
    libro = parser.agrupar_libro(filas)
    esperado = parser.agrupar_libro(
        [{"objeto_id": ID[n], "precio": p, "cantidad": c, "dudosa": False, "nombre": n} for n, p, c in lista[:13]]
    )
    aciertos = sum(1 for oid in esperado if libro.get(oid, {}).get("ofertas") == esperado[oid]["ofertas"])
    assert aciertos >= len(esperado) - 1
    # El solapamiento del scroll no duplica anuncios.
    assert sum(l["num_anuncios"] for l in libro.values()) <= 13


# ---------------------------------------------------------------- grabación
def test_sesion_grabacion_con_fuente_falsa():
    lista = sintetico.filas_aleatorias(10, semilla=11)
    a = sintetico.pantalla_mercado(lista[:6])
    b = sintetico.pantalla_mercado(lista[4:10])
    secuencia = [a] * 4 + [b] * 4 + [a] * 2
    it = iter(secuencia)
    sesion = SesionGrabacion(fps=50, cat=CAT, region=completa(a), fuente=lambda: next(it, None),
                             guardar_recortes=False)
    sesion.iniciar()
    t0 = time.time()
    while sesion.activa and time.time() - t0 < 60:
        time.sleep(0.05)
    filas = sesion.detener()
    est = sesion.estado()
    assert est["fotogramas_vistos"] == 10 and est["fotogramas_procesados"] == 3
    ok = leidas(filas)
    assert len(ok & esperadas(lista)) >= len(esperadas(lista)) - 1
    assert len(ok - esperadas(lista)) == 0


def test_sesion_grabacion_informa_errores():
    def rota():
        raise OSError("pantalla no disponible")

    sesion = SesionGrabacion(fps=5, cat=CAT, region=(0, 0, 10, 10), fuente=rota).iniciar()
    time.sleep(0.3)
    with pytest.raises(RuntimeError, match="pantalla no disponible"):
        sesion.detener()


# ---------------------------------------------------------------- vigilante
def test_vigilante_procesa_capturas_nuevas_una_vez(tmp_path):
    original = temporales.instancia()
    temporales.configurar(tmp_path / "tmp")
    try:
        carpeta = tmp_path / "pendientes"
        carpeta.mkdir()
        leidos = []
        vig = Vigilante(carpeta=carpeta, cat=CAT, al_procesar=lambda r, f: leidos.append((r, f)))
        img = sintetico.pantalla_mercado(BASICO)
        img.save(carpeta / "captura1.png")
        (carpeta / "notas.txt").write_text("no es una imagen")
        assert vig.revisar() == []          # 1ª pasada: espera a que el archivo sea estable
        res = vig.revisar()                 # 2ª pasada: lo procesa
        assert len(res) == 1 and leidas(res[0][1]) == esperadas(BASICO)
        assert vig.revisar() == []          # no se reprocesa
        assert len(leidos) == 1
        # Una captura ya registrada en temporales (guardada) no se procesa.
        img.save(carpeta / "captura2.png")
        temporales.registrar_temporal(carpeta / "captura2.png", ["id"])
        vig.revisar()
        assert vig.revisar() == []
        assert (carpeta / "captura1.png").exists()  # el vigilante nunca borra
    finally:
        temporales._por_defecto = original


# ---------------------------------------------------------------- calibración
def test_calibracion_por_resolucion(tmp_path):
    ruta = tmp_path / "calibracion.json"
    assert calibracion.region_para(1920, 1080, ruta) == (0, 0, 1920, 1080)
    assert calibracion.configuracion_para(1920, 1080, ruta)["calibrada"] is False
    calibracion.guardar_region(1920, 1080, (300, 200, 2000, 700), ruta=ruta,
                               columnas={"nombre": [320, 900], "cantidad": [1000, 1200], "precio": [1300, 1600]})
    # Se recorta a la pantalla.
    assert calibracion.region_para(1920, 1080, ruta) == (300, 200, 1620, 700)
    conf = calibracion.configuracion_para(1920, 1080, ruta)
    assert conf["calibrada"] and conf["columnas"]["precio"] == [1300, 1600]
    assert calibracion.region_para(2560, 1440, ruta) == (0, 0, 2560, 1440)
    with pytest.raises(ValueError):
        calibracion.guardar_region(1920, 1080, (0, 0, 10, 10), columnas={"color": [0, 1]}, ruta=ruta)
    assert calibracion.borrar_region(1920, 1080, ruta)
    assert calibracion.region_para(1920, 1080, ruta) == (0, 0, 1920, 1080)
