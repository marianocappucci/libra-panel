"""Configuracion del panel, toda por entorno.

**El panel tiene base de datos, pero no de negocio.** Guarda sus usuarios y el
registro de que sucursales existen. Ningun numero de ventas se copia nunca: eso
se pregunta y se descarta. Si se guardaran, habria dos verdades sobre la misma
plata y una de las dos quedaria vieja.

Ver `wiki/analyses/panel-del-dueno-multisucursal.md`.
"""
import os
from dataclasses import dataclass


class ConfiguracionInvalida(RuntimeError):
    """El entorno no alcanza para levantar el panel."""


#: Timeout por sucursal, en segundos. **Corto a proposito.** Una sucursal
#: colgada no puede dejar al dueño mirando un spinner: pasado esto, esa
#: sucursal pasa a "sin respuesta" y el resto se muestra igual.
TIMEOUT_POR_DEFECTO = 6.0


@dataclass(frozen=True)
class Settings:
    #: Nombre para mostrar. El panel es transversal —sirve para un grupo de
    #: Contalibra igual que para uno de VentaLibra—, asi que el branding sale
    #: del entorno y no hay una rama por producto en ningun lado.
    panel_name: str
    database_url: str
    timeout_sucursal: float
    #: Donde aterriza el link del mail de recupero. Sin esto el recupero existe
    #: igual, pero el mail apunta a una URL que no es la del cliente.
    reset_url_base: str

    @property
    def es_desarrollo(self) -> bool:
        return os.environ.get("ENV", "production") == "development"


def cargar_settings(env: dict | None = None) -> Settings:
    """Arma los settings desde el entorno y **falla al arrancar** si falta algo.

    Fallar aca y no en la primera request es deliberado: un panel que levanta y
    recien revienta cuando el dueño abre la pantalla es un despliegue que
    parece exitoso.
    """
    env = os.environ if env is None else env

    database_url = (env.get("LIBRA_PANEL_DATABASE_URL") or "").strip()
    if not database_url:
        raise ConfiguracionInvalida(
            "Falta LIBRA_PANEL_DATABASE_URL: la base propia del panel "
            "(usuarios y registro de sucursales). PostgreSQL, como el resto de "
            "la familia."
        )

    crudo = (env.get("TIMEOUT_SUCURSAL") or "").strip()
    try:
        timeout = float(crudo) if crudo else TIMEOUT_POR_DEFECTO
    except ValueError:
        raise ConfiguracionInvalida(
            f"TIMEOUT_SUCURSAL={crudo!r} no es un numero de segundos."
        ) from None
    if timeout <= 0:
        raise ConfiguracionInvalida(
            "TIMEOUT_SUCURSAL tiene que ser mayor que cero: sin timeout, una "
            "sola sucursal colgada cuelga la pantalla entera."
        )

    return Settings(
        panel_name=(env.get("PANEL_NAME") or "Panel").strip(),
        database_url=database_url,
        timeout_sucursal=timeout,
        reset_url_base=(env.get("LIBRA_PANEL_RESET_URL_BASE") or "").strip(),
    )
