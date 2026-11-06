"""SECCIÓN 1 - Conexión a la base de datos.

La aplicación habla con DOS motores con el mismo código:

  * SQLite (archivo `labdent_datos.db`)  -> si NO defines DATABASE_URL. Cero configuración.
  * PostgreSQL / Supabase                -> si defines DATABASE_URL (en el entorno o en `.env`).

El resto de la app solo usa `get_db()` y escribe SQL con `?` como marcador; aquí se traduce
al formato de cada motor. Con PostgreSQL varias personas comparten los mismos datos.
"""
import atexit
import json
import sqlite3
import threading
from pathlib import Path

from flask import g

import config

try:                                    # solo hace falta si usas PostgreSQL / Supabase
    import psycopg
    from psycopg_pool import ConnectionPool
except ImportError:                     # pragma: no cover
    psycopg = ConnectionPool = None

DB_PATH = Path(__file__).parent / "labdent_datos.db"          # SQLite
SCHEMA_PATH = Path(__file__).parent / "schema.sql"            # SQLite
SCHEMA_PG_PATH = Path(__file__).parent / "schema_postgres.sql"
DATABASE_URL = config.DATABASE_URL                            # "" = SQLite (las pruebas lo cambian)

# Tablas en orden de dependencia (primero las "padre"). Se usa para vaciar, copiar y respaldar.
TABLAS = ("usuarios", "odontologos", "pacientes", "servicios", "materiales", "servicio_materiales",
          "ordenes", "historial_estados", "movimientos_inventario", "configuracion")

# Vistas de LECTURA: muestran los nombres en lugar de los números (ids) para que, al abrir la base
# (por ejemplo en el Table Editor de Supabase), se vea ordenada y legible. No guardan datos propios:
# la información sigue en las tablas normalizadas (cambiar el nombre de un paciente se refleja en
# todas sus órdenes). Se recrean solas al arrancar. Nunca incluyen contraseñas.
VISTAS = {
    "v_ordenes": """
        SELECT o.id AS orden, o.estado, od.nombre AS odontologo, od.clinica, p.nombre AS paciente,
               s.nombre AS servicio, s.precio, o.fecha_ingreso, o.fecha_entrega_estimada,
               o.fecha_entrega_real, o.observaciones
        FROM ordenes o
        JOIN odontologos od ON od.id = o.odontologo_id
        JOIN pacientes p ON p.id = o.paciente_id
        JOIN servicios s ON s.id = o.servicio_id
        ORDER BY o.id""",
    "v_pacientes": """
        SELECT p.id, p.nombre AS paciente, od.nombre AS odontologo, od.clinica
        FROM pacientes p
        LEFT JOIN odontologos od ON od.id = p.odontologo_id
        ORDER BY p.id""",
    "v_movimientos_inventario": """
        SELECT mv.id, mv.fecha, mv.tipo, m.nombre AS material, mv.cantidad, m.unidad,
               mv.orden_id AS orden, mv.nota
        FROM movimientos_inventario mv
        JOIN materiales m ON m.id = mv.material_id
        ORDER BY mv.id""",
    "v_recetas": """
        SELECT s.nombre AS servicio, m.nombre AS material, sm.cantidad, m.unidad
        FROM servicio_materiales sm
        JOIN servicios s ON s.id = sm.servicio_id
        JOIN materiales m ON m.id = sm.material_id
        ORDER BY s.nombre, m.nombre""",
    "v_historial_estados": """
        SELECT h.id, h.orden_id AS orden, p.nombre AS paciente, s.nombre AS servicio, h.estado, h.fecha
        FROM historial_estados h
        JOIN ordenes o ON o.id = h.orden_id
        JOIN pacientes p ON p.id = o.paciente_id
        JOIN servicios s ON s.id = o.servicio_id
        ORDER BY h.id""",
}

# Error que lanza cualquiera de los dos motores al violar una llave foránea o un UNIQUE
ErrorIntegridad = (sqlite3.IntegrityError,) + ((psycopg.errors.IntegrityError,) if psycopg else ())


def usa_postgres():
    return bool(DATABASE_URL)


# ---------------------------------------------------------------------------
# Filas: se pueden leer por nombre (fila["stock"]), por posición (fila[0]) y con dict(fila),
# igual que sqlite3.Row, para que el código no cambie según el motor.
# ---------------------------------------------------------------------------
class Fila:
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols, vals):
        self._cols, self._vals = tuple(cols), tuple(vals)

    def __getitem__(self, clave):
        if isinstance(clave, (int, slice)):
            return self._vals[clave]
        try:
            return self._vals[self._cols.index(clave)]
        except ValueError:
            raise KeyError(clave) from None

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __repr__(self):
        return f"Fila({dict(zip(self._cols, self._vals))})"


def _fila_factory(cursor):
    """Le dice a psycopg cómo armar cada fila (ver psycopg: row_factory)."""
    columnas = [c.name for c in cursor.description] if cursor.description else []
    return lambda valores: Fila(columnas, valores)


def _a_postgres(sql):
    """SQLite usa `?` como marcador; PostgreSQL (psycopg) usa `%s` y trata `%` como especial."""
    return sql.replace("%", "%%").replace("?", "%s")


# ---------------------------------------------------------------------------
# Conexión (envoltorio común)
# ---------------------------------------------------------------------------
class Conexion:
    def __init__(self, crudo, postgres, pool=None):
        self.crudo, self.postgres, self._pool = crudo, postgres, pool

    def execute(self, sql, params=()):
        if self.postgres:
            if params:
                return self.crudo.execute(_a_postgres(sql), tuple(params))
            return self.crudo.execute(sql)
        return self.crudo.execute(sql, params)

    def insertar(self, sql, params=()):
        """Ejecuta un INSERT y devuelve el `id` nuevo (SQLite: lastrowid; PostgreSQL: RETURNING id)."""
        if self.postgres:
            return self.crudo.execute(_a_postgres(sql) + " RETURNING id", tuple(params)).fetchone()[0]
        return self.crudo.execute(sql, params).lastrowid

    def executescript(self, script):
        if self.postgres:
            self.crudo.execute(script)          # sin parámetros, PostgreSQL acepta varias sentencias
        else:
            self.crudo.executescript(script)

    def commit(self):
        self.crudo.commit()

    def rollback(self):
        self.crudo.rollback()

    def close(self):
        if self._pool is not None:             # PostgreSQL: la conexión vuelve al grupo, no se cierra
            try:
                self.crudo.rollback()          # lo no confirmado con commit() se descarta (como al cerrar SQLite)
            finally:
                self._pool.putconn(self.crudo)
        else:
            self.crudo.close()

    # --- consultas de estructura (cambian según el motor) ---
    def columnas(self, tabla):
        if self.postgres:
            filas = self.execute("SELECT column_name FROM information_schema.columns "
                                 "WHERE table_schema = current_schema() AND table_name = ?", (tabla,))
            return {f[0] for f in filas}
        return {f[1] for f in self.crudo.execute(f"PRAGMA table_info({tabla})")}

    def existe_tabla(self, tabla):
        if self.postgres:
            return self.execute("SELECT to_regclass(?)", (f"public.{tabla}",)).fetchone()[0] is not None
        return self.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                            (tabla,)).fetchone() is not None


_pool = None
_pool_url = None
_candado_pool = threading.Lock()


def _obtener_pool():
    """Un grupo de conexiones reutilizables: abrir una conexión a Supabase en cada petición sería lento."""
    global _pool, _pool_url
    if psycopg is None or ConnectionPool is None:
        raise RuntimeError("Para usar PostgreSQL/Supabase instala las librerías: pip install -r requirements.txt")
    with _candado_pool:
        if _pool is None or _pool_url != DATABASE_URL:
            if _pool is not None:
                _pool.close()
            # Prueba directa ANTES de crear el grupo: si la contraseña, el usuario o el servidor están mal,
            # aquí sale el error real y enseguida (el grupo lo escondería detrás de un "timeout" tras 15 s).
            psycopg.connect(DATABASE_URL, connect_timeout=10).close()
            _pool = ConnectionPool(
                DATABASE_URL, min_size=1, max_size=5, timeout=15, open=True,
                check=ConnectionPool.check_connection,          # descarta conexiones que el servidor cerró
                # prepare_threshold=None: necesario con el "Transaction pooler" de Supabase (puerto 6543)
                kwargs={"row_factory": _fila_factory, "prepare_threshold": None})
            _pool_url = DATABASE_URL
        return _pool


def _cerrar_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(_cerrar_pool)


def conectar():
    """Abre una conexión (fuera de Flask: seed.py, migraciones, arranque)."""
    if usa_postgres():
        pool = _obtener_pool()
        return Conexion(pool.getconn(), True, pool)
    crudo = sqlite3.connect(DB_PATH)
    crudo.row_factory = sqlite3.Row      # permite acceder por nombre de columna
    crudo.execute("PRAGMA foreign_keys = ON")
    return Conexion(crudo, False)


def get_db():
    """Devuelve la conexión de la petición actual (se crea una sola vez)."""
    if "db" not in g:
        g.db = conectar()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Creación y mantenimiento del esquema
# ---------------------------------------------------------------------------
def crear_esquema_si_falta():
    """PostgreSQL: crea las tablas que falten, sin tocar los datos. (SQLite: no hace nada; allí
    el archivo se crea con init_db() la primera vez.)"""
    if not usa_postgres():
        return
    conn = conectar()
    try:
        conn.executescript(SCHEMA_PG_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def crear_vistas(conn):
    """(Re)crea las vistas de lectura. Es seguro repetirlo: no toca los datos. Si algo falla no se
    detiene la app (las vistas son solo para leer mejor la base), solo se avisa."""
    try:
        for nombre, consulta in VISTAS.items():
            if conn.postgres:
                conn.execute(f"CREATE OR REPLACE VIEW {nombre} AS {consulta}")
            else:
                conn.execute(f"DROP VIEW IF EXISTS {nombre}")
                conn.execute(f"CREATE VIEW {nombre} AS {consulta}")
        # PostgreSQL 15+: que la vista respete la seguridad (RLS) de las tablas; así la API pública de
        # Supabase tampoco puede leer los datos a través de ellas.
        if conn.postgres and int(conn.execute("SHOW server_version_num").fetchone()[0]) >= 150000:
            for nombre in VISTAS:
                conn.execute(f"ALTER VIEW {nombre} SET (security_invoker = true)")
        conn.commit()
    except Exception as exc:                        # noqa: BLE001
        conn.rollback()
        print(f"Aviso: no se pudieron crear las vistas de lectura ({type(exc).__name__}: {exc}). "
              "La app funciona igual.")


def init_db():
    """Crea las tablas desde cero. ¡BORRA los datos existentes!"""
    conn = conectar()
    try:
        if conn.postgres:
            conn.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLAS)) + " CASCADE")
            conn.commit()
            conn.executescript(SCHEMA_PG_PATH.read_text(encoding="utf-8"))
        else:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        crear_vistas(conn)
    finally:
        conn.close()


AJUSTES_SQL = "CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT NOT NULL DEFAULT '')"


def migrar_login(conn):
    """Bases de datos creadas antes del login no tienen las columnas de acceso:
    se las agregamos sin tocar los datos existentes."""
    for tabla in ("usuarios", "odontologos"):
        cols = conn.columnas(tabla)
        if "usuario" not in cols:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN usuario TEXT")
        if "clave_hash" not in cols:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN clave_hash TEXT")
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{tabla}_usuario ON {tabla}(usuario)")


def asegurar_ajustes():
    """Deja la base lista al arrancar: tablas (PostgreSQL), tabla de ajustes y columnas de login
    (no toca tus datos)."""
    crear_esquema_si_falta()
    conn = conectar()
    try:
        conn.execute(AJUSTES_SQL)
        migrar_login(conn)
        conn.commit()
        crear_vistas(conn)
    finally:
        conn.close()


def hay_administrador():
    """¿Existe al menos un administrador que pueda iniciar sesión?"""
    n = get_db().execute(
        "SELECT COUNT(*) FROM usuarios WHERE rol = 'Administrador' "
        "AND usuario IS NOT NULL AND clave_hash IS NOT NULL").fetchone()[0]
    return n > 0


def get_ajuste(clave, defecto=""):
    fila = get_db().execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
    return fila[0] if fila and fila[0] != "" else defecto


def set_ajuste(clave, valor):
    db = get_db()
    db.execute("INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
               "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, valor))
    db.commit()


def borrar_todos_los_datos():
    """Deja el sistema vacío de trabajo (materiales, servicios, odontólogos, pacientes y
    órdenes). Conserva los ajustes y las cuentas del equipo, para no quedarte sin poder entrar."""
    db = get_db()
    tablas = ("movimientos_inventario", "historial_estados", "ordenes", "servicio_materiales",
              "pacientes", "odontologos", "servicios", "materiales")
    if db.postgres:
        # TRUNCATE + RESTART IDENTITY: vacía y reinicia los contadores de id (como sqlite_sequence)
        db.execute("TRUNCATE TABLE " + ", ".join(tablas) + " RESTART IDENTITY")
    else:
        for t in tablas:
            db.execute(f"DELETE FROM {t}")
        try:
            marcas = ",".join("?" for _ in tablas)
            db.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({marcas})", tablas)
        except sqlite3.Error:
            pass
    db.commit()


def volcar_json():
    """Todas las tablas en un JSON (respaldo descargable cuando la base es PostgreSQL)."""
    db = get_db()
    datos = {t: [dict(zip(f.keys(), tuple(f))) for f in db.execute(f"SELECT * FROM {t}")] for t in TABLAS}
    return json.dumps(datos, ensure_ascii=False, indent=1, default=str)
