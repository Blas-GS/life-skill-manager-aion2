r"""Seeds the price history with the prices from the Excel file «aion2-market-place-recipe-book (1).xlsx».

Reads the "Prices" sheet (B = item in English, C = price, D = notes; rows 6–88), matches each
name against the catalog's `nombre_en` (exact first, then fuzzy) and saves:
  - market rows as readings with fuente="excel" dated 2026-10-09 on the given server;
  - rows marked as NPC/shop (or «(Bound)») as NPC prices.
Prints a report of what could not be matched. It is idempotent: it doesn't repeat that day's excel readings.

Usage:
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
# Excel names that don't match the game client; checked against the cost of Okra frita
# in the Excel file (3×700 + 3×788 + 5×880 = 8.864)
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
        raise SystemExit(f"The Excel file has no «Prices» sheet (sheets: {', '.join(wb.sheetnames)})")
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
    """English name → catalog id."""

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
            # avoid a short name («Oil») matching a long one that merely contains it
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
        raise SystemExit("data/catalogo.json does not exist: generate the catalog first (tools\\importar_metabot.py).")
    return json.loads(ruta.read_text(encoding="utf-8")).get("objetos") or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Imports the Excel prices (Prices sheet) as the initial history.")
    ap.add_argument("--servidor", required=True, help="server id (Character tab) where the prices are saved")
    ap.add_argument("--excel", default=str(EXCEL_POR_DEFECTO), help="path to the Excel file")
    ap.add_argument("--simular", action="store_true", help="only print the report, save nothing")
    args = ap.parse_args(argv)

    ruta = Path(args.excel)
    if not ruta.exists():
        raise SystemExit(f"Excel file not found: {ruta}")
    filas = leer_excel(ruta)
    emp = Emparejador(cargar_objetos())

    from app.db import Lectura, obtener_repositorio

    repo = obtener_repositorio()
    servidores = {s["id"]: s for s in repo.listar_servidores()}
    if args.servidor not in servidores:
        disponibles = ", ".join(f"{k} ({v['nombre']})" for k, v in servidores.items()) or "none"
        raise SystemExit(f"Server «{args.servidor}» does not exist. Create it in the Character tab. Available: {disponibles}")

    lecturas, npc, sin_precio, no_emp, repetidas = [], [], [], [], []
    print(f"Excel: {ruta.name} · {len(filas)} rows · server {servidores[args.servidor]['nombre']} · DB {repo.backend}\n")
    for f in filas:
        oid, modo, punt = emp.buscar(f["nombre"])
        npc_fila = es_npc(f["nombre"], f["notas"])
        etiqueta = "NPC" if npc_fila else "market"
        if oid is None:
            no_emp.append((f, modo))
            continue
        precio = f["precio"]
        if not isinstance(precio, (int, float)) or precio <= 0:
            sin_precio.append((f, oid))
            continue
        destino = f"#{oid}" + (f" ({modo}, {punt:.0f})" if modo != "exacto" else "")
        print(f"  row {f['fila']:>2} {etiqueta:<7} {f['nombre']:<36} {precio:>10,.0f} → {destino}".replace(",", "."))
        if npc_fila:
            npc.append((oid, float(precio)))
        else:
            lecturas.append(Lectura(servidor_id=args.servidor, objeto_id=oid, fecha=FECHA_EXCEL,
                                    precio_min=float(precio), cantidad_total=None, num_anuncios=None,
                                    ofertas=[], fuente="excel"))

    # idempotency: don't repeat excel readings from the same day
    nuevas = []
    for lec in lecturas:
        previas = repo.historico(args.servidor, lec.objeto_id, FECHA_EXCEL.replace(hour=0))
        if any(p.fuente == "excel" and p.fecha.date() == FECHA_EXCEL.date() for p in previas):
            repetidas.append(lec)
        else:
            nuevas.append(lec)

    print()
    if sin_precio:
        print(f"No price in the Excel file ({len(sin_precio)}): " + "; ".join(f["nombre"] for f, _ in sin_precio))
    if no_emp:
        print(f"\nUNMATCHED ({len(no_emp)}) — check the names or add them by hand in the app:")
        for f, motivo in no_emp:
            print(f"  row {f['fila']:>2} {f['nombre']:<40} {motivo}")
    print(f"\nSummary: {len(nuevas)} new readings, {len(repetidas)} already imported, {len(npc)} NPC prices, "
          f"{len(no_emp)} unmatched, {len(sin_precio)} without price.")

    if args.simular:
        print("Dry run: nothing was saved.")
        return 0
    if nuevas:
        res = repo.guardar_lecturas(nuevas, "excel-2026-10-09")
        print(f"Saved {len(res.ids)} readings" + (" (in the offline queue: they will upload on reconnect)." if res.en_cola else "."))
    for oid, precio in npc:
        repo.guardar_precio_npc(oid, precio)
    if npc:
        print(f"Saved {len(npc)} NPC prices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
