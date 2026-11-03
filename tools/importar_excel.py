r"""Siembra el histórico con los precios del Excel «aion2-market-place-recipe-book (1).xlsx».

Lee la hoja "Prices" (B = objeto en inglés, C = precio, D = notas; filas 6–88), empareja cada
nombre con `nombre_en` del catálogo (exacto y luego difuso) y guarda:
  - las filas de mercado como lecturas fuente="excel" con fecha 2026-10-09 en el servidor indicado;
  - las filas marcadas como NPC/tienda (o «(Bound)») como precios NPC.
Muestra un informe de lo no emparejado. Es idempotente: no repite lecturas excel de ese día.

Uso:
    .\.venv\Scripts\python.exe tools\importar_excel.py --servidor <id_servidor> [--excel RUTA] [--simular]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

EXCEL_POR_DEFECTO = RAIZ / "aion2-market-place-recipe-book (1).xlsx"
FECHA_EXCEL = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
FILA_INICIO, FILA_FIN = 6, 88
UMBRAL_DIFUSO = 88
# nombres del Excel que no coinciden con el cliente; comprobado con el coste de Okra frita
# del Excel (3×700 + 3×788 + 5×880 = 8.864)
ALIAS = {"oil": "Ulmus Oil (Bound)"}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    texto = texto.replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ()]+", " ", texto)).strip()


def sin_vinculado(texto: str) -> str:
    return re.sub(r"\s*\((bound|vinculado)\)\s*", " ", texto, flags=re.I).strip()


def es_npc(nombre: str, notas: str) -> bool:
    n = (notas or "").lower()
    return "npc" in n or "general shop" in n or "general goods" in n or "(bound)" in (nombre or "").lower()


def leer_excel(ruta: Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(ruta, data_only=True, read_only=True)
    if "Prices" not in wb.sheetnames:
        raise SystemExit(f"El Excel no tiene la hoja «Prices» (hojas: {', '.join(wb.sheetnames)})")
    ws = wb["Prices"]
    filas = []
    for i, (nombre, precio, notas) in enumerate(
            ws.iter_rows(min_row=FILA_INICIO, max_row=FILA_FIN, min_col=2, max_col=4, values_only=True),
            FILA_INICIO):
        if not nombre or not str(nombre).strip():
            continue
        filas.append({"fila": i, "nombre": str(nombre).strip(), "precio": precio, "notas": str(notas or "").strip()})
    wb.close()
    return filas


class Emparejador:
    """Nombre en inglés → id del catálogo."""

    def __init__(self, objetos: dict):
        self.exactos: dict[str, list[int]] = {}
        self.base: dict[str, list[int]] = {}
        self.nombres: dict[int, str] = {}
        self.vinculado: dict[int, bool] = {}
        for k, o in objetos.items():
            en = o.get("nombre_en")
            if not en:
                continue
            oid = int(k)
            self.nombres[oid] = normalizar(en)
            self.vinculado[oid] = bool(o.get("vinculado")) or "(bound)" in en.lower()
            self.exactos.setdefault(normalizar(en), []).append(oid)
            self.base.setdefault(normalizar(sin_vinculado(en)), []).append(oid)

    def _elegir(self, ids: list[int], quiere_vinculado: bool) -> int:
        preferidos = [i for i in ids if self.vinculado.get(i) == quiere_vinculado]
        return sorted(preferidos or ids)[0]

    def buscar(self, nombre: str) -> tuple[int | None, str, float]:
        if normalizar(nombre) in ALIAS:
            oid, _, punt = self.buscar(ALIAS[normalizar(nombre)])
            return oid, f"alias de «{ALIAS[normalizar(nombre)]}»", punt
        quiere_vinc = "(bound)" in nombre.lower()
        n = normalizar(nombre)
        if n in self.exactos:
            return self._elegir(self.exactos[n], quiere_vinc), "exacto", 100.0
        b = normalizar(sin_vinculado(nombre))
        if b in self.base:
            return self._elegir(self.base[b], quiere_vinc), "exacto (sin «Bound»)", 99.0
        from rapidfuzz import fuzz, process

        res = process.extractOne(n, self.nombres, scorer=fuzz.WRatio)
        if res and res[1] >= UMBRAL_DIFUSO:
            # evitar que un nombre corto («Oil») case con uno largo que solo lo contiene
            a, c = len(sin_vinculado(n)), len(sin_vinculado(res[0]))
            if min(a, c) / max(a, c, 1) >= 0.6:
                return int(res[2]), "difuso", float(res[1])
        return None, f"sin emparejar (¿{res[0]}? {res[1]:.0f})" if res else "sin emparejar", float(res[1]) if res else 0.0


def cargar_objetos() -> dict:
    try:
        from app.catalogo import cargar_catalogo

        cat = cargar_catalogo()
        for nombre in ("datos", "data", "raw"):
            if isinstance(getattr(cat, nombre, None), dict):
                return getattr(cat, nombre).get("objetos") or {}
        if getattr(cat, "objetos", None):
            return cat.objetos
    except ModuleNotFoundError:
        pass
    import json

    ruta = RAIZ / "data" / "catalogo.json"
    if not ruta.exists():
        raise SystemExit("No existe data/catalogo.json: genera antes el catálogo (tools\\importar_metabot.py).")
    return json.loads(ruta.read_text(encoding="utf-8")).get("objetos") or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Importa los precios del Excel (hoja Prices) como histórico inicial.")
    ap.add_argument("--servidor", required=True, help="id del servidor (pestaña Personaje) donde guardar los precios")
    ap.add_argument("--excel", default=str(EXCEL_POR_DEFECTO), help="ruta del Excel")
    ap.add_argument("--simular", action="store_true", help="solo mostrar el informe, sin guardar nada")
    args = ap.parse_args(argv)

    ruta = Path(args.excel)
    if not ruta.exists():
        raise SystemExit(f"No encuentro el Excel: {ruta}")
    filas = leer_excel(ruta)
    emp = Emparejador(cargar_objetos())

    from app.db import Lectura, obtener_repositorio

    repo = obtener_repositorio()
    servidores = {s["id"]: s for s in repo.listar_servidores()}
    if args.servidor not in servidores:
        disponibles = ", ".join(f"{k} ({v['nombre']})" for k, v in servidores.items()) or "ninguno"
        raise SystemExit(f"El servidor «{args.servidor}» no existe. Créalo en la pestaña Personaje. Disponibles: {disponibles}")

    lecturas, npc, sin_precio, no_emp, repetidas = [], [], [], [], []
    print(f"Excel: {ruta.name} · {len(filas)} filas · servidor {servidores[args.servidor]['nombre']} · BD {repo.backend}\n")
    for f in filas:
        oid, modo, punt = emp.buscar(f["nombre"])
        npc_fila = es_npc(f["nombre"], f["notas"])
        etiqueta = "NPC" if npc_fila else "mercado"
        if oid is None:
            no_emp.append((f, modo))
            continue
        precio = f["precio"]
        if not isinstance(precio, (int, float)) or precio <= 0:
            sin_precio.append((f, oid))
            continue
        destino = f"#{oid}" + (f" ({modo}, {punt:.0f})" if modo != "exacto" else "")
        print(f"  fila {f['fila']:>2} {etiqueta:<7} {f['nombre']:<36} {precio:>10,.0f} → {destino}".replace(",", "."))
        if npc_fila:
            npc.append((oid, float(precio)))
        else:
            lecturas.append(Lectura(servidor_id=args.servidor, objeto_id=oid, fecha=FECHA_EXCEL,
                                    precio_min=float(precio), cantidad_total=None, num_anuncios=None,
                                    ofertas=[], fuente="excel"))

    # idempotencia: no repetir lecturas excel del mismo día
    nuevas = []
    for lec in lecturas:
        previas = repo.historico(args.servidor, lec.objeto_id, FECHA_EXCEL.replace(hour=0))
        if any(p.fuente == "excel" and p.fecha.date() == FECHA_EXCEL.date() for p in previas):
            repetidas.append(lec)
        else:
            nuevas.append(lec)

    print()
    if sin_precio:
        print(f"Sin precio en el Excel ({len(sin_precio)}): " + "; ".join(f["nombre"] for f, _ in sin_precio))
    if no_emp:
        print(f"\nNO EMPAREJADOS ({len(no_emp)}) — revisa los nombres o añádelos a mano en la app:")
        for f, motivo in no_emp:
            print(f"  fila {f['fila']:>2} {f['nombre']:<40} {motivo}")
    print(f"\nResumen: {len(nuevas)} lecturas nuevas, {len(repetidas)} ya importadas, {len(npc)} precios NPC, "
          f"{len(no_emp)} sin emparejar, {len(sin_precio)} sin precio.")

    if args.simular:
        print("Modo simulación: no se ha guardado nada.")
        return 0
    if nuevas:
        res = repo.guardar_lecturas(nuevas, "excel-2026-10-09")
        print(f"Guardadas {len(res.ids)} lecturas" + (" (en la cola offline: se subirán al reconectar)." if res.en_cola else "."))
    for oid, precio in npc:
        repo.guardar_precio_npc(oid, precio)
    if npc:
        print(f"Guardados {len(npc)} precios NPC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
