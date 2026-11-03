"""temporales tests: a file is never deleted without verifying its readings."""
import json

import pytest

from app.captura import temporales
from app.captura.temporales import Temporales


class RepoFalso:
    """Repository double: verificar_lecturas returns whatever is configured."""

    def __init__(self, respuesta=True, verificados=None, error=None):
        self.respuesta = respuesta
        self.verificados = verificados  # set of valid ids (if given, it overrides `respuesta`)
        self.error = error
        self.llamadas = []

    def verificar_lecturas(self, ids):
        self.llamadas.append(list(ids))
        if self.error:
            raise self.error
        if self.verificados is not None:
            return all(i in self.verificados for i in ids)
        return self.respuesta


@pytest.fixture
def tmp(tmp_path):
    return Temporales(tmp_path / "tmp")


def _archivo(ruta, tam=10):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"x" * tam)
    return ruta


def test_no_borra_si_la_verificacion_falla(tmp, tmp_path):
    video = _archivo(tmp_path / "videos" / "mercado.mp4")
    tmp.registrar_temporal(video, ["a", "b"])
    repo = RepoFalso(respuesta=False)
    res = tmp.limpiar_verificados(repo)
    assert video.exists()
    assert res["borrados"] == [] and len(res["conservados"]) == 1
    assert repo.llamadas == [["a", "b"]]
    assert tmp.esta_registrado(video)


def test_borra_si_la_verificacion_es_correcta(tmp, tmp_path):
    captura = _archivo(tmp_path / "pendientes" / "c1.png")
    tmp.registrar_temporal(captura, ["id1"])
    res = tmp.limpiar_verificados(RepoFalso(respuesta=True))
    assert not captura.exists()
    assert len(res["borrados"]) == 1
    assert not tmp.esta_registrado(captura)


def test_solo_true_estricto_autoriza_el_borrado(tmp, tmp_path):
    captura = _archivo(tmp_path / "c.png")
    tmp.registrar_temporal(captura, ["id1"])
    for respuesta in (None, 1, "sí", [1]):
        tmp.limpiar_verificados(RepoFalso(respuesta=respuesta))
        assert captura.exists()


def test_no_borra_si_la_verificacion_lanza_error(tmp, tmp_path):
    video = _archivo(tmp_path / "v.mkv")
    tmp.registrar_temporal(video, ["x"])
    res = tmp.limpiar_verificados(RepoFalso(error=ConnectionError("sin red")))
    assert video.exists()
    assert "sin red" in next(iter(res["errores"].values()))


def test_no_borra_sin_ids(tmp, tmp_path):
    captura = _archivo(tmp_path / "vacia.png")
    tmp.registrar_temporal(captura, [])
    repo = RepoFalso(respuesta=True)
    tmp.limpiar_verificados(repo)
    assert captura.exists() and repo.llamadas == []


def test_mezcla_verificados_y_no_verificados(tmp, tmp_path):
    a = _archivo(tmp_path / "a.png")
    b = _archivo(tmp_path / "b.png")
    tmp.registrar_temporal(a, ["1", "2"])
    tmp.registrar_temporal(b, ["3"])
    tmp.limpiar_verificados(RepoFalso(verificados={"1", "2"}))
    assert not a.exists() and b.exists()


def test_registro_acumula_ids_y_persiste(tmp, tmp_path):
    a = _archivo(tmp_path / "a.mp4")
    tmp.registrar_temporal(a, ["1"])
    tmp.registrar_temporal(a, ["1", "2"])
    datos = json.loads(tmp.ruta_registro.read_text(encoding="utf-8"))
    entrada = next(iter(datos["archivos"].values()))
    assert entrada["ids"] == ["1", "2"] and entrada["tipo"] == "video"
    # Another instance on the same folder reads the same registry.
    assert Temporales(tmp.dir_tmp).esta_registrado(a)


def test_archivo_ya_borrado_se_quita_del_registro_tras_verificar(tmp, tmp_path):
    a = _archivo(tmp_path / "a.png")
    tmp.registrar_temporal(a, ["1"])
    a.unlink()
    tmp.limpiar_verificados(RepoFalso(respuesta=True))
    assert not tmp.esta_registrado(a)


def test_recortes_solo_se_borran_tras_revisar(tmp):
    r1 = _archivo(tmp.dir_tmp / "revision" / "r1.png")
    r2 = _archivo(tmp.dir_tmp / "revision" / "r2.png")
    tmp.registrar_recorte(r1, {"objeto_id": 1, "nombre_leido": "Okra", "precio": 850, "cantidad": 2})
    tmp.registrar_recorte(r2, {})
    assert len(tmp.recortes_pendientes()) == 2
    assert tmp.limpiar_revisados() == []
    assert tmp.marcar_revisado(r1)
    borrados = tmp.limpiar_revisados()
    assert len(borrados) == 1 and not r1.exists() and r2.exists()
    assert len(tmp.recortes_pendientes()) == 1


def test_recorte_fuera_de_tmp_no_se_borra(tmp, tmp_path):
    fuera = _archivo(tmp_path / "otra" / "r.png")
    tmp.registrar_recorte(fuera)
    tmp.marcar_revisado(fuera)
    tmp.limpiar_revisados()
    assert fuera.exists()


def test_aplicar_tope_avisa_sin_borrar_lo_no_verificado(tmp):
    grande = _archivo(tmp.dir_tmp / "video_grande.mp4", tam=300_000)
    tmp.registrar_temporal(grande, ["1"])
    res = tmp.aplicar_tope(mb=0.1, repo=RepoFalso(respuesta=False))
    assert res["excedido"] and "no se borra nada sin verificar" in res["aviso"]
    assert grande.exists()


def test_aplicar_tope_limpia_lo_verificado(tmp):
    grande = _archivo(tmp.dir_tmp / "video_grande.mp4", tam=300_000)
    tmp.registrar_temporal(grande, ["1"])
    res = tmp.aplicar_tope(mb=0.1, repo=RepoFalso(respuesta=True))
    assert not res["excedido"] and res["aviso"] is None
    assert not grande.exists()


def test_aplicar_tope_por_debajo(tmp):
    _archivo(tmp.dir_tmp / "poco.png", tam=100)
    res = tmp.aplicar_tope(mb=500)
    assert not res["excedido"] and res["tamano_mb"] < 1


def test_funciones_de_modulo_con_configurar(tmp_path):
    original = temporales.instancia()
    try:
        temporales.configurar(tmp_path / "tmp")
        a = _archivo(tmp_path / "a.png")
        temporales.registrar_temporal(a, ["1"])
        assert temporales.esta_registrado(a)
        temporales.limpiar_verificados(RepoFalso(respuesta=False))
        assert a.exists()
        temporales.limpiar_verificados(RepoFalso(respuesta=True))
        assert not a.exists()
    finally:
        temporales._por_defecto = original
