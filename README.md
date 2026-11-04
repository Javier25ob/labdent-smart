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
| 4 | `services/analitica.py` | Indicadores, recomendaciones por reglas, predicción, simulación y optimización |
| 5 | `routes/panel.py` | Panel principal y simulación |
| 6 | `routes/ordenes.py` | Pantallas de órdenes |
| 7 | `routes/inventario.py` | Pantallas de inventario |
| 8 | `routes/catalogos.py` | Usuarios, odontólogos, pacientes, servicios y "recetas" |
| 9 | `app.py` | Arranque de la aplicación y control de acceso |
| 12 | `services/simulacion_colas.py` | **Simulación de colas (SimPy)** del flujo de producción y teoría M/M/c |
| 11 | `services/acceso.py`, `routes/auth.py`, `routes/portal.py` | Login del personal y del cliente, roles y límite de intentos |
| 10 | `seed.py` | Datos de ejemplo |
| 4B | `services/seguimiento.py` | **Diferenciador:** código/QR por orden, riesgo de atraso y Pulso del laboratorio |
| 6B | `routes/seguimiento.py` | Portal público del odontólogo y etiqueta imprimible |
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
| Odontólogo (cliente) | `/portal/login` | Solo **sus** órdenes (`/portal/`) |

**Roles del personal:** `Administrador`, `Técnico` y `Recepción`. Solo el Administrador entra a **Ajustes**, **Respaldo** y **Mi equipo** (los demás reciben 403).
Las cuentas se crean en *Clientes y servicios*: en **Mi equipo** (personal) y en **Odontólogos** (acceso al portal, opcional). Si dejas el usuario vacío, esa persona queda sin acceso. Siempre debe quedar al menos un administrador con acceso.

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
6. Para ver los datos: en Supabase, *Table Editor*.

**¿Ya tenías datos en SQLite?** Con `DATABASE_URL` configurada: `python migrar_sqlite_a_postgres.py` los copia a PostgreSQL (si allá ya hay datos, no toca nada salvo que añadas `--reemplazar`).

**Notas**
- `python seed.py` con `DATABASE_URL` configurada **borra y recrea las tablas en PostgreSQL**: no lo uses sobre datos reales.
- El botón **Respaldo** descarga un `.db` con SQLite y un `.json` con todas las tablas con PostgreSQL. En Supabase además hay respaldos propios del proyecto.
- Las tablas se crean con *Row Level Security* activado y sin políticas: la API REST pública de Supabase no puede leer tus datos; la app entra directo por PostgreSQL con el rol `postgres`.
- Los precios se guardan como `DOUBLE PRECISION` en pesos (COP); las fechas como texto `AAAA-MM-DD`, igual que en SQLite.
- Tablas: `schema.sql` (SQLite) y `schema_postgres.sql` (PostgreSQL) tienen el mismo modelo.

## Valores en pesos
Todos los montos se guardan como número en pesos colombianos (COP) y se muestran con el formato `$380.000` mediante el filtro `|pesos` (definido en `app.py`).

## Pruebas
`python -m unittest discover -s tests -v` (54 pruebas, incluidas simulación, pesos y base de datos: primer acceso, login, roles, portal del cliente, consulta pública y migración de bases antiguas). Para probar contra PostgreSQL: `TEST_DATABASE_URL=postgresql://usuario@host/base python -m unittest discover -s tests` (¡esa base se borra en cada prueba: usa una de pruebas!).

## Ideas para ampliar
Gráficos (Chart.js), exportar a Excel, notificaciones por WhatsApp/correo, modelos predictivos más avanzados.

## Lo que hace diferente a LABDENT SMART
- **Portal del odontólogo con QR:** cada orden genera un código (`LD-0001-AB12C`) y un QR para pegar en la caja. La clínica escanea y ve el avance en vivo (solo iniciales del paciente, sin precios) y puede escribir por WhatsApp.
- **Pulso del laboratorio (0-100):** índice que resume atrasos, materiales en alerta y cumplimiento.
- **Riesgo por orden:** detecta antes de que venza si una orden se atrasará (incluye falta de material).

Para que el QR funcione desde el celular del odontólogo, publica la app en internet y escribe tu dirección en **Ajustes**. Tu número de WhatsApp se configura dentro de la app, en **Ajustes**.
