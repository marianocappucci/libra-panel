"""El registro de sucursales y quien ve cada una.

**La credencial nunca sale por la API.** Los diccionarios que devuelve este
modulo llevan `tiene_credencial: bool` y no el valor: el unico camino por el
que la credencial descifrada sale de aca es `credencial_de()`, que la usa el
cliente HTTP para armar el header. Una pantalla que mostrara la credencial
seria una forma de filtrarla que ningun `.gitignore` tapa.
"""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from libraauth.crypto import ClaveDeCifradoAusente, SecretoIndescifrable, cifrar, descifrar
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Sucursal, UsuarioSucursal


@dataclass(frozen=True)
class SucursalParaConsultar:
    """Una sucursal con su credencial YA descifrada, lista para preguntarle.

    Es una dataclass y no un `dict` a proposito: los diccionarios de este
    modulo se devuelven tal cual por la API, y una credencial dentro de uno de
    ellos se filtraria sola el dia que alguien agregue un campo al listado.
    Esto no se serializa por accidente — hay que sacarle los campos a mano.
    """

    slug: str
    nombre: str
    url_base: str
    cuit: str
    razon_social: str
    credencial: str
    #: Por que no hay credencial utilizable, si no la hay. Va a parar al
    #: detalle de la fila "sin respuesta", que es donde se puede leer.
    problema: str = ""


class SlugTomado(Exception):
    """Ya hay una sucursal con ese slug."""


class SucursalDesconocida(Exception):
    """No existe una sucursal con ese slug."""


class AsignacionDesconocida(Exception):
    """Ese usuario no tiene asignada esa sucursal.

    Se distingue de `SucursalDesconocida` a proposito: son dos arreglos
    distintos ---dar de alta la sucursal, o asignarsela al socio--- y un solo
    mensaje mandaria a mirar el lugar equivocado.
    """


class ParticipacionInvalida(Exception):
    """Un porcentaje fuera de 0..100."""


class CredencialIlegible(Exception):
    """La credencial guardada no se puede descifrar con la clave actual.

    El caso realista no es un ataque: es que se roto el `SECRET_KEY` del panel.
    Se trata como "sin credencial" y la sucursal aparece sin respuesta con un
    detalle que lo dice, en vez de tumbar la pantalla entera — que es la
    diferencia entre "no puedo leer una de cinco" y "no puedo leer ninguna".
    """


def _a_dict(s: Sucursal) -> dict:
    return {
        "slug": s.slug,
        "nombre": s.nombre,
        "url_base": s.url_base,
        "cuit": s.cuit or "",
        "razon_social": s.razon_social or "",
        "activa": bool(s.activa),
        "tiene_credencial": bool(s.credencial_cifrada),
    }


class RegistroDeSucursales:
    def __init__(self, session_factory: Callable[[], AbstractContextManager[Session]]):
        self.session_factory = session_factory

    # ── Lectura ─────────────────────────────────────────────────────────────

    def listar(self, *, solo_activas: bool = False) -> list[dict]:
        """Todas las sucursales del registro. **Es la vista de admin.**

        No la usa `/api/resumen`: ahi se usa `listar_de_usuario`, siempre, para
        todos los roles.
        """
        with self.session_factory() as session:
            q = select(Sucursal).order_by(Sucursal.razon_social, Sucursal.nombre)
            if solo_activas:
                q = q.where(Sucursal.activa.is_(True))
            return [_a_dict(s) for s in session.execute(q).scalars()]

    def listar_de_usuario(self, usuario_id: str | int, *, solo_activas: bool = True) -> list[dict]:
        """Las sucursales asignadas a un usuario.

        🔴 **Es el unico camino por el que se arma un consolidado**, sin
        excepcion de rol. Un admin no asignado ve cero sucursales, y eso es lo
        correcto: sumar las de clientes distintos daria un numero que no
        significa nada.
        """
        try:
            uid = int(usuario_id)
        except (TypeError, ValueError):
            # Un usuario sin id numerico no es un usuario de la tabla (el
            # `SERVICE_USER` de libraauth, por ejemplo). No ve ninguna.
            return []
        with self.session_factory() as session:
            q = (
                select(Sucursal)
                .join(UsuarioSucursal, UsuarioSucursal.sucursal_id == Sucursal.id)
                .where(UsuarioSucursal.usuario_id == uid)
                .order_by(Sucursal.razon_social, Sucursal.nombre)
            )
            if solo_activas:
                q = q.where(Sucursal.activa.is_(True))
            return [_a_dict(s) for s in session.execute(q).scalars()]

    def obtener(self, slug: str) -> dict | None:
        with self.session_factory() as session:
            s = self._buscar(session, slug)
            return _a_dict(s) if s else None

    def usuarios_de(self, slug: str) -> list[int]:
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            filas = session.execute(
                select(UsuarioSucursal.usuario_id).where(UsuarioSucursal.sucursal_id == s.id)
            ).scalars()
            return sorted(filas)

    def sucursales_de_usuario_ids(self, usuario_id: str | int) -> list[str]:
        return [s["slug"] for s in self.listar_de_usuario(usuario_id, solo_activas=False)]

    def para_consultar(self, usuario_id: str | int) -> list[SucursalParaConsultar]:
        """Las sucursales de un usuario con la credencial ya descifrada.

        Se resuelve todo aca —una consulta y N descifrados en memoria— para que
        el router no tenga que tocar la base una vez por sucursal en medio de
        las llamadas en paralelo: cada una de esas consultas es sincrona y
        bloquearia el loop mientras las N esperan la red.

        Una credencial que no se puede descifrar **no tumba la consulta**: esa
        sucursal sale con `problema` cargado y el resto se consulta igual. La
        diferencia entre "no puedo leer una de cinco" y "no puedo leer ninguna".
        """
        salida = []
        for s in self.listar_de_usuario(usuario_id, solo_activas=True):
            credencial, problema = "", ""
            try:
                credencial = self.credencial_de(s["slug"])
            except CredencialIlegible:
                problema = (
                    "La credencial guardada no se puede descifrar. Suele ser "
                    "que se roto el SECRET_KEY del panel: hay que volver a "
                    "cargarla."
                )
            if not credencial and not problema:
                problema = "Esta sucursal no tiene credencial cargada en el panel."
            salida.append(
                SucursalParaConsultar(
                    slug=s["slug"],
                    nombre=s["nombre"],
                    url_base=s["url_base"],
                    cuit=s["cuit"],
                    razon_social=s["razon_social"],
                    credencial=credencial,
                    problema=problema,
                )
            )
        return salida

    def credencial_de(self, slug: str) -> str:
        """La credencial en claro. Solo para armar el header `X-Panel-Auth`."""
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            blob = s.credencial_cifrada or ""
        if not blob:
            return ""
        try:
            return descifrar(blob)
        except (SecretoIndescifrable, ClaveDeCifradoAusente) as exc:
            raise CredencialIlegible(str(exc)) from exc

    # ── Escritura ───────────────────────────────────────────────────────────

    def crear(
        self, *, slug: str, nombre: str, url_base: str, cuit: str = "",
        razon_social: str = "", credencial: str = "", activa: bool = True,
    ) -> dict:
        with self.session_factory() as session:
            s = Sucursal(
                slug=slug.strip(),
                nombre=nombre.strip(),
                url_base=url_base.strip().rstrip("/"),
                cuit=(cuit or "").strip(),
                razon_social=(razon_social or "").strip(),
                credencial_cifrada=_cifrar_o_vacio(credencial),
                activa=activa,
            )
            session.add(s)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                if "slug" in str(exc.orig).lower():
                    raise SlugTomado(slug.strip()) from exc
                raise
            session.refresh(s)
            return _a_dict(s)

    def actualizar(
        self, slug: str, *, nombre: str | None = None, url_base: str | None = None,
        cuit: str | None = None, razon_social: str | None = None,
        credencial: str | None = None, activa: bool | None = None,
    ) -> dict:
        """`credencial=None` **deja la guardada como esta**, no la borra.

        Es la misma regla que `UserRepository.update` con el email, y por el
        mismo motivo: la pantalla nunca recibe la credencial, asi que si
        mandara siempre el campo del formulario mandaria vacio — y editarle el
        nombre a una sucursal le borraria la credencial. Para borrarla de
        verdad hay que mandar la cadena vacia explicitamente.
        """
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            if nombre is not None:
                s.nombre = nombre.strip()
            if url_base is not None:
                s.url_base = url_base.strip().rstrip("/")
            if cuit is not None:
                s.cuit = cuit.strip()
            if razon_social is not None:
                s.razon_social = razon_social.strip()
            if credencial is not None:
                s.credencial_cifrada = _cifrar_o_vacio(credencial)
            if activa is not None:
                s.activa = activa
            session.commit()
            session.refresh(s)
            return _a_dict(s)

    def eliminar(self, slug: str) -> None:
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            session.delete(s)
            session.commit()

    def asignar(self, slug: str, usuario_ids: list[int]) -> list[int]:
        """Fija **el conjunto completo** de usuarios que ven esta sucursal.

        Reemplaza en vez de agregar: la pantalla manda la lista entera, asi que
        un id que no viene es un permiso que se saca. Agregar sin sacar dejaria
        sin forma de revocar desde la interfaz.
        """
        quedan = sorted({int(u) for u in usuario_ids})
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            # 🔴 **La participación de los que SIGUEN se conserva.** Esta función
            # borra y reinserta, así que sin esto reasignar la membresía ---sacar
            # a un socio, agregar a otro--- le pondría la participación en cero a
            # todos los demás. Y en silencio: la pantalla de asignación no
            # muestra porcentajes, así que nadie vería el momento en que se
            # perdieron.
            previas = {
                f.usuario_id: f.participacion
                for f in session.execute(
                    select(UsuarioSucursal).where(UsuarioSucursal.sucursal_id == s.id)
                ).scalars()
            }
            session.execute(
                delete(UsuarioSucursal).where(UsuarioSucursal.sucursal_id == s.id)
            )
            for uid in quedan:
                session.add(UsuarioSucursal(
                    usuario_id=uid, sucursal_id=s.id,
                    participacion=previas.get(uid, Decimal("0")),
                ))
            session.commit()
        return quedan

    def fijar_participacion(self, slug: str, usuario_id: int, participacion) -> Decimal:
        """El porcentaje de un socio en una sucursal. Devuelve el que quedó.

        🔑 **Es un dato informativo y no toca ningún número.** El socio ve la
        facturación completa de las sucursales donde participa; el porcentaje se
        muestra al lado. Ver el comentario de la columna.

        Exige que la asignación exista: fijarle participación a alguien que no
        ve la sucursal sería crear el permiso por la puerta de atrás.
        """
        valor = Decimal(str(participacion)).quantize(Decimal("0.01"))
        if valor < 0 or valor > 100:
            raise ParticipacionInvalida(
                f"La participación tiene que estar entre 0 y 100 (llegó {valor})."
            )
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            fila = session.execute(
                select(UsuarioSucursal).where(
                    UsuarioSucursal.sucursal_id == s.id,
                    UsuarioSucursal.usuario_id == int(usuario_id),
                )
            ).scalar_one_or_none()
            if fila is None:
                raise AsignacionDesconocida(
                    f"El usuario {usuario_id} no tiene asignada la sucursal {slug!r}."
                )
            fila.participacion = valor
            session.commit()
        return valor

    def participaciones_de(self, slug: str) -> dict[int, Decimal]:
        """`{usuario_id: participacion}` de esa sucursal, para la pantalla."""
        with self.session_factory() as session:
            s = self._exigir(session, slug)
            filas = session.execute(
                select(UsuarioSucursal).where(UsuarioSucursal.sucursal_id == s.id)
            ).scalars()
            return {f.usuario_id: f.participacion for f in filas}

    # ── Internos ────────────────────────────────────────────────────────────

    def _buscar(self, session: Session, slug: str) -> Sucursal | None:
        return session.execute(
            select(Sucursal).where(Sucursal.slug == slug)
        ).scalar_one_or_none()

    def _exigir(self, session: Session, slug: str) -> Sucursal:
        s = self._buscar(session, slug)
        if s is None:
            raise SucursalDesconocida(slug)
        return s


def _cifrar_o_vacio(credencial: str | None) -> str:
    """Cifra, salvo que la credencial venga vacia.

    Una credencial vacia se guarda como cadena vacia y no como un blob que
    descifra a "": asi `tiene_credencial` puede distinguir "no le cargaron
    ninguna" de "le cargaron una", que es la diferencia entre un alta a medio
    hacer y una sucursal lista.
    """
    if not (credencial or "").strip():
        return ""
    return cifrar(credencial.strip())
