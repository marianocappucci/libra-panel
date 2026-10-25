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

> **«Sin cobrar» desde libracore v1.172.0 (ADR-059): es lo que falta cobrar.** Antes
> sumaba el total de las facturas sin ningún cobro; ahora suma lo que falta de cada
> una (`total − cobrado − acreditado por notas de crédito`) y **incluye las facturas
> cobradas a medias**, que antes desaparecían del bloque. Lo calcula cada sucursal
> (`/api/resumen` es de su libracore), no el panel: hasta que una sucursal suba el
> pin, sigue mandando el cálculo viejo, y el consolidado mezcla los dos.

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

## El estado de las sucursales: `GET /api/salud`

Análogo del `/api/salud` de [`libra-backoffice`](https://github.com/marianocappucci/libra-backoffice),
con una diferencia de alcance: el backoffice lista las instancias de **todo un
producto**; el panel, sólo **las del usuario** (`usuario_sucursales`, para todos
los roles, igual que el resumen). Con la misma sesión que el resto: sin ella, 401.

Le pregunta el `/health` a cada sucursal activa, **en paralelo y con un tope corto**
(`TIMEOUT_SALUD`, 3 s: el `/health` no hace ninguna cuenta), y contesta:

```json
{
  "total": 3, "respondieron": 2,
  "sucursales": [
    {"slug": "c1", "nombre": "Complejo Uno", "estado": "ok", "latencia_ms": 42,
     "version": null, "detalle": "", "tiene_credencial": true},
    {"slug": "c3", "nombre": "Complejo Tres", "estado": "sin_respuesta", "latencia_ms": 3001,
     "version": null, "detalle": "No contestó el /health en 3 s.", "tiene_credencial": true}
  ]
}
```

- **Un 200 no alcanza.** El cuerpo tiene que ser un objeto JSON (sin exigir ninguna
  clave): una `url_base` mal cargada contesta 200 con el `index.html` de la SPA y
  figura `sin_respuesta`, con el motivo. Mismo criterio que el backoffice.
- **No prueba la credencial**: el `/health` es público (y el panel no le manda la
  credencial). Por eso cada fila trae `tiene_credencial`; la prueba de la
  credencial sigue siendo `POST /api/sucursales/{slug}/probar` (admin).
- `version` sale del cuerpo del `/health` **si la instancia la manda**; hoy ningún
  producto lo hace, así que viene `null`.
- La pantalla principal lo muestra como una fila de estados bajo el encabezado, aparte
  del resumen: no se tumban entre sí. Sin caché (`no-store`), por lo mismo que arriba.

## El bloque `club` de LibraClub: una fila por sucursal, no por instancia

El gate del ROADMAP de LibraClub: **«un dueño con dos instancias y cinco sucursales viendo
cinco filas, no dos»**. Cada instancia de LibraClub agrega a su `/api/resumen` una clave
`club` (`por_sucursal`: una entrada por sede, con ocupación, franjas día × hora, ingresos y
su período anterior, canceladas, ausentes, reservas y origen). El panel la suma entre
instancias en `club.py` (funciones puras, como `consolidado.py`) y la dibuja en la pestaña
**Reservas y ocupación**, que sólo aparece si alguna instancia manda el bloque.

> **Dos significados de «sucursal».** Para el panel, una *sucursal* es una **instancia**
> registrada; para LibraClub, una *sucursal* es una **sede** dentro de una instancia. En la
> respuesta y en la pantalla la primera es `slug` / `instancia` y la segunda `sucursal_id` /
> `sucursal`. Una instancia con tres sedes aporta tres filas.

`club` es una lista de filas y no un árbol de números, así que **no pasa por el consolidado
genérico** (`NO_SON_BLOQUES` lo excluye): como bloque saldría vacío.

```json
"club": {
  "instancias": 2, "slugs": ["norte", "sur"], "invalidos": [],
  "por_sucursal": [{"slug": "norte", "instancia": "Club Norte", "sucursal_id": 1, "sucursal": "Centro",
                    "ocupacion_pct": 60.0, "reservas": 100, "canceladas": 3, "ausentes": 2,
                    "ingresos": {"reservas": 0.0, "senas": 200.0, "buffet": 300.0, "total": 1500.0, "total_periodo_anterior": 1200.0},
                    "variacion_pct": 25.0, "origen": {"mostrador": 40, "portal": 50}, "franjas": [...]}],
  "totales": {"sucursales": 5, "ocupacion_pct": 66.5, "criterio_ocupacion": "ponderada_por_reservas", "reservas": 800, ...},
  "franjas": [{"dia": 0, "hora": 18, "ocupacion_pct": 70.0, "sucursales": 3}]
}
```

Cómo se suma (el criterio está escrito en `club.py` y la pantalla lo repite):

- **Conteos e ingresos**: suma simple. **Variación** = `(total − total_periodo_anterior) / total_periodo_anterior`;
  sin período anterior (o en cero) es `null` y se ve «—», no `+∞` ni `0 %`.
- 🔑 **Ocupación general: promedio ponderado por reservas** de cada sucursal. Un porcentaje no se
  suma, y el promedio simple le daría el mismo peso a una sede de 3 reservas que a una de 300.
  Lo exacto sería ponderar por capacidad (turnos disponibles), que el contrato no manda. Sin
  reservas en ninguna, cae al promedio simple.
- **Mapa de calor** (día × hora): combinado, con el mismo criterio por franja, o de la sucursal
  elegida. Una franja que una sede no manda es «sin dato» (celda vacía), no `0 %`.
- **Origen**: suma por clave, con las claves que vengan (hoy `mostrador`, `portal`, `whatsapp`,
  `telefono`, `serie`); las que el panel no conoce se muestran igual, prolijas.

Las mismas reglas que el resto del panel:

- **Una instancia sin `club` no es un club en cero.** Una instancia vieja (o de otro producto)
  no aporta filas ni baja el promedio; la pantalla dice «de 2 de 3 que contestaron». Si ninguna
  manda el bloque, `club` es `null` y no hay pestaña.
- **Un dato que no vino es `null`, no `0`** (también un valor con forma rara: texto, `NaN`, un
  `bool`).
- **Un `club` ilegible no tumba a las demás**: esa instancia queda en `club.invalidos`, con el
  motivo, y se nombra en pantalla.

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
  club.py               el bloque `club` de LibraClub: una fila por sede, sumada entre instancias
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
| `TIMEOUT_SALUD` | no | Tope en segundos del `/health` de cada sucursal (`GET /api/salud`). Default 3: el `/health` no hace ninguna cuenta. |
| `LIBRA_PANEL_RESET_URL_BASE` | no | Dónde aterriza el link del mail de recupero. |
| `WEB_CONCURRENCY` | no | Procesos de uvicorn (`--workers` del `CMD`). Default 1. Ver «Varios procesos». |
| `LIBRA_ERRORES_DIR` | no | Carpeta del registro de errores (`errores.jsonl`). Sin ella cae en `$DATA_DIR/errores` o en el directorio de trabajo, o sea **dentro del contenedor**: en producción se fija a una carpeta de un volumen (el compose de ejemplo la monta en `/var/lib/libra-panel/errores`). |
| `LIBRA_ENTORNO` | no | `cliente`, `demo` o `dev`: de eso depende cómo avisa el vigía. Sin ella, `desconocido` (se trata como `cliente`). |
| `LIBRA_INSTANCIA` | no | Nombre del contenedor (`<slug>-panel`). Sale en cada línea del registro. |
| `LIBRA_VERSION` | no | El `release` de cada línea. La imagen la trae del tag con que se construyó (`APP_VERSION`). |

Y en **cada sucursal**, del otro lado: `LIBRA_PANEL_TOKEN`, distinta por
instancia. Sin ella el guard de `libraauth` ni mira el header (opt-in por
ausencia) y contesta 401.

## Registro de errores

Desde `libracore` v1.159.0 (ADR-045) un `500` ya no se pierde en el stdout del contenedor: `instalar_registro_de_errores(app, "libra-panel")`
(en `app.py`, al lado de `SecurityHeadersMiddleware`) responde `{"detail": "Error interno", "ref": "a1b2c3d4"}` y deja **una línea JSON** en
`$LIBRA_ERRORES_DIR/errores.jsonl` (rotación 5 MB × 3, sin cuerpos, cookies ni datos personales). El `ref` es el código que la pantalla «Algo
falló» (`<ErrorBoundary>` de `libra-ui`, en `main.tsx`) le muestra al usuario. Los errores del navegador llegan a `POST /api/errores-cliente`
(`instalarReporteDeErrores`). Lee los archivos el vigía del host (`operaciones/vigilar_errores.py` del wiki) y avisa por Telegram.

🔴 **El archivo tiene que estar en un volumen**: sin él, cada `docker compose up` que recrea el contenedor lo borra. El compose de ejemplo monta el
volumen `estado` en `/var/lib/libra-panel` y fija `LIBRA_ERRORES_DIR=/var/lib/libra-panel/errores`; en el host queda en
`/var/lib/docker/volumes/<proyecto>_estado/_data/errores/errores.jsonl`, que es lo que busca el glob por defecto del vigía.

## Varios procesos

El contenedor corre **un solo uvicorn** (`WEB_CONCURRENCY` vale 1 si no se la toca) y así se queda: subirlo es una decisión aparte. Lo que ya está
listo para cuando se decida (libraauth v0.50.0, ADR-023):

- **El captcha del login anota los desafíos usados en la base** (`UsadosEnBase`, tabla `libraauth_captcha_usados`, que crea el `create_all` del
  arranque como las demás). Con la lista en memoria, un desafío resuelto serviría una vez **por worker**. Cuesta una ida a la base por cada login.
- **El bloqueo por intentos del login ya era compartido** (cuenta sobre `auth_log`, en la base).
- El panel no guarda estado en archivos ni en memoria entre pedidos (el consolidado no se cachea), así que no hay nada más que mover.

Cada proceso abre su propio pool de conexiones: antes de subir `WEB_CONCURRENCY`, mirar `max_connections` del PostgreSQL del sidecar.

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

## Rotar el `SECRET_KEY` sin perder las credenciales

De `SECRET_KEY` se **deriva** la clave con la que se cifra la credencial de
panel de cada sucursal. Rotarlo a secas las deja ilegibles — y el panel no se
cae, muestra las sucursales **sin respuesta**, que es la forma silenciosa de
romperse. Pasó el 2026-09-07 y se detectó dos días después.

El ciclo tiene cuatro pasos y el tercero es el que no se puede saltear:

1. Rotar `SECRET_KEY` en el `.env`/compose de la instancia.
2. Poner el valor **anterior** en `LIBRAAUTH_CLAVES_ANTERIORES` (acepta varios,
   separados por coma) y recrear el contenedor.
3. `docker exec <contenedor> python -m libra_panel.recifrar`
4. **Sacar `LIBRAAUTH_CLAVES_ANTERIORES`** y recrear de nuevo.

Para ver en qué estado está sin escribir nada:

```
docker exec <contenedor> python -m libra_panel.recifrar --ver
```

Sale distinto de cero mientras quede alguna credencial dependiendo de una clave
anterior. Mientras eso pase, el paso 4 perdería esas credenciales.

> Una credencial que **no se puede leer con ninguna** clave conocida no se toca
> ni aparece como pendiente: hay que volver a cargarla a mano. Son dos
> situaciones distintas y el comando las distingue a propósito.

## Dónde se arregla (regla de la familia, 2026-10-03)

**El arreglo de fondo vive siempre en el motor** (`libracore`; `libracommerce` y `libra-ui` para
lo suyo), **nunca en este repo.** Lo que otro producto comparte o podría compartir —el protocolo
con ARCA, las reglas fiscales y sus validaciones, las guardas contra duplicados, la numeración, la
cuenta corriente, los componentes de pantalla compartidos— se escribe y se arregla en el motor.
Este repo sólo aporta **costuras** (los hooks que el motor ya expone) y lo suyo: pantallas,
textos y su modelo de datos propio. Si falta la costura, se agrega al motor; si el arreglo hace
falta antes, igual se hace en el motor (PR y tag) y acá se sube el pin: nada «provisorio» en este
repo. Un hueco que se encuentra acá se busca en los demás productos antes de darlo por acotado.
Detalle y motivo: `reglas/producto.md` del wiki.
