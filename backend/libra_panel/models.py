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
from decimal import Decimal

from libraauth.models import Base
from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text,
    UniqueConstraint, func,
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

    #: Donde vive el router de usuarios de ESTA sucursal, para aprovisionar
    #: empleados.
    #:
    #: 🔴 **No es la misma en todos los productos, y por eso es un campo.**
    #: Medido el 2026-08-29: `/api/usuarios` en LibraClub, LibraCargo,
    #: LibraDesk, Contalibra y Restolibra; **`/users`** en VentaLibra, MedLibra
    #: y Gestiolibra. El router de usuarios no es de libraauth ---cada producto
    #: tiene el suyo--- asi que no hay una convencion que asumir. Es la misma
    #: razon por la que `libra-backoffice` lleva su `USERS_PATH` configurable.
    #:
    #: El default es el de la mayoria; una sucursal de los otros tres se corrige
    #: en el alta. Adivinarlo probando las dos rutas seria peor: los productos
    #: sirven una SPA con fallback, asi que una ruta que no existe puede
    #: contestar 200 con HTML en vez de 404.
    ruta_de_usuarios: Mapped[str] = mapped_column(
        String(200), nullable=False, default="/api/usuarios",
        server_default="/api/usuarios",
    )

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
        # Un porcentaje fuera de 0..100 no significa nada, y lo impide la base y
        # no el router: el repositorio no es el unico que escribe esta tabla
        # ---la escribe tambien el `asignar` que reemplaza el conjunto--- y una
        # validacion en un solo camino deja el otro abierto.
        CheckConstraint(
            "participacion >= 0 AND participacion <= 100",
            name="ck_participacion_0_100",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sucursal_id: Mapped[int] = mapped_column(
        ForeignKey("sucursales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Que porcentaje de esta sucursal le corresponde a este socio.
    #:
    #: 🔑 **Es un dato, no un calculo.** Decision del humano el 2026-08-29,
    #: entre las dos lecturas que planteaba el analisis: el socio ve los numeros
    #: **completos** de las sucursales donde participa, y el porcentaje se
    #: muestra al lado como referencia. La otra lectura ---que viera "su parte",
    #: el 30% de la facturacion--- arrastra decisiones que no son de software:
    #: si la participacion cambio a mitad de año, si el historico se recalcula,
    #: si se prorratean los gastos o solo los ingresos.
    #:
    #: ⚠️ Por eso **ninguna consulta de numeros la mira**. Si algun dia alguien
    #: la usa para multiplicar, eso es la otra lectura y hay que decidirla de
    #: nuevo, no deducirla de que la columna existe.
    #:
    #: `0` no significa "no participa" sino "no se cargo": la participacion no
    #: es lo que da acceso ---eso lo da la fila--- y arrancar en cero es lo que
    #: permite asignar primero y completar despues.
    participacion: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0"
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
