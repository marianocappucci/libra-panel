"""La suma. Es donde vive la parte del panel que puede mentir.

Cada test de este archivo corresponde a una de las tres reglas del encabezado
de `consolidado.py`. Si alguno se pone en rojo, el panel volvio a poder mostrar
un numero mas chico que la realidad con cara de numero correcto.
"""
from libra_panel.consolidado import (
    ResultadoSucursal,
    agrupar_por_cuit,
    armar_respuesta,
    consolidar,
    normalizar_cuit,
    sumar_bloque,
)


def sucursal(slug, *, cuit="", razon_social="", ok=True, detalle="", **bloques):
    """Una sucursal que contesto los bloques que se le pasen."""
    datos = {
        "instancia": {"nombre": slug, "cuit": bloques.pop("cuit_informado", cuit), "punto_venta": 1},
        "periodo": {"desde": "2026-08-01", "hasta": "2026-08-20"},
        **bloques,
    }
    return ResultadoSucursal(
        slug=slug, nombre=slug.title(), cuit=cuit, razon_social=razon_social,
        ok=ok, detalle=detalle, datos=datos if ok else None,
    )


NUCLEO = {"facturado": 100.0, "cobrado": 80.0, "sin_cobrar": {"cantidad": 2, "monto": 20.0}}


# ── Regla 1: una sucursal que no contesta NO es una sucursal que vendio cero ─


def test_la_sucursal_caida_no_suma_cero_y_el_total_queda_marcado_parcial():
    caida = ResultadoSucursal(
        slug="complejo-3", nombre="Complejo 3", ok=False, detalle="ReadTimeout",
    )
    salida = consolidar([sucursal("a", nucleo=NUCLEO), sucursal("b", nucleo=NUCLEO), caida])

    assert salida["cobertura"] == {
        "total": 3,
        "respondieron": 2,
        "parcial": True,
        "sin_respuesta": [
            {"slug": "complejo-3", "nombre": "Complejo 3", "detalle": "ReadTimeout"}
        ],
    }
    # 200, no 300 con un tercio inventado, y tampoco un 200 que se lea como el
    # total de las tres.
    assert salida["bloques"]["nucleo"]["datos"]["facturado"] == 200.0
    assert salida["bloques"]["nucleo"]["sucursales"] == 2


def test_la_cobertura_va_siempre_aunque_contesten_todas():
    """Un contador que solo aparece ante un problema entrena a no mirarlo."""
    salida = consolidar([sucursal("a", nucleo=NUCLEO)])
    assert salida["cobertura"]["total"] == 1
    assert salida["cobertura"]["respondieron"] == 1
    assert salida["cobertura"]["parcial"] is False


def test_sin_ninguna_sucursal_no_hay_bloques_ni_ceros():
    salida = consolidar([])
    assert salida["bloques"] == {}
    assert salida["cobertura"]["parcial"] is False


# ── Regla 2: un bloque que no aplica NO es un bloque en cero ─────────────────


def test_el_bloque_que_una_sucursal_no_tiene_no_entra_como_cero():
    comercio = {"ventas": {"cantidad": 3, "monto": 30.0}, "stock_bajo_minimo": 1}
    salida = consolidar([
        sucursal("padel-1", nucleo=NUCLEO, comercio=comercio),
        sucursal("padel-2", nucleo=NUCLEO, comercio=comercio),
        # Un producto sin LibraCommerce (MedLibra): manda nucleo y nada mas.
        sucursal("consultorio", nucleo=NUCLEO),
    ])

    assert salida["bloques"]["nucleo"]["sucursales"] == 3
    # El denominador del bloque es 2, no 3: el consultorio no mide buffet.
    assert salida["bloques"]["comercio"]["sucursales"] == 2
    assert salida["bloques"]["comercio"]["slugs"] == ["padel-1", "padel-2"]
    assert salida["bloques"]["comercio"]["datos"]["ventas"]["monto"] == 60.0


def test_un_bloque_que_nadie_reporta_no_aparece_en_la_salida():
    salida = consolidar([sucursal("a", nucleo=NUCLEO)])
    assert "comercio" not in salida["bloques"]
    assert "agenda" not in salida["bloques"]


def test_un_bloque_nuevo_se_suma_sin_tocar_este_modulo():
    """Un producto que sume `agenda` de LibraGenda entra solo."""
    salida = consolidar([
        sucursal("a", nucleo=NUCLEO, agenda={"turnos": 4}),
        sucursal("b", nucleo=NUCLEO, agenda={"turnos": 6}),
    ])
    assert salida["bloques"]["agenda"]["datos"]["turnos"] == 10


def test_una_clave_que_falta_en_una_sucursal_se_marca_como_incompleta():
    """El total de esa clave sale de menos sucursales que el resto del bloque."""
    salida = consolidar([
        sucursal("a", nucleo=NUCLEO, comercio={"ventas": {"monto": 10.0}, "stock_bajo_minimo": 2}),
        sucursal("b", nucleo=NUCLEO, comercio={"ventas": {"monto": 5.0}}),
    ])
    assert salida["bloques"]["comercio"]["datos"]["ventas"]["monto"] == 15.0
    assert salida["bloques"]["comercio"]["incompletos"] == ["stock_bajo_minimo"]


def test_los_booleanos_no_se_suman():
    """`activo: true` sumado cinco veces daria 5, que no es el total de nada."""
    assert sumar_bloque([{"activo": True, "monto": 2}, {"activo": True, "monto": 3}]) == {
        "datos": {"monto": 5},
        "incompletos": [],
    }


def test_los_textos_no_entran_en_la_suma():
    assert sumar_bloque([{"moneda": "ARS", "monto": 1.5}])["datos"] == {"monto": 1.5}


# ── Regla 3: sumar entre CUITs da un numero de gestion, no uno fiscal ────────


def test_normalizar_cuit_ignora_guiones_y_espacios():
    assert normalizar_cuit("30-71234567-9") == normalizar_cuit(" 30712345679 ") == "30712345679"


def test_dos_sucursales_del_mismo_cuit_forman_un_grupo():
    grupos = agrupar_por_cuit([
        sucursal("a", cuit="30-71234567-9", razon_social="Padel SA", nucleo=NUCLEO),
        sucursal("b", cuit="30712345679", razon_social="Padel SA", nucleo=NUCLEO),
    ])
    assert len(grupos) == 1
    assert grupos[0]["identificado"] is True
    assert grupos[0]["sucursales"] == ["a", "b"]
    assert grupos[0]["bloques"]["nucleo"]["datos"]["facturado"] == 200.0


def test_el_cuit_vacio_NO_agrupa():
    """🔴 El caso medido el 2026-08-20: la demo contesto `CUIT ''`.

    Con el CUIT vacio como clave, dos sucursales sin configurar se juntarian
    como si fueran la misma empresa. Un dato faltante se ve; uno agrupado mal,
    no.
    """
    grupos = agrupar_por_cuit([
        sucursal("sin-config-1", cuit="", nucleo=NUCLEO),
        sucursal("sin-config-2", cuit="", nucleo=NUCLEO),
    ])
    assert len(grupos) == 2
    assert [g["identificado"] for g in grupos] == [False, False]
    assert [g["sucursales"] for g in grupos] == [["sin-config-1"], ["sin-config-2"]]
    # Y ninguna suma incluye a la otra.
    assert all(g["bloques"]["nucleo"]["datos"]["facturado"] == 100.0 for g in grupos)


def test_las_sin_identificar_van_al_final_de_la_lista():
    grupos = agrupar_por_cuit([
        sucursal("suelta", cuit="", nucleo=NUCLEO),
        sucursal("a", cuit="30111111119", razon_social="Zeta SA", nucleo=NUCLEO),
    ])
    assert [g["identificado"] for g in grupos] == [True, False]


def test_una_sucursal_caida_cae_igual_en_su_grupo_y_lo_marca_parcial():
    """Se agrupa por el CUIT del registro, que existe aunque no conteste."""
    caida = ResultadoSucursal(
        slug="b", nombre="B", cuit="30111111119", razon_social="Padel SA",
        ok=False, detalle="ConnectError",
    )
    grupos = agrupar_por_cuit([
        sucursal("a", cuit="30111111119", razon_social="Padel SA", nucleo=NUCLEO),
        caida,
    ])
    assert len(grupos) == 1
    assert grupos[0]["cobertura"] == {
        "total": 2, "respondieron": 1, "parcial": True,
        "sin_respuesta": [{"slug": "b", "nombre": "B", "detalle": "ConnectError"}],
    }


# ── La identidad que puede venir vacia o no coincidir ────────────────────────


def test_una_sucursal_que_no_sabe_quien_es_se_marca():
    salida = armar_respuesta(
        desde="2026-08-01", hasta="2026-08-20",
        resultados=[sucursal("demo", cuit="", cuit_informado="", nucleo=NUCLEO)],
    )
    fila = salida["sucursales"][0]
    assert fila["identidad_incompleta"] is True
    assert fila["cuit_discrepa"] is False


def test_el_cuit_del_registro_y_el_informado_que_no_coinciden_se_marcan():
    salida = armar_respuesta(
        desde="2026-08-01", hasta="2026-08-20",
        resultados=[sucursal("a", cuit="30111111119", cuit_informado="30999999998", nucleo=NUCLEO)],
    )
    assert salida["sucursales"][0]["cuit_discrepa"] is True


def test_la_sucursal_caida_no_se_marca_como_identidad_incompleta():
    """No sabemos si tiene empresa configurada: no contesto. Es otra cosa."""
    caida = ResultadoSucursal(slug="a", nombre="A", ok=False, detalle="timeout")
    salida = armar_respuesta(desde="2026-08-01", hasta="2026-08-20", resultados=[caida])
    fila = salida["sucursales"][0]
    assert fila["estado"] == "sin_respuesta"
    assert fila["identidad_incompleta"] is False


def test_la_respuesta_completa_trae_las_cuatro_piezas():
    salida = armar_respuesta(
        desde="2026-08-01", hasta="2026-08-20",
        resultados=[sucursal("a", cuit="30111111119", razon_social="Padel SA", nucleo=NUCLEO)],
    )
    assert set(salida) == {"periodo", "cobertura", "consolidado", "grupos", "sucursales"}
    assert salida["periodo"] == {"desde": "2026-08-01", "hasta": "2026-08-20"}
