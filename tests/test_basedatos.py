"""Pruebas de la capa de base de datos (SQLite y PostgreSQL/Supabase).

    python -m unittest discover -s tests -v                      # contra SQLite temporal
    TEST_DATABASE_URL=postgresql://... python -m unittest ...    # contra PostgreSQL
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config    # noqa: E402
import database  # noqa: E402
from test_login import BaseLogin  # noqa: E402


class Fila(unittest.TestCase):
    def test_se_lee_por_nombre_posicion_y_con_dict(self):
        f = database.Fila(["id", "nombre"], [3, "Ana"])
        self.assertEqual((f["id"], f[1], f[0]), (3, "Ana", 3))
        self.assertEqual(dict(f), {"id": 3, "nombre": "Ana"})
        self.assertEqual(list(f), [3, "Ana"])
        with self.assertRaises(KeyError):
            f["no_existe"]


class Traduccion(unittest.TestCase):
    def test_marcadores_y_porcentajes(self):
        self.assertEqual(database._a_postgres("SELECT * FROM t WHERE a = ? AND b LIKE '%x'"),
                         "SELECT * FROM t WHERE a = %s AND b LIKE '%%x'")


class UrlBaseDeDatos(unittest.TestCase):
    def url(self, valor):
        with mock.patch.dict(os.environ, {"DATABASE_URL": valor}):
            return config._url_base_de_datos()

    def test_vacia_usa_sqlite(self):
        self.assertEqual(self.url(""), "")

    def test_remota_exige_ssl_y_corrige_postgres(self):
        u = self.url("postgres://u:p@db.supabase.co:5432/postgres")
        self.assertEqual(u, "postgresql://u:p@db.supabase.co:5432/postgres?sslmode=require")

    def test_no_duplica_sslmode_y_local_no_lo_pide(self):
        self.assertEqual(self.url("postgresql://u:p@h.com/db?sslmode=disable"), "postgresql://u:p@h.com/db?sslmode=disable")
        self.assertNotIn("sslmode", self.url("postgresql://u@localhost:5432/db"))


class Operaciones(BaseLogin):
    """Se ejecutan en el motor activo (SQLite, o PostgreSQL si hay TEST_DATABASE_URL)."""

    def test_insertar_devuelve_id_y_las_filas_se_leen_por_nombre(self):
        db = database.conectar()
        try:
            a = db.insertar("INSERT INTO servicios (nombre, precio, dias_estimados) VALUES (?, ?, ?)", ("A", 100.5, 3))
            b = db.insertar("INSERT INTO servicios (nombre, precio, dias_estimados) VALUES (?, ?, ?)", ("B", 200, 4))
            db.commit()
            self.assertEqual(b, a + 1)
            fila = db.execute("SELECT * FROM servicios WHERE id = ?", (a,)).fetchone()
            self.assertEqual((fila["nombre"], fila["precio"], fila[3]), ("A", 100.5, 3))
            self.assertIsInstance(fila["precio"], float)       # nunca Decimal: la app hace cuentas con floats
        finally:
            db.close()

    def test_unique_lanza_error_de_integridad_y_se_puede_seguir(self):
        db = database.conectar()
        try:
            db.execute("INSERT INTO usuarios (nombre, rol, usuario) VALUES ('X', 'Técnico', 'repetido')")
            db.commit()
            with self.assertRaises(database.ErrorIntegridad):
                db.execute("INSERT INTO usuarios (nombre, rol, usuario) VALUES ('Y', 'Técnico', 'repetido')")
            db.rollback()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], 1)
        finally:
            db.close()

    def test_llave_foranea_se_respeta(self):
        db = database.conectar()
        try:
            with self.assertRaises(database.ErrorIntegridad):
                db.execute("INSERT INTO pacientes (nombre, odontologo_id) VALUES ('P', 999)")
            db.rollback()
        finally:
            db.close()

    def test_borrar_todo_reinicia_los_ids_y_conserva_cuentas(self):
        db = database.conectar()
        db.execute("INSERT INTO usuarios (nombre, rol) VALUES ('Staff', 'Técnico')")
        db.insertar("INSERT INTO servicios (nombre) VALUES ('S1')")
        db.commit()
        db.close()
        with self.app.app_context():
            database.borrar_todos_los_datos()
        db = database.conectar()
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM servicios").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], 1)
            self.assertEqual(db.insertar("INSERT INTO servicios (nombre) VALUES ('S2')"), 1)
            db.commit()
        finally:
            db.close()

    def test_respaldo_funciona_en_ambos_motores(self):
        c = self.crear_admin()
        r = c.get("/respaldo")
        self.assertEqual(r.status_code, 200)
        if database.usa_postgres():
            self.assertEqual(set(json.loads(r.get_data(as_text=True))), set(database.TABLAS))
        r.close()

    def test_crear_esquema_es_idempotente_y_no_borra_datos(self):
        db = database.conectar()
        db.insertar("INSERT INTO servicios (nombre) VALUES ('Persistente')")
        db.commit()
        db.close()
        database.crear_esquema_si_falta()
        database.asegurar_ajustes()
        db = database.conectar()
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM servicios").fetchone()[0], 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
