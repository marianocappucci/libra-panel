"""Una sucursal de mentira, con el router de verdad.

🔑 **Lo que se dobla es la consulta a la base, no el contrato.** El router lo
arma `libracore.resumen_router.build_resumen_router` —la factory real— y el
cerrojo es `libraauth.session_auth.json_api_require_panel_o_admin` —el guard
real—. Lo unico reemplazado es `get_resumen_core`, que es la funcion que hace
el SQL.

Importa que sea asi: un doble de la sucursal entera reproduciria exactamente el
contrato que yo supongo, y los tests pasarian aunque el contrato fuera otro. Con
el router real, si LibraCore cambia la forma de la respuesta, estos tests se
ponen en rojo.

El fallback de la SPA tambien es real: se monta un catch-all que devuelve 200
con HTML, que es lo que hacen los seis productos de la familia y la razon por la
que el cliente del panel no se conforma con el codigo de estado.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from libraauth.session_auth import json_api_require_panel_o_admin
from libracore.resumen_router import build_resumen_router

HTML_DE_LA_SPA = "<!doctype html>\n<html lang=\"es\"><head><title>Sucursal</title></head></html>"


class _SesionQueNoLoguea:
    """Lo minimo que el guard necesita cuando no hay credencial de panel.

    Sin esto, el guard cae en `request.app.state.session_auth` y revienta con
    `AttributeError` -> 500, cuando lo correcto para el panel es un 401.
    """

    def get_current_user(self, request: Request):
        return None


#: Lo que devuelve `get_resumen_core` de LibraCore, con la forma exacta que
#: tiene en `libracore/db/resumen.py` v1.41.0.
NUCLEO_TIPICO = {
    "facturado": 1000.0, "cobrado": 800.0, "egresos": 100.0,
    "saldo_caja": 700.0, "comprobantes": 4,
    "sin_cobrar": {"cantidad": 2, "monto": 200.0},
}


def crear_sucursal_falsa(
    monkeypatch, *, identidad: dict | None = None, nucleo: dict | None = None,
    bloques: dict | None = None, con_spa: bool = True,
) -> FastAPI:
    """Una app que contesta `/api/resumen` como lo hace un producto real.

    `bloques` son los agregados que ESTE producto puede contestar ademas del
    nucleo, igual que en el cableado real de Contalibra
    (`{"comercio": _comercio}`). Lo que no se pasa no se manda: un bloque
    ausente no es un bloque en cero.

    El `monkeypatch` es para reemplazar `get_resumen_core`, que es la unica
    pieza doblada. Al ser un parche de modulo, todas las sucursales falsas de
    un mismo test comparten nucleo — para los tests que necesitan nucleos
    distintos por sucursal alcanza con un doble del cliente, que es lo que se
    usa en `test_resumen.py`.
    """
    _parchear_nucleo(monkeypatch, nucleo if nucleo is not None else NUCLEO_TIPICO)
    app = FastAPI()
    app.state.session_auth = _SesionQueNoLoguea()

    router = build_resumen_router(
        identidad=lambda: identidad if identidad is not None else {
            "nombre": "Complejo Uno", "cuit": "30-71234567-9", "punto_venta": 1,
        },
        guard=json_api_require_panel_o_admin,
        bloques={
            nombre: (lambda desde, hasta, _c=cuerpo: _c)
            for nombre, cuerpo in (bloques or {}).items()
        },
    )
    app.include_router(router)

    if con_spa:
        @app.get("/{ruta:path}", include_in_schema=False)
        def spa(ruta: str):
            return HTMLResponse(HTML_DE_LA_SPA)

    return app


def crear_sucursal_que_contesta(cuerpo, *, status: int = 200) -> FastAPI:
    """Una sucursal que contesta cualquier cosa en `/api/resumen`, sin guard.

    Para los casos de forma equivocada —un JSON que no es objeto, un JSON sin
    `nucleo`— que no se pueden producir con el router real justamente porque el
    router real esta bien.
    """
    app = FastAPI()

    @app.get("/api/resumen")
    def resumen():
        if status >= 400:
            raise HTTPException(status, "algo salio mal")
        if isinstance(cuerpo, str):
            return HTMLResponse(cuerpo)
        return cuerpo

    return app


def _parchear_nucleo(monkeypatch, datos: dict) -> None:
    monkeypatch.setattr(
        "libracore.resumen_router.get_resumen_core",
        lambda desde, hasta: datos,
    )
