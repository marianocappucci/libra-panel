"""Dependencias compartidas de los routers.

`SessionAuth.require_admin` de libraauth existe pero redirige (307 a `/login`),
que es lo correcto para un backoffice server-rendered y lo equivocado para una
SPA: el `fetch` seguiria el redirect y le devolveria HTML al `api-client`. Los
guards JSON del mismo modulo (`json_api_*`) son los que contestan 401/403, y
son los que se usan aca.
"""
from fastapi import Request
from libraauth.session_auth import json_api_get_current_user, json_api_require_role

#: El usuario de la sesion, o 401 JSON.
usuario_actual = json_api_get_current_user

#: Solo nosotros: alta de sucursales, credenciales, usuarios y asignaciones.
#: El cliente (`socio`) no toca nada de esto.
requiere_admin = json_api_require_role("admin")


def get_registro(request: Request):
    return request.app.state.registro


def get_cliente(request: Request):
    return request.app.state.cliente_sucursal
