"""El bloque `club`: una fila por sucursal del club, sumada entre instancias.

El gate del ROADMAP de LibraClub: «un dueño con dos instancias y cinco
sucursales viendo cinco filas, no dos». El primer test de cada grupo es ese
criterio; los demas fijan las reglas de `club.py` (suma, ponderacion, bloque
ausente que no es cero, instancia con el bloque roto que no tumba a las otras).

Datos ficticios: no hay ninguna persona ni empresa real.
"""
import json
import math

import pytest

from libra_panel.club import armar_club, promedio_ponderado, variacion_pct
from libra_panel.consolidado import ResultadoSucursal, armar_respuesta

from .conftest import hacer_cliente
from .test_resumen import ClienteFalso, alta, asignar_todas_al_admin, cuerpo


def ingresos(total, anterior, *, de_reservas=0.0, senas=0.0, buffet=0.0):
    return {
        "reservas": de_reservas, "senas": senas, "buffet": buffet,
        "total": total, "total_periodo_anterior": anterior,
    }


def sede(sucursal_id, nombre, *, ocupacion, reservas, total, anterior, origen=None, franjas=None,
         canceladas=0, ausentes=0, **resto_ingresos):
    return {
        "sucursal_id": sucursal_id,
        "sucursal": nombre,
        "ocupacion_pct": ocupacion,
        "franjas": franjas or [],
        "ingresos": ingresos(total, anterior, **resto_ingresos),
        "canceladas": canceladas,
        "ausentes": ausentes,
        "reservas": reservas,
        "origen": origen or {},
    }


def club(*sedes):
    return {"desde": "2026-10-01", "hasta": "2026-10-24", "por_sucursal": list(sedes)}


#: Instancia «norte»: dos sedes. Instancia «sur»: tres. Cinco filas en total.
#: El `sucursal_id` 1 se repite en las dos instancias a proposito: el id es de
#: cada base, no del panel, y la fila tiene que distinguirse por instancia.
NORTE = club(
    sede(1, "Centro", ocupacion=60.0, reservas=100, total=1500.0, anterior=1200.0,
         canceladas=3, ausentes=2, buffet=300.0, senas=200.0,
         origen={"mostrador": 40, "portal": 50},
         franjas=[{"dia": 0, "hora": 18, "ocupacion_pct": 90.0},
                  {"dia": 5, "hora": 10, "ocupacion_pct": 40.0}]),
    sede(2, "Norte", ocupacion=80.0, reservas=300, total=3000.0, anterior=3300.0,
         canceladas=10, ausentes=4, buffet=900.0,
         origen={"mostrador": 10, "whatsapp": 5, "serie": 15},
         franjas=[{"dia": 0, "hora": 18, "ocupacion_pct": 70.0}]),
)
SUR = club(
    sede(1, "Centro", ocupacion=50.0, reservas=100, total=500.0, anterior=0.0,
         canceladas=1, ausentes=1, origen={"portal": 20, "telefono": 5},
         franjas=[{"dia": 0, "hora": 18, "ocupacion_pct": 50.0}]),
    sede(2, "Costanera", ocupacion=70.0, reservas=200, total=2000.0, anterior=1000.0,
         canceladas=6, ausentes=0, buffet=400.0),
    sede(3, "Puerto", ocupacion=42.0, reservas=100, total=800.0, anterior=800.0,
         canceladas=2, ausentes=3),
)


def reportes(**instancias):
    return [(slug, slug.title(), datos) for slug, datos in instancias.items()]


def datos_de(**bloques):
    return {"instancia": {"nombre": "x", "cuit": "", "punto_venta": 1}, "nucleo": {"facturado": 1.0}, **bloques}


# ── El criterio de aceptacion: cinco filas, no dos ──────────────────────────


def test_dos_instancias_y_cinco_sucursales_dan_cinco_filas():
    salida = armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))

    assert salida["instancias"] == 2
    assert [(f["slug"], f["sucursal_id"], f["sucursal"]) for f in salida["por_sucursal"]] == [
        ("norte", 1, "Centro"), ("norte", 2, "Norte"),
        ("sur", 1, "Centro"), ("sur", 2, "Costanera"), ("sur", 3, "Puerto"),
    ]
    # Cada fila lleva el nombre de la instancia de donde viene.
    assert [f["instancia"] for f in salida["por_sucursal"]] == ["Norte", "Norte", "Sur", "Sur", "Sur"]
    assert salida["totales"]["sucursales"] == 5


def test_los_totales_suman_las_cinco_sucursales():
    t = armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))["totales"]

    assert t["reservas"] == 800
    assert t["canceladas"] == 22
    assert t["ausentes"] == 10
    assert t["ingresos"]["total"] == 7800.0
    assert t["ingresos"]["total_periodo_anterior"] == 6300.0
    assert t["ingresos"]["buffet"] == 1600.0
    assert t["variacion_pct"] == 23.8  # (7800 - 6300) / 6300


def test_la_ocupacion_general_se_pondera_por_reservas_y_no_es_el_promedio_simple():
    t = armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))["totales"]

    # (60*100 + 80*300 + 50*100 + 70*200 + 42*100) / 800
    assert t["ocupacion_pct"] == 66.5
    # El promedio simple daria 60.4: una sede de 100 reservas pesaria como una de 300.
    assert t["ocupacion_pct"] != round((60 + 80 + 50 + 70 + 42) / 5, 1)
    # El criterio viaja con el numero, para que la pantalla lo diga.
    assert t["criterio_ocupacion"] == "ponderada_por_reservas"


def test_la_variacion_de_cada_fila_es_contra_su_periodo_anterior():
    filas = {
        (f["slug"], f["sucursal_id"]): f["variacion_pct"]
        for f in armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))["por_sucursal"]
    }
    assert filas[("norte", 1)] == 25.0
    assert filas[("norte", 2)] == -9.1
    assert filas[("sur", 2)] == 100.0
    assert filas[("sur", 3)] == 0.0
    # Sin periodo anterior no hay contra que comparar: ni +inf ni 0 %.
    assert filas[("sur", 1)] is None


def test_el_origen_suma_por_clave_con_las_claves_que_vengan():
    t = armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))["totales"]

    assert t["origen"] == {"mostrador": 50, "portal": 70, "whatsapp": 5, "serie": 15, "telefono": 5}


def test_el_mapa_combinado_pondera_por_reservas_y_cuenta_de_cuantas_sucursales_sale():
    franjas = {
        (f["dia"], f["hora"]): f
        for f in armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))["franjas"]
    }
    # Lunes 18 h: 90 (100 reservas), 70 (300) y 50 (100) -> 35000 / 500.
    assert franjas[(0, 18)]["ocupacion_pct"] == 70.0
    assert franjas[(0, 18)]["sucursales"] == 3
    # Sabado 10 h: solo la informa una sede. Las otras no tienen dato, no tienen 0 %.
    assert franjas[(5, 10)]["ocupacion_pct"] == 40.0
    assert franjas[(5, 10)]["sucursales"] == 1
    assert len(franjas) == 2


# ── Regla: un bloque que no esta no es un bloque en cero ────────────────────


def test_una_instancia_sin_club_no_aporta_filas_ni_baja_el_promedio():
    con = armar_club(reportes(norte=datos_de(club=NORTE), sur=datos_de(club=SUR)))
    # Una instancia vieja (o de otro producto) que contesta sin `club`.
    mezcla = armar_club(reportes(
        norte=datos_de(club=NORTE), vieja=datos_de(), sur=datos_de(club=SUR),
    ))

    assert mezcla["instancias"] == 2
    assert mezcla["slugs"] == ["norte", "sur"]
    assert mezcla["invalidos"] == []
    assert mezcla["totales"] == con["totales"]
    assert len(mezcla["por_sucursal"]) == 5


def test_si_ninguna_instancia_manda_club_no_hay_bloque():
    assert armar_club(reportes(vieja=datos_de(), otra=datos_de())) is None
    assert armar_club([]) is None
    # Una instancia que no contesto tiene `datos=None`.
    assert armar_club([("caida", "Caida", None)]) is None


def test_un_club_sin_sucursales_es_un_club_vacio_y_no_un_total_en_cero():
    salida = armar_club(reportes(norte=datos_de(club=club())))

    assert salida["instancias"] == 1
    assert salida["por_sucursal"] == []
    # Nada que sumar: sin dato, no 0.
    assert salida["totales"]["reservas"] is None
    assert salida["totales"]["ocupacion_pct"] is None
    assert salida["totales"]["variacion_pct"] is None
    assert salida["totales"]["ingresos"]["total"] is None


# ── Una instancia con el bloque roto no tumba a las otras ───────────────────


@pytest.mark.parametrize("roto", [None, [], "texto", 7, {"desde": "x"}, {"por_sucursal": {"a": 1}}])
def test_un_club_ilegible_se_nombra_y_las_demas_siguen(roto):
    salida = armar_club(reportes(norte=datos_de(club=NORTE), rota=datos_de(club=roto)))

    assert [i["slug"] for i in salida["invalidos"]] == ["rota"]
    assert "por_sucursal" in salida["invalidos"][0]["detalle"]
    assert salida["instancias"] == 1
    assert len(salida["por_sucursal"]) == 2


def test_los_valores_con_forma_rara_quedan_en_none_y_no_en_cero():
    rara = {
        "sucursal_id": 9, "sucursal": "Rara",
        "ocupacion_pct": "mucho", "reservas": True, "canceladas": float("nan"),
        "ausentes": None, "origen": {"portal": "diez", "mostrador": 4, "otro": True},
        "ingresos": {"total": float("inf"), "senas": "x"},
        "franjas": [
            {"dia": 7, "hora": 10, "ocupacion_pct": 50.0},   # dia fuera de rango
            {"dia": 1, "hora": 24, "ocupacion_pct": 50.0},   # hora fuera de rango
            {"dia": 1, "hora": 10, "ocupacion_pct": "x"},    # no es numero
            {"dia": 1, "hora": 10},                          # sin ocupacion
            "no soy una franja",
            {"dia": 2, "hora": 9, "ocupacion_pct": 30.0},    # la unica buena
        ],
    }
    fila = armar_club(reportes(norte=datos_de(club=club(rara, "no soy una sede"))))["por_sucursal"][0]

    assert fila["ocupacion_pct"] is None
    assert fila["reservas"] is None  # un bool no es un conteo
    assert fila["canceladas"] is None
    assert fila["ausentes"] is None
    assert fila["origen"] == {"mostrador": 4}
    assert fila["ingresos"]["total"] is None
    assert fila["ingresos"]["senas"] is None
    assert fila["variacion_pct"] is None
    assert fila["franjas"] == [{"dia": 2, "hora": 9, "ocupacion_pct": 30.0}]


def test_el_resultado_siempre_es_json_valido():
    # `inf` y `NaN` no son JSON: si pasaran, la respuesta entera daria 500.
    rara = sede(1, "X", ocupacion=float("nan"), reservas=1, total=float("inf"), anterior=1.0)
    salida = armar_club(reportes(norte=datos_de(club=club(rara))))

    json.dumps(salida, allow_nan=False)


# ── Las piezas chicas ───────────────────────────────────────────────────────


def test_promedio_ponderado():
    assert promedio_ponderado([]) is None
    assert promedio_ponderado([(10.0, 1), (30.0, 3)]) == 25.0
    # Todos los pesos en cero: cae al promedio simple y no divide por cero.
    assert promedio_ponderado([(10.0, 0), (30.0, 0)]) == 20.0


def test_variacion_pct():
    assert variacion_pct(150, 100) == 50.0
    assert variacion_pct(50, 100) == -50.0
    assert variacion_pct(10, 0) is None
    assert variacion_pct(None, 100) is None
    assert variacion_pct(10, None) is None
    assert not math.isinf(variacion_pct(1, 3) or 0)


# ── La respuesta completa ───────────────────────────────────────────────────


def _resultado(slug, club_=None, *, ok=True):
    datos = {
        "instancia": {"nombre": slug, "cuit": "", "punto_venta": 1},
        "periodo": {"desde": "2026-10-01", "hasta": "2026-10-24"},
        "nucleo": {"facturado": 100.0},
    }
    if club_ is not None:
        datos["club"] = club_
    return ResultadoSucursal(
        slug=slug, nombre=slug.title(), ok=ok, datos=datos if ok else None,
        detalle="" if ok else "ConnectTimeout",
    )


def test_la_respuesta_trae_club_y_no_lo_cuela_como_bloque_generico():
    salida = armar_respuesta(
        desde="2026-10-01", hasta="2026-10-24",
        resultados=[_resultado("norte", NORTE), _resultado("vieja"), _resultado("sur", SUR),
                    _resultado("caida", ok=False)],
    )

    assert len(salida["club"]["por_sucursal"]) == 5
    # `club` es una lista de filas y no un arbol de numeros: como bloque generico
    # saldria vacio, un «Club» sin tarjetas.
    assert "club" not in salida["consolidado"]
    assert all("club" not in g["bloques"] for g in salida["grupos"])
    assert all("club" not in s["bloques"] for s in salida["sucursales"])
    # Lo demas sigue igual: el nucleo suma las tres que contestaron.
    assert salida["consolidado"]["nucleo"]["datos"]["facturado"] == 300.0
    assert salida["cobertura"]["respondieron"] == 3


def test_sin_club_en_ninguna_instancia_la_respuesta_trae_club_null():
    salida = armar_respuesta(
        desde="2026-10-01", hasta="2026-10-24", resultados=[_resultado("vieja")],
    )
    assert salida["club"] is None


# ── De punta a punta: GET /api/resumen ──────────────────────────────────────


def test_el_endpoint_devuelve_cinco_filas_de_dos_instancias_y_tolera_una_sin_club(crear_app):
    respuestas = {
        "http://norte:8000": cuerpo(nombre="Norte", club=NORTE),
        "http://sur:8000": cuerpo(nombre="Sur", club=SUR),
        "http://vieja:8000": cuerpo(nombre="Vieja"),
    }
    app = crear_app(cliente_sucursal=ClienteFalso(respuestas))
    cliente = hacer_cliente(app)
    assert cliente.post("/auth/login", json={"username": "admin", "password": "admin-de-test"}).status_code == 200
    for url in respuestas:
        alta(cliente, url.removeprefix("http://").removesuffix(":8000"), url=url)
    asignar_todas_al_admin(cliente, ["norte", "sur", "vieja"])

    resp = cliente.get("/api/resumen")

    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["cobertura"]["respondieron"] == 3
    assert len(datos["club"]["por_sucursal"]) == 5
    assert datos["club"]["instancias"] == 2
    assert datos["club"]["totales"]["reservas"] == 800
    assert "club" not in datos["consolidado"]
