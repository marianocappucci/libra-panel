"""Engine y session factory del panel.

Una sola base y un solo engine: la tabla `usuarios` de [[libraauth]] y las dos
tablas propias del panel (`sucursales` y `usuario_sucursales`) viven juntas.
`usuario_sucursales` tiene FK a las dos, y una FK resuelve contra la tabla que
este en la misma base — separarlas dejaria la asignacion sin poder declararse.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_session_factory: sessionmaker | None = None


def configure(database_url: str) -> None:
    """Configura el engine. **El panel corre sobre PostgreSQL y nada mas.**

    Se rechaza cualquier otro destino en vez de aceptarlo callado (decision de
    familia del 2026-08-12): una URL `sqlite://` aca levanta la app con un
    motor donde las FK no se chequean y los tipos son dinamicos, o sea que los
    defectos que PostgreSQL rechaza de entrada pasan desapercibidos hasta
    produccion. Misma guarda que `libradesk/app/database.py`.
    """
    global _engine, _session_factory
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        esquema = database_url.split("://")[0]
        raise ValueError(f"El panel requiere PostgreSQL y recibio: {esquema}://…")
    # 🔴 `postgresql://` a secas hay que normalizarlo ANTES de `create_engine`.
    # SQLAlchemy resuelve el esquema pelado al dialecto psycopg2, que no esta
    # instalado (la dependencia es `psycopg[binary]`, psycopg 3), y falla al
    # IMPORTARSE: el contenedor ni llega a levantar. Las dos formas existen en
    # el parque porque LibraCore conecta con `psycopg.connect()`, que acepta la
    # forma libpq. Normalizar aca es lo que hace que el panel arranque
    # cualquiera sea la forma en que se escribio el compose.
    url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    # `pool_pre_ping` evita entregar una conexion que el sidecar cerro durante
    # un restart.
    _engine = create_engine(url, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine)


def get_engine():
    if _engine is None:
        raise RuntimeError("db.configure() no se llamo todavia.")
    return _engine


def get_session_factory() -> sessionmaker:
    if _session_factory is None:
        raise RuntimeError("db.configure() no se llamo todavia.")
    return _session_factory
