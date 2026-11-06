"""Pruebas del portal del odontólogo ampliado: solicitudes, pacientes, historial, perfil
y la bandeja de solicitudes del laboratorio.

    python -m unittest discover -s tests -v
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database                       # noqa: E402
from tests.test_login import CLAVE, BaseLogin   # noqa: E402


class BasePortal(BaseLogin):
    """Admin + servicio + dos odontólogos con acceso («uno» y «dos»), un paciente de cada uno."""

    def setUp(self):
        super().setUp()
        self.admin = self.crear_admin()
        self.admin.post("/catalogos/servicio", data={"nombre": "Corona zirconio", "precio": "380000", "dias": "5"})
        for nombre, usuario in (("Dra. Uno", "uno"), ("Dr. Dos", "dos")):
            self.admin.post("/catalogos/odontologo", data={"nombre": nombre, "clinica": "C", "telefono": "1",
                                                           "usuario": usuario, "clave": CLAVE})
        self.admin.post("/catalogos/paciente", data={"nombre": "Ana DeUno", "odontologo_id": "1"})
        self.admin.post("/catalogos/paciente", data={"nombre": "Beto DeDos", "odontologo_id": "2"})
        self.uno, _ = self.entrar("uno", portal=True)
        self.dos, _ = self.entrar("dos", portal=True)

    def fila(self, sql, params=()):
        with self.app.app_context():
            return database.get_db().execute(sql, params).fetchone()

    def solicitar(self, cliente=None, paciente_id="1", servicio_id="1", **extra):
        datos = {"paciente_id": paciente_id, "servicio_id": servicio_id, "observaciones": "Color A2", **extra}
        return (cliente or self.uno).post("/portal/solicitar", data=datos)


class Solicitudes(BasePortal):
    def test_solicitar_con_su_paciente_queda_pendiente(self):
        r = self.solicitar()
        self.assertEqual(r.status_code, 302)
        s = self.fila("SELECT * FROM solicitudes")
        self.assertEqual((s["estado"], s["odontologo_id"], s["observaciones"]), ("Pendiente", 1, "Color A2"))
        inicio = self.uno.get("/portal/").get_data(as_text=True)
        self.assertIn("esperando respuesta", inicio)
        self.assertIn("Corona zirconio", inicio)
        # todavía NO es una orden
        self.assertEqual(self.fila("SELECT COUNT(*) FROM ordenes")[0], 0)

    def test_no_puede_usar_el_paciente_de_otro_odontologo(self):
        r = self.solicitar(paciente_id="2")          # Beto es del Dr. Dos
        self.assertEqual(r.status_code, 200)
        self.assertIn("Elige uno de tus pacientes", r.get_data(as_text=True))
        self.assertEqual(self.fila("SELECT COUNT(*) FROM solicitudes")[0], 0)

    def test_servicio_invalido_no_deja_paciente_suelto(self):
        r = self.solicitar(paciente_id="nuevo", paciente_nombre="Carla Nueva", servicio_id="99")
        self.assertIn("Elige un servicio", r.get_data(as_text=True))
        self.assertIsNone(self.fila("SELECT id FROM pacientes WHERE nombre = 'Carla Nueva'"))

    def test_paciente_nuevo_desde_la_solicitud(self):
        self.solicitar(paciente_id="nuevo", paciente_nombre="Carla Nueva")
        p = self.fila("SELECT * FROM pacientes WHERE nombre = 'Carla Nueva'")
        self.assertEqual(p["odontologo_id"], 1)
        self.assertEqual(self.fila("SELECT paciente_id FROM solicitudes")[0], p["id"])

    def test_laboratorio_acepta_y_se_crea_la_orden(self):
        self.solicitar()
        bandeja = self.admin.get("/solicitudes/").get_data(as_text=True)
        self.assertIn("Dra. Uno", bandeja)
        self.assertIn("Solicitudes", self.admin.get("/").get_data(as_text=True))
        r = self.admin.post("/solicitudes/1/aceptar")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/ordenes/1", r.headers["Location"])
        s = self.fila("SELECT * FROM solicitudes WHERE id = 1")
        self.assertEqual((s["estado"], s["orden_id"]), ("Aceptada", 1))
        o = self.fila("SELECT * FROM ordenes WHERE id = 1")
        self.assertEqual((o["odontologo_id"], o["paciente_id"], o["estado"]), (1, 1, "Recibida"))
        self.assertIn("Color A2", o["observaciones"])
        # el odontólogo ya la ve como trabajo en proceso y entra a su detalle
        self.assertIn("/portal/orden/1", self.uno.get("/portal/").get_data(as_text=True))
        detalle = self.uno.get("/portal/orden/1").get_data(as_text=True)
        self.assertIn("Solicitado desde el portal", detalle)
        # aceptar dos veces no crea otra orden
        self.admin.post("/solicitudes/1/aceptar")
        self.assertEqual(self.fila("SELECT COUNT(*) FROM ordenes")[0], 1)

    def test_rechazo_exige_motivo_y_el_odontologo_lo_ve(self):
        self.solicitar()
        self.admin.post("/solicitudes/1/rechazar", data={"motivo": ""})
        self.assertEqual(self.fila("SELECT estado FROM solicitudes")[0], "Pendiente")
        self.admin.post("/solicitudes/1/rechazar", data={"motivo": "Falta la impresión"})
        self.assertEqual(self.fila("SELECT estado FROM solicitudes")[0], "Rechazada")
        hist = self.uno.get("/portal/historial").get_data(as_text=True)
        self.assertIn("Falta la impresión", hist)
        self.assertIn("Rechazada", hist)

    def test_cancelar_solo_la_propia_y_pendiente(self):
        self.solicitar()
        self.dos.post("/portal/solicitudes/1/cancelar")                # no es suya
        self.assertEqual(self.fila("SELECT estado FROM solicitudes")[0], "Pendiente")
        self.uno.post("/portal/solicitudes/1/cancelar")
        self.assertEqual(self.fila("SELECT estado FROM solicitudes")[0], "Cancelada")
        r = self.admin.post("/solicitudes/1/aceptar")                  # ya no se puede aceptar
        self.assertEqual(self.fila("SELECT COUNT(*) FROM ordenes")[0], 0)
        self.assertIn("/solicitudes/", r.headers["Location"])

    def test_cliente_no_entra_a_la_bandeja_del_laboratorio(self):
        self.solicitar()
        r = self.uno.post("/solicitudes/1/aceptar")
        self.assertIn("/portal/", r.headers["Location"])
        self.assertEqual(self.fila("SELECT estado FROM solicitudes")[0], "Pendiente")


class DetalleEHistorial(BasePortal):
    def test_orden_ajena_da_404(self):
        self.admin.post("/ordenes/nueva", data={"odontologo_id": "2", "paciente_id": "2", "servicio_id": "1"})
        self.assertEqual(self.dos.get("/portal/orden/1").status_code, 200)
        self.assertEqual(self.uno.get("/portal/orden/1").status_code, 404)
        self.assertEqual(self.uno.get("/portal/orden/999").status_code, 404)

    def test_entregada_pasa_al_historial(self):
        self.admin.post("/ordenes/nueva", data={"odontologo_id": "1", "paciente_id": "1", "servicio_id": "1"})
        for _ in range(3):
            self.admin.post("/ordenes/1/avanzar")
        self.assertEqual(self.fila("SELECT estado FROM ordenes")[0], "Entregada")
        inicio = self.uno.get("/portal/").get_data(as_text=True)
        self.assertNotIn("/portal/orden/1", inicio)
        hist = self.uno.get("/portal/historial").get_data(as_text=True)
        self.assertIn("/portal/orden/1", hist)
        self.assertIn("A tiempo", hist)


class Pacientes(BasePortal):
    def test_ve_solo_sus_pacientes(self):
        html = self.uno.get("/portal/pacientes").get_data(as_text=True)
        self.assertIn("Ana DeUno", html)
        self.assertNotIn("Beto DeDos", html)

    def test_agregar_editar_y_eliminar(self):
        self.uno.post("/portal/pacientes", data={"nombre": "Diana Nueva"})
        pid = self.fila("SELECT id, odontologo_id FROM pacientes WHERE nombre = 'Diana Nueva'")
        self.assertEqual(pid["odontologo_id"], 1)
        self.uno.post(f"/portal/pacientes/{pid['id']}/editar", data={"nombre": "Diana Pérez"})
        self.assertIsNotNone(self.fila("SELECT id FROM pacientes WHERE nombre = 'Diana Pérez'"))
        self.uno.post(f"/portal/pacientes/{pid['id']}/eliminar")
        self.assertIsNone(self.fila("SELECT id FROM pacientes WHERE nombre = 'Diana Pérez'"))

    def test_no_toca_pacientes_ajenos(self):
        self.assertEqual(self.uno.post("/portal/pacientes/2/editar", data={"nombre": "X"}).status_code, 404)
        self.assertEqual(self.uno.post("/portal/pacientes/2/eliminar").status_code, 404)
        self.assertEqual(self.fila("SELECT nombre FROM pacientes WHERE id = 2")[0], "Beto DeDos")

    def test_no_elimina_paciente_con_solicitudes(self):
        self.solicitar()
        self.uno.post("/portal/pacientes/1/eliminar")
        self.assertIsNotNone(self.fila("SELECT id FROM pacientes WHERE id = 1"))


class Perfil(BasePortal):
    def test_editar_datos(self):
        self.uno.post("/portal/perfil", data={"accion": "datos", "nombre": "Dra. Uno Pérez",
                                              "clinica": "Sonrisas", "telefono": "3001234567"})
        o = self.fila("SELECT * FROM odontologos WHERE id = 1")
        self.assertEqual((o["nombre"], o["clinica"], o["telefono"]), ("Dra. Uno Pérez", "Sonrisas", "3001234567"))

    def test_cambiar_contrasena(self):
        nueva = "otra-clave-456"
        self.uno.post("/portal/perfil", data={"accion": "clave", "actual": "mala", "nueva": nueva, "nueva2": nueva})
        _, r = self.entrar("uno", nueva, portal=True)
        self.assertEqual(r.status_code, 200)            # no cambió: la actual era incorrecta
        self.uno.post("/portal/perfil", data={"accion": "clave", "actual": CLAVE, "nueva": nueva, "nueva2": "distinta"})
        _, r = self.entrar("uno", nueva, portal=True)
        self.assertEqual(r.status_code, 200)            # no cambió: no coinciden
        self.uno.post("/portal/perfil", data={"accion": "clave", "actual": CLAVE, "nueva": nueva, "nueva2": nueva})
        _, r = self.entrar("uno", nueva, portal=True)
        self.assertEqual(r.status_code, 302)            # ahora sí


class Mantenimiento(BasePortal):
    def test_base_vieja_sin_tabla_de_solicitudes_se_actualiza_sola(self):
        if database.usa_postgres():
            self.skipTest("Solo aplica a SQLite")
        con = sqlite3.connect(database.DB_PATH)
        con.execute("DROP TABLE solicitudes")
        con.commit()
        con.close()
        database.asegurar_ajustes()
        self.assertEqual(self.solicitar().status_code, 302)

    def test_borrar_todos_los_datos_con_solicitudes(self):
        self.solicitar()
        with self.app.test_request_context():
            database.borrar_todos_los_datos()
        self.assertEqual(self.fila("SELECT COUNT(*) FROM solicitudes")[0], 0)
