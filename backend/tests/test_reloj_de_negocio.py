"""El «hoy» del panel es el reloj de Argentina del motor, no el de la máquina.

`libra_panel.fechas` delega en `libracore.fechas` (ADR-070): una sola fuente
para la fecha de negocio de toda la familia. El «mes en curso» que el panel le
pide a cada sucursal cuando no se le dice otro período sale de ahí.

🔴 Entre las 21:00 y la medianoche de Argentina una máquina en UTC ya está en el
día siguiente y el período por defecto arrancaría el 1 del mes que viene. La
suite corre con `TZ=America/Argentina/Buenos_Aires` (ver `conftest.py`): estos
tests vuelven el proceso a UTC y pisan el instante del motor (`_ahora_utc`).
"""
import datetime
import os
import time

import pytest
from libracore import fechas

from libra_panel.fechas import AR_TZ, ahora_ar, hoy_ar, rango_por_defecto
from tests.test_resumen import con_cinco, cuerpo  # noqa: F401  (fixtures)

#: 02:30 UTC del 1 de abril de 2031 = 23:30 del 31 de marzo en Argentina. Una fecha
#: lejana a propósito: así el reloj real nunca coincide con la esperada. Además cae
#: en cambio de mes, que es donde el defecto muestra todo en cero.
INSTANTE = datetime.datetime(2031, 4, 1, 2, 30, tzinfo=datetime.UTC)


@pytest.fixture
def _proceso_en_utc_a_las_23_30_de_argentina(monkeypatch):
    """El proceso en UTC y el reloj del motor clavado en `INSTANTE`."""
    antes = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    monkeypatch.setattr(fechas, "_ahora_utc", lambda: INSTANTE)
    try:
        yield
    finally:
        if antes is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = antes
        time.tzset()


def test_hoy_y_ahora_son_los_del_motor(_proceso_en_utc_a_las_23_30_de_argentina):
    assert hoy_ar() == datetime.date(2031, 3, 31)
    assert ahora_ar() == INSTANTE
    assert ahora_ar().utcoffset() == datetime.timedelta(hours=-3)
    assert AR_TZ is fechas.ZONA_AR


def test_el_periodo_por_defecto_es_el_mes_en_curso_de_argentina(
    _proceso_en_utc_a_las_23_30_de_argentina,
):
    assert rango_por_defecto() == ("2031-03-01", "2031-03-31")


def test_sin_periodo_se_le_pide_a_cada_sucursal_el_mes_de_argentina(
    con_cinco, _proceso_en_utc_a_las_23_30_de_argentina,  # noqa: F811
):
    cliente, falso = con_cinco({"http://c1:8000": cuerpo()})
    cliente.get("/api/resumen")
    assert falso.llamadas == [("http://c1:8000", "2031-03-01", "2031-03-31")]
