"""Las dos tablas propias del panel.

🔴 **Cuelgan del `Base` de [[libraauth]], no de uno propio.** No es prolijidad:
`usuario_sucursales.usuario_id` declara una FK a `usuarios.id`, y una FK se
resuelve dentro del **mismo `MetaData`**. Con un `DeclarativeBase` propio,
`create_all()` no encuentra la tabla `usuarios` y corta con
`NoReferencedTableError: could not find table 'usuarios'` — la app no levanta.

Es la misma decision que ya toman `PasswordResetToken` y `SmtpSettings` dentro
de libraauth por el mismo motivo, y la razon por la que alcanza con **un solo**
`create_all` en `create_app`.

> Lo encontro la suite contra PostgreSQL apenas se creo la primera sucursal.
> Es exactamente el tipo de defecto que SQLite no habria mostrado: con el
> pragma de FKs apagado la tabla se crea igual y la constraint no existe.

🔑 **Ningun numero de negocio vive aca.** No hay tabla de facturado, de ventas
ni de caja. El panel pregunta y descarta; si guardara, habria dos verdades
sobre la misma plata y una de las dos quedaria vieja.
"""
from datetime import datetime

from libraauth.models import Base
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column


class Sucursal(Base):
    """Una sucursal: una instancia de un producto de la familia, con su URL y
    su credencial propia.

    > El analisis la llamaba tabla `instancias`. Se llama `sucursales` porque
    > es la palabra que usa todo el resto de esta pantalla y la que reconoce el
    > dueño; "instancia" es nuestra palabra de despliegue y en el panel no
    > aporta nada.
    """

    __tablename__ = "sucursales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    #: Identificador estable en la URL y en las respuestas. No es el slug de la
    #: instancia en el VPS necesariamente: es como la nombra este panel.
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Base a la que se le pega `/api/resumen`. En el VPS es el nombre del
    #: contenedor en la red de control (`http://contalibra:8000`): el trafico
    #: del panel no sale a internet. Con dominio publico tambien funciona.
    url_base: Mapped[str] = mapped_column(String(300), nullable=False)
    #: El CUIT **del registro**, cargado en el alta. Es el que agrupa, incluso
    #: cuando la sucursal no contesta — ver `consolidado.agrupar_por_cuit`.
    cuit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    #: Razon social del registro, para nombrar el grupo por CUIT en la pantalla.
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # 🔴 **La credencial se guarda CIFRADA, no en claro.**
    #
    # Es distinto del caso SMTP de libra-backoffice, donde el que descifra es
    # otro proceso y por eso el backoffice no puede cifrar: aca el unico que
    # lee esta credencial es este mismo panel, con su propio `SECRET_KEY`. O
    # sea que cifrar no cuesta nada y un dump de la base deja de alcanzar para
    # leerle los numeros a las sucursales de un cliente.
    #
    # Es una credencial POR SUCURSAL, distinta del `LIBRA_SERVICE_TOKEN` del
    # producto: ese es uno solo, compartido por todas las instancias del mismo
    # producto —medido el 2026-08-20: `libradesk-lagrace` y
    # `libradesk-compulibra`, dos clientes distintos, tienen el mismo—, asi que
    # darselo a un cliente le abriria las instancias de los demas.
    credencial_cifrada: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: Baja logica. Una sucursal desactivada no se consulta y no cuenta para el
    #: "N de M": el dueño cerro ese local, no es que no conteste.
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UsuarioSucursal(Base):
    """Que sucursales ve cada usuario.

    **Esta tabla ES el aislamiento entre clientes.** No hay una entidad
    "grupo" ni un despliegue por dueño: toda consulta de numeros se filtra por
    las filas de aca, para todos los roles sin excepcion. Un dueño nuevo son
    filas nuevas.

    Existe desde el dia uno aunque hoy haya un solo usuario que ve las cinco
    sucursales, porque agregarla despues es migrar datos y revisar cada
    consulta. Cuesta una tabla ahora.
    """

    __tablename__ = "usuario_sucursales"
    __table_args__ = (
        # Sin esto, asignar dos veces la misma sucursal al mismo usuario
        # duplicaria la fila y la sucursal entraria DOS VECES en el
        # consolidado: el facturado saldria al doble, con cara de numero
        # correcto. Lo impide la base, no el router.
        UniqueConstraint("usuario_id", "sucursal_id", name="uq_usuario_sucursal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sucursal_id: Mapped[int] = mapped_column(
        ForeignKey("sucursales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


#: Roles del panel. **Dos, y significan cosas distintas de las de un producto.**
#:
#: - `admin`: nosotros. Da de alta sucursales, carga credenciales y asigna quien
#:   ve que. Es el unico rol que administra el registro.
#: - `socio`: el cliente. Mira los numeros de las sucursales que tiene
#:   asignadas y nada mas.
#:
#: 🔴 **`admin` NO ve los numeros de todo el mundo.** El ABM del registro es
#: global, pero `/api/resumen` se filtra por `usuario_sucursales` para todos
#: los roles: un admin sin asignaciones ve un panel vacio, y eso es lo correcto.
#: Sumar las sucursales de clientes distintos daria un numero que no significa
#: nada.
ROLES = ("admin", "socio")

#: El campo `role` de un `Usuario` de libraauth es `String(20)`; los dos
#: entran holgados.
ROL_POR_DEFECTO = "socio"
