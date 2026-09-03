"""ABM de usuarios del panel. **Solo admin.**

No sale de [[libraauth]] porque el router de usuarios **no es de libraauth**:
cada producto tiene el suyo, con su vocabulario de roles. El contrato que
implementa es el que espera el componente `Usuarios` de [[libra-ui]] —
`GET/POST <base>`, `PUT <base>/{id}`, `PUT <base>/{id}/password`— para poder
reusar esa pantalla tal cual.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from libraauth.repository import UsernameTaken
from pydantic import BaseModel, Field

from ..deps import requiere_admin
from ..models import ROL_POR_DEFECTO, ROLES

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"], dependencies=[Depends(requiere_admin)])

#: Minimo de la contrasena. **El mismo que `build_json_api_auth_router`**
#: (`min_password_length=6`) y que `PasswordResetService`: tres caminos que
#: fijan la contrasena del mismo usuario no pueden pedir cosas distintas — el
#: mas laxo volveria decorativos a los otros dos.
MIN_PASSWORD = 6


class UsuarioIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD)
    email: str = ""
    role: str = ROL_POR_DEFECTO


class UsuarioPatch(BaseModel):
    name: str
    role: str
    active: bool
    email: str | None = None


class PasswordIn(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD)


def _validar_rol(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(422, f"Rol invalido: {role!r}. Los validos son {list(ROLES)}.")
    return role


@router.get("")
def listar(request: Request):
    return request.app.state.users.list()


@router.post("", status_code=201)
def crear(datos: UsuarioIn, request: Request):
    _validar_rol(datos.role)
    try:
        return request.app.state.users.create(
            username=datos.username, name=datos.name, password=datos.password,
            role=datos.role, email=datos.email,
        )
    except UsernameTaken:
        raise HTTPException(409, f"El usuario {datos.username!r} ya existe.") from None


@router.put("/{user_id}")
def actualizar(user_id: str, datos: UsuarioPatch, request: Request, actual: dict = Depends(requiere_admin)):
    _validar_rol(datos.role)
    users = request.app.state.users
    if users.get_by_id(user_id) is None:
        raise HTTPException(404, "No existe ese usuario.")
    # 🔴 Un admin no puede desactivarse ni bajarse de rol a si mismo. Con un
    # solo admin —que es el caso hoy— eso deja el panel sin nadie que pueda
    # dar de alta sucursales ni usuarios, y la unica salida es entrar a la base
    # a mano. La guarda es sobre uno mismo y no sobre "el ultimo admin" porque
    # es la equivocacion realista: uno editandose la fila.
    if str(actual["id"]) == str(user_id) and (not datos.active or datos.role != "admin"):
        raise HTTPException(
            409,
            "No podes desactivarte ni sacarte el rol admin a vos mismo. "
            "Pedile a otro admin que lo haga.",
        )
    return users.update(
        user_id, name=datos.name, role=datos.role, active=datos.active, email=datos.email,
    )


@router.put("/{user_id}/password")
def cambiar_password(user_id: str, datos: PasswordIn, request: Request):
    """Le fija la contrasena a OTRO usuario. Pide rol admin y no la actual.

    El camino para cambiar la propia estando adentro es
    `POST /api/auth/change-password`, que pide la contrasena vigente y saca el
    usuario de la cookie. Son dos cosas distintas y por eso son dos endpoints.
    """
    users = request.app.state.users
    if users.get_by_id(user_id) is None:
        raise HTTPException(404, "No existe ese usuario.")
    users.update_password(user_id, datos.password)
    return {"ok": True}
