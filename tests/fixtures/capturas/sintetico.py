"""Generador de pantallas sintéticas del mercado (fondo oscuro, texto en español).

Imita una lista del mercado de AION 2: icono, nombre (con color según grado),
cantidad y precio unitario con separadores de miles españoles. No es una
captura real: sirve para probar OCR + parser de forma reproducible.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARPETA = Path(__file__).resolve().parent

CATALOGO = {
    610620013: "Mineral de orichalcum",
    610620014: "Lingote de orichalcum",
    630541001: "Okra",
    630541002: "Okra frita",
    620110001: "Esencia de Balaur",
    620110002: "Od",
    620110003: "Polvo de cristal brillante",
    640010001: "Solomillo wellington de dragón oscuro",
    640010002: "Piel de lagarto curtida",
    640010003: "Hilo de seda resistente",
    640010004: "Poción de recuperación de vida",
    640010005: "Fragmento de piedra de maná",
    640010006: "Madera de árbol antiguo",
    640010007: "Cristal de éter puro",
}

COLORES_GRADO = [(235, 235, 235), (120, 220, 110), (100, 160, 255), (240, 190, 70)]
FUENTES = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/tahoma.ttf"]


def miles(n: int) -> str:
    """12500 -> "12.500" (formato español)."""
    return f"{n:,}".replace(",", ".")


def fuente(tam: int, ruta: str | None = None):
    for r in ([ruta] if ruta else []) + FUENTES:
        try:
            return ImageFont.truetype(r, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def filas_aleatorias(n: int, semilla: int = 0) -> list[tuple[str, int, int]]:
    rnd = random.Random(semilla)
    nombres = list(CATALOGO.values())
    filas = []
    for _ in range(n):
        nombre = rnd.choice(nombres)
        precio = rnd.choice([rnd.randint(5, 999), rnd.randint(1000, 99999), rnd.randint(100000, 2500000)])
        cantidad = rnd.choice([1, rnd.randint(2, 50), rnd.randint(51, 999)])
        filas.append((nombre, precio, cantidad))
    return filas


def pantalla_mercado(
    filas: list[tuple[str, int, int]],
    ancho: int = 1100,
    alto_fila: int = 44,
    tam_fuente: int = 19,
    ruta_fuente: str | None = None,
    cabecera: str | None = None,
    margen_sup: int = 70,
    semilla: int = 1,
) -> Image.Image:
    """Lista del mercado: [icono] Nombre ........ Cantidad ...... Precio [moneda]."""
    rnd = random.Random(semilla)
    alto = margen_sup + alto_fila * (len(filas) + 1) + 40
    img = Image.new("RGB", (ancho, alto), (16, 18, 24))
    d = ImageDraw.Draw(img)
    f = fuente(tam_fuente, ruta_fuente)
    fc = fuente(tam_fuente - 2, ruta_fuente)
    # marco y título
    d.rectangle([8, 8, ancho - 8, alto - 8], outline=(70, 60, 40), width=2)
    d.text((24, 22), cabecera or "Mercado", fill=(230, 200, 140), font=f)
    y = margen_sup
    d.text((80, y + 10), "Nombre del objeto", fill=(150, 150, 160), font=fc)
    d.text((620, y + 10), "Cantidad", fill=(150, 150, 160), font=fc)
    d.text((850, y + 10), "Precio unitario", fill=(150, 150, 160), font=fc)
    y += alto_fila
    for i, (nombre, precio, cantidad) in enumerate(filas):
        fondo = (26, 29, 38) if i % 2 == 0 else (21, 23, 31)
        d.rectangle([14, y, ancho - 14, y + alto_fila - 4], fill=fondo)
        # icono
        c = tuple(rnd.randint(60, 200) for _ in range(3))
        d.rectangle([24, y + 5, 24 + alto_fila - 14, y + alto_fila - 9], fill=c, outline=(120, 100, 60))
        ty = y + (alto_fila - 4 - tam_fuente) // 2 - 2
        d.text((80, ty), nombre, fill=rnd.choice(COLORES_GRADO), font=f)
        tc = str(cantidad)
        d.text((700 - d.textlength(tc, font=f), ty), tc, fill=(220, 220, 220), font=f)
        tp = miles(precio)
        d.text((1010 - d.textlength(tp, font=f), ty), tp, fill=(245, 225, 160), font=f)
        # moneda (Kinah)
        d.ellipse([1020, ty + 4, 1020 + tam_fuente - 4, ty + tam_fuente], fill=(200, 160, 60))
        y += alto_fila
    return img


def generar_fixtures() -> list[Path]:
    """Escribe en esta carpeta algunas pantallas de ejemplo (para inspeccionarlas)."""
    rutas = []
    ejemplos = {
        "mercado_basico.png": [
            ("Mineral de orichalcum", 12500, 35),
            ("Okra", 850, 120),
            ("Esencia de Balaur", 1234567, 2),
            ("Od", 45, 999),
            ("Solomillo wellington de dragón oscuro", 98000, 5),
        ],
        "mercado_aleatorio.png": filas_aleatorias(12, semilla=7),
    }
    for nombre, filas in ejemplos.items():
        ruta = CARPETA / nombre
        pantalla_mercado(filas).save(ruta)
        rutas.append(ruta)
    return rutas


if __name__ == "__main__":
    for r in generar_fixtures():
        print(r)
