"""Copia los datos de tu base SQLite (labdent_datos.db) a PostgreSQL / Supabase.

Uso (con DATABASE_URL ya definida en el entorno o en el archivo .env):

    python migrar_sqlite_a_postgres.py                  # usa labdent_datos.db
    python migrar_sqlite_a_postgres.py ruta/otra.db     # otro archivo SQLite
    python migrar_sqlite_a_postgres.py --reemplazar     # si PostgreSQL ya tiene datos, los borra antes

Es seguro: si PostgreSQL ya tiene datos y no pasas --reemplazar, no toca nada.
"""
import sqlite3
import sys
from pathlib import Path

import database
from database import TABLAS


def main(argv):
    reemplazar = "--reemplazar" in argv
    rutas = [a for a in argv if not a.startswith("--")]
    origen = Path(rutas[0]) if rutas else database.DB_PATH
    if not database.usa_postgres():
        sys.exit("Falta DATABASE_URL: defínela en el entorno o en el archivo .env (ver .env.example).")
    if not origen.exists():
        sys.exit(f"No encuentro la base SQLite: {origen}")

    lite = sqlite3.connect(origen)
    lite.row_factory = sqlite3.Row
    database.crear_esquema_si_falta()
    pg = database.conectar()
    try:
        con_datos = [t for t in TABLAS if t != "configuracion"
                     and pg.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] > 0]
        if con_datos and not reemplazar:
            sys.exit("PostgreSQL ya tiene datos en: " + ", ".join(con_datos) +
                     ".\nNo se copió nada. Si quieres reemplazarlos, vuelve a correr con --reemplazar.")
        if con_datos:
            pg.execute("TRUNCATE TABLE " + ", ".join(TABLAS) + " RESTART IDENTITY")

        for tabla in TABLAS:
            existe = lite.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone()
            if not existe:
                print(f"  {tabla:<24} (no existe en SQLite, se omite)")
                continue
            cols_lite = [c[1] for c in lite.execute(f"PRAGMA table_info({tabla})")]
            cols = [c for c in cols_lite if c in pg.columnas(tabla)]      # solo las columnas que existen en ambos
            filas = lite.execute(f"SELECT {', '.join(cols)} FROM {tabla}").fetchall()
            marcas = ", ".join("?" for _ in cols)
            for f in filas:
                pg.execute(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({marcas})", tuple(f))
            if "id" in cols:      # que los próximos ids sigan después del mayor copiado
                pg.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
                           f"COALESCE((SELECT MAX(id) FROM {tabla}), 1), (SELECT MAX(id) FROM {tabla}) IS NOT NULL)")
            print(f"  {tabla:<24} {len(filas):>5} filas")
        pg.commit()
        print("\nListo: los datos ya están en PostgreSQL.")
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
        lite.close()


if __name__ == "__main__":
    main(sys.argv[1:])
