"""Pruebas de los datos del paciente (nombre, documento y teléfono) en todo el sistema.

    python -m unittest discover -s tests -v
"""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database                                   # noqa: E402
from services import pacientes as pac             # noqa: E402
from tests.test_portal import BasePortal          # noqa: E402


class Validacion(unittest.TestCase):
    def leer(self, **campos):
        return pac.leer({"nombre": "Ana Ruiz", **campos})

    def test_solo_nombre_es_valido(self):
        datos, error = self.leer()
        self.assertIsNone(error)
        self.assertEqual((datos["documento"], datos["tipo_documento"], datos["telefono"]), (None, None, None))

    def test_documento_se_limpia(self):
        datos, _ = self.leer(tipo_documento="CC", documento=" 1.065.234-567 ", telefono="300 123 4567")
        self.assertEqual((datos["tipo_documento"], datos["documento"]), ("CC", "1065234567"))
        self.assertEqual(datos["telefono"], "300 123 4567")

    def test_errores(self):
        casos = [
            ({"nombre": ""}, "nombre"),
            ({"tipo_documento": "XX", "documento": "123456"}, "tipo de documento"),
            ({"tipo_documento": "CC", "documento": "12AB34"}, "solo lleva números"),
            ({"tipo_documento": "CC", "documento": "12"}, "entre 4 y 20"),
            ({"telefono": "12345"}, "teléfono"),
            ({"telefono": "300-abc-4567"}, "teléfono"),
        ]
        for campos, texto in casos:
            with self.subTest(campos=campos):
                _, error = pac.leer({"nombre": "Ana", **campos})
                self.assertIn(texto, error)

    def test_pasaporte_admite_letras(self):
        datos, error = self.leer(tipo_documento="PA", documento="ab123456")
        self.assertIsNone(error)
        self.assertEqual(datos["documento"], "AB123456")


class EnElSistema(BasePortal):
    DOC = {"tipo_documento": "CC", "documento": "1065234567", "telefono": "3001234567"}

    def test_laboratorio_registra_con_documento_y_telefono(self):
        self.admin.post("/catalogos/paciente", data={"nombre": "Carlos Pérez", "odontologo_id": "1", **self.DOC})
        p = self.fila("SELECT * FROM pacientes WHERE nombre = 'Carlos Pérez'")
        self.assertEqual((p["tipo_documento"], p["documento"], p["telefono"]), ("CC", "1065234567", "3001234567"))
        html = self.admin.get("/catalogos/?tab=pacientes").get_data(as_text=True)
        self.assertIn("CC 1065234567", html)

    def test_documento_repetido_mismo_odontologo_se_rechaza(self):
        self.admin.post("/catalogos/paciente", data={"nombre": "Uno", "odontologo_id": "1", **self.DOC})
        r = self.admin.post("/catalogos/paciente", data={"nombre": "Otro", "odontologo_id": "1", **self.DOC},
                            follow_redirects=True)
        self.assertIn("mismo documento", r.get_data(as_text=True))
        self.assertIsNone(self.fila("SELECT id FROM pacientes WHERE nombre = 'Otro'"))
        # otro odontólogo sí puede tener a esa misma persona como paciente
        self.admin.post("/catalogos/paciente", data={"nombre": "Otro", "odontologo_id": "2", **self.DOC})
        self.assertIsNotNone(self.fila("SELECT id FROM pacientes WHERE nombre = 'Otro'"))

    def test_editar_desde_el_laboratorio(self):
        self.admin.post("/catalogos/paciente/1/editar", data={"nombre": "Ana De Uno", "odontologo_id": "1", **self.DOC})
        p = self.fila("SELECT * FROM pacientes WHERE id = 1")
        self.assertEqual((p["nombre"], p["documento"]), ("Ana De Uno", "1065234567"))
        r = self.admin.post("/catalogos/paciente/1/editar", data={"nombre": "Ana", "odontologo_id": "1",
                                                                  "documento": "ABC", "tipo_documento": "CC"},
                            follow_redirects=True)
        self.assertIn("solo lleva números", r.get_data(as_text=True))
        self.assertEqual(self.fila("SELECT documento FROM pacientes WHERE id = 1")[0], "1065234567")

    def test_paciente_nuevo_al_crear_orden(self):
        self.admin.post("/ordenes/nueva", data={"odontologo_id": "1", "paciente_id": "nuevo", "servicio_id": "1",
                                               "paciente_nombre": "Dora Nueva", "paciente_tipo_documento": "TI",
                                               "paciente_documento": "1067123456", "paciente_telefono": "3157654321"})
        p = self.fila("SELECT * FROM pacientes WHERE nombre = 'Dora Nueva'")
        self.assertEqual((p["odontologo_id"], p["tipo_documento"], p["documento"]), (1, "TI", "1067123456"))
        self.assertEqual(self.fila("SELECT paciente_id FROM ordenes")[0], p["id"])
        detalle = self.admin.get("/ordenes/1").get_data(as_text=True)
        self.assertIn("TI 1067123456", detalle)
        self.assertIn("3157654321", detalle)

    def test_orden_con_documento_invalido_no_crea_nada(self):
        self.admin.post("/ordenes/nueva", data={"odontologo_id": "1", "paciente_id": "nuevo", "servicio_id": "1",
                                               "paciente_nombre": "Mal Dato", "paciente_documento": "12"})
        self.assertIsNone(self.fila("SELECT id FROM pacientes WHERE nombre = 'Mal Dato'"))
        self.assertEqual(self.fila("SELECT COUNT(*) FROM ordenes")[0], 0)

    def test_odontologo_registra_y_edita_sus_pacientes(self):
        self.uno.post("/portal/pacientes", data={"nombre": "Elena Sol", **self.DOC})
        p = self.fila("SELECT * FROM pacientes WHERE nombre = 'Elena Sol'")
        self.assertEqual((p["odontologo_id"], p["documento"], p["telefono"]), (1, "1065234567", "3001234567"))
        self.assertIn("CC 1065234567", self.uno.get("/portal/pacientes").get_data(as_text=True))
        self.uno.post(f"/portal/pacientes/{p['id']}/editar",
                      data={"nombre": "Elena Sol", "tipo_documento": "CC", "documento": "1065234567",
                            "telefono": "3209998877", "odontologo_id": "2"})          # no puede regalarlo a otro
        p = self.fila(f"SELECT * FROM pacientes WHERE id = {p['id']}")
        self.assertEqual((p["telefono"], p["odontologo_id"]), ("3209998877", 1))

    def test_portal_error_conserva_lo_escrito(self):
        r = self.uno.post("/portal/pacientes", data={"nombre": "Fabio Luna", "documento": "12"})
        html = r.get_data(as_text=True)
        self.assertIn("entre 4 y 20", html)
        self.assertIn('value="Fabio Luna"', html)

    def test_paciente_nuevo_en_la_solicitud_con_datos(self):
        self.solicitar(paciente_id="nuevo", paciente_nombre="Gina Paz", paciente_tipo_documento="CC",
                       paciente_documento="49765432", paciente_telefono="3154567890")
        p = self.fila("SELECT * FROM pacientes WHERE nombre = 'Gina Paz'")
        self.assertEqual((p["documento"], p["telefono"]), ("49765432", "3154567890"))
        self.assertEqual(self.fila("SELECT paciente_id FROM solicitudes")[0], p["id"])

    def test_consulta_publica_no_muestra_documento(self):
        self.admin.post("/catalogos/paciente/1/editar", data={"nombre": "Ana DeUno", "odontologo_id": "1", **self.DOC})
        self.admin.post("/ordenes/nueva", data={"odontologo_id": "1", "paciente_id": "1", "servicio_id": "1"})
        from services import seguimiento
        with self.app.app_context():
            codigo = seguimiento.codigo(1)
        html = self.cliente_http().get(f"/seguimiento/{codigo}").get_data(as_text=True)
        self.assertNotIn("1065234567", html)
        self.assertNotIn("3001234567", html)

    def test_vista_legible_incluye_documento(self):
        self.admin.post("/catalogos/paciente/1/editar", data={"nombre": "Ana DeUno", "odontologo_id": "1", **self.DOC})
        f = self.fila("SELECT paciente, tipo_documento, documento, telefono FROM v_pacientes WHERE id = 1")
        self.assertEqual(tuple(f), ("Ana DeUno", "CC", "1065234567", "3001234567"))


class Migracion(BasePortal):
    def test_base_vieja_sin_columnas_se_actualiza_sola(self):
        if database.usa_postgres():
            self.skipTest("Solo aplica a SQLite (en PostgreSQL se usa el mismo ALTER TABLE)")
        con = sqlite3.connect(database.DB_PATH)
        con.execute("DROP VIEW IF EXISTS v_pacientes")
        for col in ("telefono", "documento", "tipo_documento"):
            con.execute("DROP INDEX IF EXISTS idx_pacientes_documento")
            con.execute(f"ALTER TABLE pacientes DROP COLUMN {col}")
        con.commit()
        con.close()
        database.asegurar_ajustes()
        self.admin.post("/catalogos/paciente/1/editar", data={"nombre": "Ana", "odontologo_id": "1",
                                                              "documento": "123456", "tipo_documento": "CC"})
        self.assertEqual(self.fila("SELECT documento FROM pacientes WHERE id = 1")[0], "123456")
        self.assertEqual(self.fila("SELECT nombre FROM pacientes WHERE id = 2")[0], "Beto DeDos")   # nada se perdió
