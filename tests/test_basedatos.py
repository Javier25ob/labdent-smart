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


class Vistas(BaseLogin):
    """Las vistas muestran nombres en vez de ids, sin duplicar datos."""

    def preparar(self):
        db = database.conectar()
        od = db.insertar("INSERT INTO odontologos (nombre, clinica) VALUES ('Dra. Ana', 'Clínica Sol')")
        pa = db.insertar("INSERT INTO pacientes (nombre, odontologo_id) VALUES ('Juan Pérez', ?)", (od,))
        sv = db.insertar("INSERT INTO servicios (nombre, precio, dias_estimados) VALUES ('Corona', 380000, 5)")
        ma = db.insertar("INSERT INTO materiales (nombre, unidad, stock) VALUES ('Zirconio', 'und', 10)")
        db.execute("INSERT INTO servicio_materiales (servicio_id, material_id, cantidad) VALUES (?, ?, 2)", (sv, ma))
        orden = db.insertar("INSERT INTO ordenes (odontologo_id, paciente_id, servicio_id, fecha_ingreso, "
                            "fecha_entrega_estimada) VALUES (?, ?, ?, '2026-11-04 10:00:00', '2026-11-09')",
                            (od, pa, sv))
        db.execute("INSERT INTO historial_estados (orden_id, estado, fecha) VALUES (?, 'Recibida', '2026-11-04')", (orden,))
        db.execute("INSERT INTO movimientos_inventario (material_id, tipo, cantidad, fecha, orden_id, nota) "
                   "VALUES (?, 'SALIDA', 2, '2026-11-04', ?, 'Consumo')", (ma, orden))
        db.commit()
        return db

    def test_ordenes_con_nombres(self):
        db = self.preparar()
        try:
            f = db.execute("SELECT * FROM v_ordenes").fetchone()
            self.assertEqual((f["odontologo"], f["clinica"], f["paciente"], f["servicio"], f["estado"]),
                             ("Dra. Ana", "Clínica Sol", "Juan Pérez", "Corona", "Recibida"))
            self.assertEqual(f["precio"], 380000)
        finally:
            db.close()

    def test_resto_de_vistas(self):
        db = self.preparar()
        try:
            self.assertEqual(db.execute("SELECT paciente, odontologo FROM v_pacientes").fetchone()[:], ("Juan Pérez", "Dra. Ana"))
            m = db.execute("SELECT material, tipo, cantidad, orden FROM v_movimientos_inventario").fetchone()
            self.assertEqual((m["material"], m["tipo"], m["cantidad"]), ("Zirconio", "SALIDA", 2))
            r = db.execute("SELECT servicio, material, cantidad FROM v_recetas").fetchone()
            self.assertEqual((r["servicio"], r["material"], r["cantidad"]), ("Corona", "Zirconio", 2))
            h = db.execute("SELECT paciente, servicio, estado FROM v_historial_estados").fetchone()
            self.assertEqual(tuple(h), ("Juan Pérez", "Corona", "Recibida"))
        finally:
            db.close()

    def test_las_vistas_no_exponen_contrasenas_y_se_pueden_recrear(self):
        db = database.conectar()
        try:
            for nombre in database.VISTAS:
                cur = db.execute(f"SELECT * FROM {nombre}")
                self.assertEqual(cur.fetchall(), [])
                nombres = [d[0] for d in cur.description]
                self.assertFalse([n for n in nombres if "clave" in n or "hash" in n], nombre)
            database.crear_vistas(db)
            database.crear_vistas(db)                    # repetirlo no falla ni borra nada
        finally:
            db.close()
        database.asegurar_ajustes()                     # el arranque normal también las deja listas

    def test_nombre_cambiado_se_refleja_en_las_ordenes_viejas(self):
        db = self.preparar()
        try:
            db.execute("UPDATE pacientes SET nombre = 'Juan P. Gómez'")
            db.commit()
            self.assertEqual(db.execute("SELECT paciente FROM v_ordenes").fetchone()[0], "Juan P. Gómez")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
