"""La participacion del socio en una sucursal.

**Decision del humano el 2026-08-29: es un dato, no un calculo.** El socio ve los
numeros COMPLETOS de las sucursales donde participa, y el porcentaje se muestra
al lado como referencia. La otra lectura ---que viera "su parte"--- arrastra
decisiones que no son de software y se descarto.

Lo que estos tests fijan, en orden de importancia:

1. 🔴 **La participacion NO toca ningun numero.** Es lo que distingue la lectura
   elegida de la otra, y lo unico que impide que alguien la use para multiplicar
   sin volver a decidirlo.
2. 🔴 **Reasignar la membresia no borra los porcentajes** de los socios que
   siguen. `asignar` borra y reinserta.
3. La columna se agrega sobre un panel ya desplegado ---`create_all` no lo hace---.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from libra_panel import db
from libra_panel.repositorio import AsignacionDesconocida, ParticipacionInvalida


@pytest.fixture
def registro(app):
    return app.state.registro


def socio(app, nombre: str) -> int:
    """Un socio de verdad. La FK contra `usuarios` se aplica en PostgreSQL, asi
    que un id inventado no sirve ---y que no sirva es lo correcto: esta tabla es
    el aislamiento entre clientes---."""
    creado = app.state.users.create(
        username=nombre, name=nombre.title(), password=f"clave-{nombre}", role="socio"
    )
    return int(creado["id"])


def crear(registro, slug="c1", **kw):
    datos = {
        "slug": slug, "nombre": slug.title(), "url_base": "http://c1:8000",
        "cuit": "30-71234567-9", "razon_social": "Padel SA", "credencial": "secreta-1",
    }
    datos.update(kw)
    return registro.crear(**datos)


# -- Lo que mas importa ------------------------------------------------------


def test_LA_PARTICIPACION_NO_TOCA_NINGUN_NUMERO(app, registro):
    """🔴 Es la diferencia entre las dos lecturas, y la eligio el humano.

    Con participacion como FILTRO, el socio ve la facturacion completa de las
    sucursales donde participa. Si algun dia alguien multiplica por este
    porcentaje, eso es la otra lectura ---la de "su parte"--- y hay que
    decidirla de nuevo, no deducirla de que la columna existe.

    Se mide sobre lo que el panel devuelve: la lista de sucursales de un usuario
    tiene que ser identica con 30% que con 100%.
    """
    uno = socio(app, "uno")
    crear(registro, "c1")
    registro.asignar("c1", [uno])

    registro.fijar_participacion("c1", uno, 30)
    con_30 = registro.listar_de_usuario(uno)
    registro.fijar_participacion("c1", uno, 100)
    con_100 = registro.listar_de_usuario(uno)

    assert con_30 == con_100, (
        "la participacion esta cambiando lo que ve el socio: eso es la otra lectura"
    )
    # Y el control de que el test mide algo: la participacion SI cambio.
    assert registro.participaciones_de("c1")[uno] == Decimal("100.00")


def test_REASIGNAR_LA_MEMBRESIA_NO_BORRA_LOS_PORCENTAJES(app, registro):
    """🔴 `asignar` borra y reinserta el conjunto entero.

    Sin conservar, sacar a un socio de la lista le pondria la participacion en
    cero a todos los demas ---y en silencio, porque la pantalla de asignacion no
    muestra porcentajes---.
    """
    uno, dos, tres = socio(app, "uno"), socio(app, "dos"), socio(app, "tres")
    crear(registro, "c1")
    registro.asignar("c1", [uno, dos])
    registro.fijar_participacion("c1", uno, 60)
    registro.fijar_participacion("c1", dos, 40)

    # Se saca a `dos` y entra `tres`.
    registro.asignar("c1", [uno, tres])

    quedaron = registro.participaciones_de("c1")
    assert quedaron[uno] == Decimal("60.00"), (
        f"la participacion del socio que sigue se perdio: {quedaron}"
    )
    # El que entra arranca en cero: no se hereda nada de nadie.
    assert quedaron[tres] == Decimal("0.00")
    # Y el que salio no esta.
    assert dos not in quedaron


def _columnas_de_asignaciones() -> set[str]:
    with db.get_engine().begin() as conn:
        return {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='usuario_sucursales'"
        ))}


def test_EL_ARRANQUE_AGREGA_LA_COLUMNA_sobre_un_panel_ya_desplegado(app, settings):
    """🔴 `create_all` NO agrega columnas a una tabla que ya existe.

    Un panel que ya estaba corriendo se habria quedado sin la columna, y el
    error no aparece al arrancar sino cuando alguien abre la seccion.

    ⚠️ **Se pasa por `create_app` y no se llama a la funcion directo.** La
    primera version de este test invocaba `_agregar_participacion_si_falta(engine)`
    a mano: probaba que la funcion anda, no que el arranque la corra. La
    mutacion de sacar la llamada de `create_app` **sobrevivia** ---y sacar esa
    llamada es exactamente el defecto que este test tiene que atrapar---.

    Tampoco se usa la fixture `crear_app`: esa DROPEA las tablas antes, asi que
    el schema saldria nuevo y el ALTER seria un no-op. Lo que se quiere simular
    es una tabla vieja, con datos, a la que le falta la columna.
    """
    from libra_panel.app import create_app

    with db.get_engine().begin() as conn:
        conn.execute(text("ALTER TABLE usuario_sucursales DROP COLUMN participacion"))
    # Control del punto de partida: la columna NO esta, o el test no mide nada.
    assert "participacion" not in _columnas_de_asignaciones()

    # El camino real: levantar la app sobre esa base.
    create_app(settings=settings)
    assert "participacion" in _columnas_de_asignaciones(), (
        "el arranque no agrego la columna: una instancia ya desplegada se queda sin ella"
    )


def test_arrancar_dos_veces_no_revienta(app, settings):
    """El ALTER es idempotente. Sin esto, el segundo arranque de un contenedor
    ---un `restart`, un redeploy--- tumbaria la app con "column already exists"."""
    from libra_panel.app import create_app

    create_app(settings=settings)
    create_app(settings=settings)
    assert "participacion" in _columnas_de_asignaciones()


def test_las_filas_que_ya_estaban_quedan_en_cero_y_SIGUEN_VIENDO(app, registro):
    """La participacion no es lo que da acceso: eso lo da la fila.

    Un socio asignado antes de que existiera la columna tiene que seguir viendo
    sus sucursales mientras el porcentaje se completa.
    """
    from libra_panel.app import _agregar_participacion_si_falta

    uno = socio(app, "uno")
    crear(registro, "c1")
    registro.asignar("c1", [uno])

    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE usuario_sucursales DROP COLUMN participacion"))
    _agregar_participacion_si_falta(engine)

    assert [s["slug"] for s in registro.listar_de_usuario(uno)] == ["c1"]
    assert registro.participaciones_de("c1")[uno] == Decimal("0.00")


# -- Validacion --------------------------------------------------------------


def test_un_porcentaje_fuera_de_rango_no_entra(app, registro):
    uno = socio(app, "uno")
    crear(registro, "c1")
    registro.asignar("c1", [uno])
    with pytest.raises(ParticipacionInvalida):
        registro.fijar_participacion("c1", uno, 101)
    with pytest.raises(ParticipacionInvalida):
        registro.fijar_participacion("c1", uno, -1)
    # El control: uno valido si entra.
    assert registro.fijar_participacion("c1", uno, 100) == Decimal("100.00")


def test_LA_BASE_TAMBIEN_LO_IMPIDE(app, registro):
    """🔴 La validacion del repositorio no es el unico camino de escritura.

    `asignar` escribe la misma tabla sin pasar por `fijar_participacion`. Con la
    validacion solo en el router o solo en el repositorio, ese otro camino queda
    abierto. Se prueba contra la base, salteando el repositorio.
    """
    from sqlalchemy.exc import IntegrityError

    uno = socio(app, "uno")
    crear(registro, "c1")
    registro.asignar("c1", [uno])
    with pytest.raises(IntegrityError):
        with db.get_engine().begin() as conn:
            conn.execute(
                text("UPDATE usuario_sucursales SET participacion = 150 "
                     "WHERE usuario_id = :uid"),
                {"uid": uno},
            )


def test_fijarle_participacion_a_quien_no_ve_la_sucursal_no_se_puede(app, registro):
    """Seria crear el permiso por la puerta de atras: el acceso lo da la fila."""
    uno, otro = socio(app, "uno"), socio(app, "otro")
    crear(registro, "c1")
    registro.asignar("c1", [uno])
    with pytest.raises(AsignacionDesconocida):
        registro.fijar_participacion("c1", otro, 50)


def test_los_decimales_se_conservan(app, registro):
    """Un tercio de una sociedad es 33,33 y no 33."""
    uno = socio(app, "uno")
    crear(registro, "c1")
    registro.asignar("c1", [uno])
    assert registro.fijar_participacion("c1", uno, "33.33") == Decimal("33.33")
    assert registro.participaciones_de("c1")[uno] == Decimal("33.33")
