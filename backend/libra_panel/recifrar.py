"""Cierra una rotacion de `SECRET_KEY`: deja las credenciales bajo la clave viva.

    docker exec <contenedor> python -m libra_panel.recifrar --ver
    docker exec <contenedor> python -m libra_panel.recifrar

**Cuando se usa.** Despues de rotar el `SECRET_KEY` del panel, con el valor
anterior declarado en `LIBRAAUTH_CLAVES_ANTERIORES`. Mientras haya credenciales
cifradas con la clave vieja, sacar esa variable dejaria a esas sucursales sin
credencial — o sea que la rotacion **todavia no termino**.

El ciclo completo es: rotar, declarar el valor viejo, correr esto, y **sacar la
variable**. Este comando es el unico paso que no se puede saltear sin perder
algo.

**Por que un modulo y no un endpoint.** Es una operacion de servidor que
acompaña un cambio en el entorno del contenedor: quien la corre ya esta en el
`docker exec` que cambio el compose. Un endpoint agregaria superficie
autenticada para algo que se hace una vez por rotacion.
"""
import argparse
import os
import sys

from . import db
from .repositorio import RegistroDeSucursales


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--ver",
        action="store_true",
        help="solo informa que credenciales dependen de una clave anterior; no escribe",
    )
    args = p.parse_args(argv)

    url = os.environ.get("LIBRA_PANEL_DATABASE_URL", "")
    if not url:
        print("falta LIBRA_PANEL_DATABASE_URL en el entorno", file=sys.stderr)
        return 2
    db.configure(url)
    registro = RegistroDeSucursales(db.get_session_factory())

    pendientes = registro.pendientes_de_recifrado()
    if args.ver:
        if pendientes:
            print(f"dependen de una clave anterior ({len(pendientes)}): {', '.join(pendientes)}")
            print("la rotacion no termino: recifrar antes de sacar LIBRAAUTH_CLAVES_ANTERIORES")
            return 1
        print("ninguna credencial depende de una clave anterior")
        return 0

    cambiados = registro.recifrar_credenciales()
    if not cambiados:
        print("no habia nada que recifrar")
        return 0
    print(f"recifradas ({len(cambiados)}): {', '.join(cambiados)}")

    # Se vuelve a preguntar en vez de confiar en lo que se acaba de hacer: si
    # quedo alguna pendiente —porque no se pudo leer con ninguna clave— el
    # comando NO puede decir que la rotacion cerro.
    quedan = registro.pendientes_de_recifrado()
    if quedan:
        print(f"AVISO: siguen dependiendo de una clave anterior: {', '.join(quedan)}",
              file=sys.stderr)
        return 1
    print("ya se puede sacar LIBRAAUTH_CLAVES_ANTERIORES del entorno")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
