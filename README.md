# libra-panel

**El panel del dueño multisucursal.** Un cliente con N locales entra, elige un
período y ve los números de todos juntos — aunque cada local sea una instancia
separada, con su propia base, y algunos facturen con distinto CUIT.

No es el backoffice de superadmin. [`libra-backoffice`](https://github.com/marianocappucci/libra-backoffice)
comparte el patrón y no el público:

| | libra-backoffice | libra-panel |
|---|---|---|
| Quién entra | superadmin (nosotros) | el cliente |
| Qué hace | alta/baja de instancias, planes, SMTP, salud | mira sus números |
| Alcance | **todas** las instancias de un producto | **las suyas** |
| Escribe en las instancias | sí | **nunca** |

Mezclarlos significaría que el cliente entra a la herramienta que administra
instancias de **otros** clientes. No es una cuestión de permisos: es el objeto
equivocado.

Diseño completo y las decisiones detrás: `wiki/analyses/panel-del-dueno-multisucursal.md`.

## Cómo llega a los datos

**Preguntándole a cada sucursal por HTTP.** No abre ninguna base y no copia
ningún número.

```
┌─────────────────┐
│ libra-panel     │  ← login propio del dueño (SessionAuth)
└────────┬────────┘
         │  GET /api/resumen?desde=&hasta=   +   X-Panel-Auth (una credencial POR SUCURSAL)
         ├──────────► complejo-1  (CUIT A, PV 1)
         ├──────────► complejo-2  (CUIT A, PV 2)
         ├──────────► complejo-3  (CUIT A, PV 3)   ← si ésta no contesta, el panel lo DICE
         ├──────────► complejo-4  (CUIT B, PV 1)
         └──────────► complejo-5  (CUIT C, PV 1)
```

El endpoint del otro lado no es de este repo: lo arma la factory
`libracore.resumen_router.build_resumen_router` (v1.41.0) y lo monta cada
producto, con el guard `json_api_require_panel_o_admin` de `libraauth` (v0.29.0).
El núcleo —facturado, cobrado, egresos, saldo de caja, comprobantes y sin
cobrar— sale de LibraCore, que está en los seis productos. Los bloques extra
salen por motor: `comercio` de LibraCommerce (4 productos), `agenda` de
LibraGenda (3).

**El panel tiene base de datos, pero no de negocio.** Guarda sus usuarios, el
registro de sucursales y quién ve cuál. Ningún número de ventas se copia nunca:
se pregunta y se descarta. Si se guardaran habría dos verdades sobre la misma
plata, y una de las dos quedaría vieja.

## Las cuatro cosas que hacen que el panel no mienta

Son el producto. Todo lo demás es plomería.

### 1. Una sucursal que no contesta NO es una sucursal que vendió cero

Si el complejo 3 está apagado, sumar cuatro y mostrar el total produce **un
número más chico que la realidad, con cara de número correcto**. El dueño lo lee
como "hoy vendimos menos".

El panel muestra **"4 de 5 sucursales" siempre** —no sólo cuando falla alguna—,
marca el total como parcial, nombra las que faltan y dice el motivo de cada una.
Y cuando no contestó ninguna **no dibuja un total en cero**: no hay de dónde
sacarlo.

### 2. Un bloque que no aplica NO es un bloque en cero

Una sucursal de MedLibra no tiene ventas de buffet. Mostrar `0` ahí dice "no
vendieron nada" cuando lo cierto es "esto no se mide acá" — y consolidando, un
cero se suma y un ausente no.

Cada bloque lleva **su propio denominador**: "Ventas y stock — de 2 de 4 que
contestaron". Un bloque que nadie reportó no aparece.

### 3. Sumar entre CUITs da un número de gestión, no uno fiscal

"Facturado del mes" sumando tres razones sociales no es una cifra declarable:
cada CUIT tiene su libro de IVA. La pantalla lo dice, y el consolidado **por
razón social** está a un clic.

🔴 **Y el CUIT vacío no agrupa.** Una instancia sin empresa configurada informa
CUIT `''`; con eso como clave, dos sucursales sin configurar quedarían juntas
como si fueran la misma empresa. Van sueltas, nombradas y marcadas.

### 4. Nada de caché

El pedido fue en vivo. Cachear en vivo es contradecirse, y un total parcial
cacheado se queda pegado después de que la sucursal volvió. La respuesta va con
`Cache-Control: no-store` y cada pedido vuelve a preguntar.

## La credencial es por sucursal, no por producto

🔴 **`LIBRA_SERVICE_TOKEN` es por PRODUCTO.** Medido en el VPS el 2026-08-20:
`contalibra` y `contalibra-demo` comparten uno, y `libradesk-lagrace` y
`libradesk-compulibra` —**dos clientes distintos**— también.

Darle ese token a un cliente le abriría **todas** las instancias de ese
producto, incluidas las de otros clientes. Por eso cada sucursal lleva su propia
`LIBRA_PANEL_TOKEN`, con su propio header (`X-Panel-Auth`), guardada **cifrada**
en el registro del panel (`libraauth.crypto`, clave derivada del `SECRET_KEY`
del panel). Una credencial filtrada expone la lectura de agregados de **una**
sucursal.

La credencial entra por la pantalla de alta y **no vuelve a salir nunca**: la
API devuelve `tiene_credencial: true/false` y nada más.

## El login es del cliente

`SessionAuth` de `libraauth`, no `AdminAuth`. La diferencia no es de estilo:

| | `AdminAuth` (backoffice) | `SessionAuth` (acá) |
|---|---|---|
| Dónde viven las credenciales | variables de entorno | tabla `usuarios` |
| Cambiar la contraseña | **redeploy** | desde la pantalla |
| Recupero por mail | ❌ | ✅ |
| Auditoría de accesos | ❌ | ✅ `auth_log` |
| Más de un usuario | ❌ | ✅ |

Que el cliente necesite que nosotros redespleguemos su contenedor para cambiar
su propia contraseña es una dependencia absurda, y un panel que muestra la plata
de un negocio quiere registro de accesos.

## Multi-cliente desde el modelo

No hay una entidad "grupo" ni un despliegue por dueño: la tabla
`usuario_sucursales` **es** el aislamiento.

🔴 **Toda consulta de números se filtra por esa tabla, para todos los roles sin
excepción.** No hay una rama para admin que consulte todo: sumar las sucursales
de clientes distintos daría un número que no significa nada, y además le
mostraría a uno los del otro. Un admin sin asignaciones ve un panel vacío, y
está bien.

| Rol | Qué puede |
|---|---|
| `admin` (nosotros) | ABM del registro, credenciales, usuarios, asignaciones |
| `socio` (el cliente) | ver los números de las sucursales que tiene asignadas |

## Estructura

```
backend/libra_panel/    FastAPI, API JSON
  consolidado.py        la suma. Funciones puras: es donde vive lo que puede mentir
  cliente_sucursal.py   el HTTP contra una sucursal, con timeout y validación de forma
  repositorio.py        el registro y las credenciales cifradas
frontend/               Vite + React + shadcn/ui + libra-ui
Dockerfile              build del frontend -> estáticos servidos por el backend
```

## Configuración

| Variable | Obligatoria | Qué es |
|---|---|---|
| `LIBRA_PANEL_DATABASE_URL` | sí | PostgreSQL propio del panel. Otro motor **no arranca**. |
| `SECRET_KEY` | sí | Firma la cookie **y** deriva la clave que cifra las credenciales. |
| `LIBRA_PANEL_ADMIN_PASSWORD` | sí | Admin inicial. Fail-closed: sin esto no levanta. |
| `LIBRA_PANEL_ADMIN_USERNAME` | no | Default `admin`. |
| `PANEL_NAME` | no | Nombre para mostrar. El panel es transversal: el branding sale de acá. |
| `TIMEOUT_SUCURSAL` | no | Segundos por sucursal. Default 6. Corto a propósito. |
| `LIBRA_PANEL_RESET_URL_BASE` | no | Dónde aterriza el link del mail de recupero. |

Y en **cada sucursal**, del otro lado: `LIBRA_PANEL_TOKEN`, distinta por
instancia. Sin ella el guard de `libraauth` ni mira el header (opt-in por
ausencia) y contesta 401.

## Desarrollo

La suite corre contra **PostgreSQL de verdad**. No cae a SQLite: falla.

```bash
docker run -d --name libra-panel-test-pg -e POSTGRES_PASSWORD=panel -e POSTGRES_USER=panel -e POSTGRES_DB=panel -p 55432:5432 postgres:16
```

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
LIBRA_PANEL_TEST_DATABASE_URL=postgresql://panel:panel@127.0.0.1:55432/panel .venv/bin/python -m pytest -q --cov
```

```bash
cd frontend && npm install && npm run build && npm test
```
