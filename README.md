# 🦷 LABDENT SMART
Sistema inteligente para la gestión de órdenes de trabajo e inventario en un laboratorio dental.

## Cómo ejecutarlo
1. Instala Python 3.10+ y abre una terminal en esta carpeta.
2. `pip install -r requirements.txt`
3. `python app.py`  (la primera vez crea una base de datos **vacía**: tú ingresas tus datos)
4. Abre http://127.0.0.1:5000 — la primera vez te lleva a **/primer-acceso** para crear tu cuenta de **Administrador**.

Opcional, solo para una demo: `python seed.py` borra todo y carga datos de ejemplo. Imprime en pantalla
las cuentas de demostración con contraseñas **aleatorias** (solo se muestran en ese momento: anótalas).
Por defecto tus datos viven en `labdent_datos.db` (SQLite); usa el botón **Respaldo** del menú para descargar una copia.
Para que **todo el equipo comparta los mismos datos**, conecta la app a PostgreSQL / Supabase (ver abajo).

## Estructura por secciones
| Sección | Archivo | Qué hace |
|---|---|---|
| 0 | `config.py` | Estados de la orden y parámetros del modelo |
| 1 | `schema.sql`, `schema_postgres.sql`, `database.py` | Tablas y conexión (SQLite o PostgreSQL/Supabase) |
| 2 | `services/inventario.py` | Entradas, salidas y alertas de stock bajo |
| 3 | `services/ordenes.py` | Crear órdenes, cambiar estado, descuento automático de materiales |
| 3B | `services/solicitudes.py` | Solicitudes de trabajo del odontólogo: crear, aceptar (crea la orden), rechazar, cancelar |
| 4 | `services/analitica.py` | Indicadores, recomendaciones por reglas, predicción, simulación y optimización |
| 5 | `routes/panel.py` | Panel principal y simulación |
| 6 | `routes/ordenes.py` | Pantallas de órdenes |
| 7 | `routes/inventario.py` | Pantallas de inventario |
| 8 | `routes/catalogos.py` | Usuarios, odontólogos, pacientes, servicios y "recetas" |
| 8B | `services/pacientes.py`, `templates/_paciente_campos.html` | Datos del paciente (nombre, documento, teléfono) y sus validaciones, iguales en todo el sistema |
| 9 | `app.py` | Arranque de la aplicación y control de acceso |
| 12 | `services/simulacion_colas.py` | **Simulación de colas (SimPy)** del flujo de producción y teoría M/M/c |
| 11 | `services/acceso.py`, `routes/auth.py`, `routes/portal.py` | Login del personal y del cliente, roles y límite de intentos |
| 10 | `seed.py` | Datos de ejemplo |
| 4B | `services/seguimiento.py` | **Diferenciador:** código/QR por orden, riesgo de atraso y Pulso del laboratorio |
| 6B | `routes/seguimiento.py` | Consulta pública por código/QR y etiqueta imprimible |
| 6C | `routes/solicitudes.py` | Bandeja de solicitudes en el panel del laboratorio |
| 11B | `routes/portal.py` | Portal del odontólogo: órdenes, solicitudes, pacientes, historial y perfil |
| — | `templates/`, `static/` | Pantallas (Bootstrap + tema propio) y estilos |

## Flujo principal
1. Se crea una **orden** (estado *Recibida*).
2. Al pasar a **En producción**, el sistema descuenta del inventario los materiales del servicio (si no alcanza el stock, avisa y no avanza).
3. Luego pasa a *Terminada* y *Entregada*.
4. El **panel** muestra indicadores, alertas y recomendaciones; **Simulación** compara dos configuraciones del laboratorio (flujo de producción) y también proyecta la compra de materiales.

## Login: personal y clientes
Hay dos entradas separadas:

| Quién | Dónde entra | Qué ve |
|---|---|---|
| Personal del laboratorio | `/login` | El panel completo, según su rol |
| Odontólogo (cliente) | `/portal/login` | Su portal: **sus** órdenes, pacientes, solicitudes e historial |

**Roles del personal:** `Administrador`, `Técnico` y `Recepción`. Solo el Administrador entra a **Ajustes**, **Respaldo** y **Mi equipo** (los demás reciben 403).
Las cuentas se crean en *Clientes y servicios*: en **Mi equipo** (personal) y en **Odontólogos** (acceso al portal, opcional). Si dejas el usuario vacío, esa persona queda sin acceso. Siempre debe quedar al menos un administrador con acceso.

### Datos del paciente
Cada paciente guarda **nombre**, **tipo y número de documento** (CC, TI, RC, CE, PA, PPT) y **teléfono**. Se piden con el mismo formulario en *Clientes y servicios → Pacientes*, en *Nueva orden* (paciente nuevo), y en el portal (*Mis pacientes* y *Solicitar trabajo*).
- El nombre es obligatorio; documento y teléfono son opcionales.
- El documento se guarda sin puntos ni espacios (`1.065.234.567` → `1065234567`). CC, TI y RC solo admiten números.
- Un mismo odontólogo no puede tener dos pacientes con el mismo documento.
- El teléfono debe tener entre 7 y 15 dígitos.
- La consulta pública por QR **no** muestra documento ni teléfono (solo las iniciales).
- En bases existentes las columnas se agregan solas al arrancar; los pacientes antiguos quedan sin documento hasta que los edites.

### Portal del odontólogo (cliente)
Más completo que una simple consulta, pero sin acceso a lo interno del laboratorio:

| Sección | Qué puede hacer el odontólogo |
|---|---|
| **Mis órdenes** (`/portal/`) | Resumen (en proceso, con retraso, pendientes, entregadas) y sus trabajos activos |
| **Detalle** (`/portal/orden/<id>`) | Etapas, línea de tiempo con fechas y entrega estimada. Una orden ajena da 404 |
| **Solicitar trabajo** (`/portal/solicitar`) | Elige paciente (o crea uno), servicio e indicaciones. Queda *Pendiente* |
| **Mis pacientes** (`/portal/pacientes`) | Registra, renombra y elimina **sus** pacientes (no los que ya tienen órdenes) |
| **Historial** (`/portal/historial`) | Trabajos entregados (a tiempo o no) y sus solicitudes con su estado y motivo de rechazo |
| **Mi perfil** (`/portal/perfil`) | Edita nombre, clínica y teléfono; cambia su contraseña |

Las solicitudes llegan al panel en **Solicitudes** (con contador en el menú y aviso en el panel). El personal la **acepta** (se crea la orden con su QR y fecha de entrega) o la **rechaza** con un motivo que el odontólogo ve. Si al servicio le falta material, la bandeja lo avisa antes de aceptar. El odontólogo **no** ve inventario, costos, simulación ni datos de otros clientes, y no puede avanzar estados.

La tabla `solicitudes` se crea sola al arrancar si tu base es anterior a este cambio (SQLite y Supabase): no hay que borrar nada.

La consulta pública por código/QR (`/seguimiento/<código>`) sigue abierta a propósito: la clínica escanea el QR y ve el avance sin iniciar sesión.

**Seguridad incluida:** contraseñas con hash (werkzeug), clave secreta aleatoria, cookie de sesión HttpOnly + SameSite=Lax, límite de 5 intentos fallidos por IP cada 10 min, cierre de sesión por POST, redirecciones `next` solo internas y rol/usuario releídos de la base en cada petición.
Limitación conocida: no hay token CSRF; la protección es SameSite=Lax.

**Variables de entorno (opcionales):**
- `LABDENT_SECRET_KEY`: clave que firma sesiones y QR. Si no existe se crea `clave_secreta.key` (no la subas a GitHub).
- `LABDENT_HTTPS=1`: márcalo cuando publiques con https (cookie `Secure`).

> ⚠️ Si cambias o pierdes la clave secreta, los códigos/QR ya impresos dejan de funcionar (se derivan de esa clave).

## Simulación del flujo de producción (modelamiento y simulación)
Menú **Simulación → Flujo de producción** (`/simulacion`). Es una simulación de eventos discretos hecha con **SimPy**:

- Las órdenes llegan con un proceso de **Poisson** (por defecto 20 por día de 8 h) y pasan en serie por **Diseño CAD → Fresado → Horno → Acabado/QC**.
- Cada estación es un recurso con `c` servidores y una fila FIFO; el tiempo de servicio es **exponencial** (cola **M/M/c**). Por defecto: 20 / 22 / 18 / 15 min, con 1 servidor cada una.
- Se comparan dos escenarios (**A actual** vs **B propuesto**) con las **mismas semillas** (números aleatorios comunes), varias repeticiones, descarte de los 3 primeros días (calentamiento) e **intervalo de confianza del 95 %**.
- **Validación:** junto a cada resultado simulado se muestra el teórico (fórmula de **Erlang C**). Por el teorema de Burke cada estación de la serie es una M/M/c, así que ambos deben coincidir.
- **¿Dónde invertir?** agrega un servidor a cada estación y mide la mejora; con los valores por defecto el cuello de botella es el **Fresado** (ρ ≈ 0,92) y una segunda fresadora baja el tiempo total de ~8,7 h a ~4,8 h (≈ 45 %).
- Los parámetros se validan y limitan (p. ej. máx. 60 días y 30 repeticiones) para que una corrida nunca sea demasiado pesada. Es reproducible: misma semilla, mismo resultado.

La pestaña **Compra de materiales** (`/simulacion/materiales`) conserva la proyección de inventario anterior. El modelo independiente en script está en la carpeta `lab-dental-simulacion` del proyecto.

## Base de datos compartida: PostgreSQL / Supabase
La app funciona con dos motores usando el mismo código:

| Motor | Cuándo se usa | Datos |
|---|---|---|
| **SQLite** | si NO defines `DATABASE_URL` | archivo `labdent_datos.db` en tu computador (solo tuyo) |
| **PostgreSQL / Supabase** | si defines `DATABASE_URL` | una base en la nube que **todo el equipo comparte** |

**Supabase es PostgreSQL alojado**, así que sirve cualquier PostgreSQL (el de Supabase, uno local, Render, Neon…).

### Pasos con Supabase
1. Crea una cuenta y un proyecto en <https://supabase.com> (guarda la **contraseña de la base de datos** que eliges al crearlo).
2. En el proyecto pulsa **Connect** (o *Project Settings → Database → Connection string*) y copia la URI del **Session pooler** (puerto 5432; funciona con IPv4, que es lo habitual en casa y en la universidad). El *Transaction pooler* (puerto 6543) también sirve.
3. En la carpeta del proyecto copia `.env.example` como `.env` y pega la URI en `DATABASE_URL=`, cambiando `[YOUR-PASSWORD]` por tu contraseña. Si la contraseña tiene símbolos (`@ : / # ?`), escríbelos con su código (`@` = `%40`, `#` = `%23`).
4. Pon también una `LABDENT_SECRET_KEY` y que **todo el equipo use la misma** (si no, los QR generados en un computador no sirven en otro): `python -c "import secrets; print(secrets.token_hex(32))"`.
5. `pip install -r requirements.txt` y `python app.py`. Al arrancar crea las tablas que falten (sin borrar nada) y muestra `Base de datos: PostgreSQL / Supabase`. Entra a `/primer-acceso` para crear el administrador. Los demás solo copian el `.env` (por un canal privado, **nunca por GitHub**).
6. **Comprueba la conexión** antes de arrancar: `python verificar_conexion.py`. Te dice si encuentra el `.env`, si leyó la `DATABASE_URL`, si logra conectarse y, si no, por qué. Nunca muestra tu contraseña.
7. Para ver los datos: en Supabase, *Table Editor*. Las tablas guardan referencias (`odontologo_id = 1`); para leer los nombres usa las **vistas** (ver abajo).

**¿Ya tenías datos en SQLite?** Con `DATABASE_URL` configurada: `python migrar_sqlite_a_postgres.py` los copia a PostgreSQL (si allá ya hay datos, no toca nada salvo que añadas `--reemplazar`).

**Notas**
- `python seed.py` con `DATABASE_URL` configurada **borra y recrea las tablas en PostgreSQL**: no lo uses sobre datos reales.
- El botón **Respaldo** descarga un `.db` con SQLite y un `.json` con todas las tablas con PostgreSQL. En Supabase además hay respaldos propios del proyecto.
- Las tablas se crean con *Row Level Security* activado y sin políticas: la API REST pública de Supabase no puede leer tus datos; la app entra directo por PostgreSQL con el rol `postgres`.
- Los precios se guardan como `DOUBLE PRECISION` en pesos (COP); las fechas como texto `AAAA-MM-DD`, igual que en SQLite.
- Tablas: `schema.sql` (SQLite) y `schema_postgres.sql` (PostgreSQL) tienen el mismo modelo.

### Vistas: la base legible
Las tablas están **normalizadas**: una orden guarda `odontologo_id`, `paciente_id` y `servicio_id`, no los nombres. Así, si corriges el nombre de un paciente, se actualiza en todas sus órdenes y nunca hay datos repetidos o contradictorios. Para leerlas sin ir tabla por tabla, la app crea al arrancar estas **vistas** (solo lectura, con los nombres ya unidos; en Supabase aparecen junto a las tablas en *Table Editor*, o en *Database → Views*):

| Vista | Muestra |
|---|---|
| `v_ordenes` | orden, estado, odontólogo, clínica, paciente, servicio, precio y fechas |
| `v_pacientes` | paciente, su odontólogo/clínica, documento y teléfono |
| `v_movimientos_inventario` | fecha, entrada/salida, material, cantidad, unidad y orden |
| `v_recetas` | qué materiales y cuánto consume cada servicio |
| `v_historial_estados` | cambios de estado de cada orden, con paciente y servicio |
| `v_solicitudes` | solicitudes del portal con odontólogo, paciente, servicio, estado y motivo |

No guardan datos propios ni incluyen contraseñas. Con PostgreSQL 15+ se crean con `security_invoker`, para que la seguridad de las tablas (RLS) también las proteja. Además, en cualquier tabla del *Table Editor* las columnas con llave foránea tienen una flecha que abre la fila relacionada.

## Valores en pesos
Todos los montos se guardan como número en pesos colombianos (COP) y se muestran con el formato `$380.000` mediante el filtro `|pesos` (definido en `app.py`).

## Pruebas
`python -m unittest discover -s tests -v` (91 pruebas, incluidas simulación, pesos, base de datos y vistas: primer acceso, login, roles, portal del cliente con solicitudes, pacientes, historial y perfil, datos y validación del paciente, consulta pública y migración de bases antiguas). Para probar contra PostgreSQL: `TEST_DATABASE_URL=postgresql://usuario@host/base python -m unittest discover -s tests` (¡esa base se borra en cada prueba: usa una de pruebas!).

## Ideas para ampliar
Gráficos (Chart.js), exportar a Excel, notificaciones por WhatsApp/correo, modelos predictivos más avanzados.

## Lo que hace diferente a LABDENT SMART
- **Portal del odontólogo con QR:** cada orden genera un código (`LD-0001-AB12C`) y un QR para pegar en la caja. La clínica escanea y ve el avance en vivo (solo iniciales del paciente, sin precios) y puede escribir por WhatsApp.
- **Pulso del laboratorio (0-100):** índice que resume atrasos, materiales en alerta y cumplimiento.
- **Riesgo por orden:** detecta antes de que venza si una orden se atrasará (incluye falta de material).

Para que el QR funcione desde el celular del odontólogo, publica la app en internet y escribe tu dirección en **Ajustes**. Tu número de WhatsApp se configura dentro de la app, en **Ajustes**.
