"""Pruebas del login (administrador y cliente).  Ejecutar desde la carpeta labdent_smart:

    python -m unittest discover -s tests -v

Cada prueba usa una base de datos temporal: no toca tus datos reales.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config            # noqa: E402
import database          # noqa: E402
from services import acceso  # noqa: E402

CLAVE = "clave-larga-123"


class BaseLogin(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.unlink(self._tmp.name)
        self._db_original = database.DB_PATH
        self._url_original = database.DATABASE_URL
        database.DB_PATH = Path(self._tmp.name)
        # Con TEST_DATABASE_URL las pruebas corren contra PostgreSQL (se recrean las tablas en cada una);
        # sin ella, contra un SQLite temporal.
        database.DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
        database.init_db()
        database.asegurar_ajustes()
        acceso._fallos.clear()
        from app import create_app
        self.app = create_app()
        self.app.config["TESTING"] = True

    def tearDown(self):
        database.DB_PATH = self._db_original
        database.DATABASE_URL = self._url_original
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    # --- ayudas ---
    def cliente_http(self):
        return self.app.test_client()

    def crear_admin(self, usuario="admin", nombre="Admin Uno"):
        c = self.cliente_http()
        r = c.post("/primer-acceso", data={"nombre": nombre, "usuario": usuario,
                                           "clave": CLAVE, "clave2": CLAVE})
        self.assertEqual(r.status_code, 302)
        return c          # ya queda con la sesión iniciada

    def entrar(self, usuario, clave=CLAVE, portal=False):
        c = self.cliente_http()
        r = c.post("/portal/login" if portal else "/login", data={"usuario": usuario, "clave": clave})
        return c, r

    def datos_con_admin(self):
        """Admin + un servicio + dos odontólogos con acceso y una orden de cada uno."""
        admin = self.crear_admin()
        admin.post("/catalogos/servicio", data={"nombre": "Corona", "precio": "380000", "dias": "5"})
        for nombre, usuario in (("Dra. Uno", "uno"), ("Dr. Dos", "dos")):
            r = admin.post("/catalogos/odontologo", data={"nombre": nombre, "clinica": "C", "telefono": "1",
                                                         "usuario": usuario, "clave": CLAVE})
            self.assertEqual(r.status_code, 302)
        admin.post("/catalogos/paciente", data={"nombre": "Paciente DeUno", "odontologo_id": "1"})
        admin.post("/catalogos/paciente", data={"nombre": "Paciente DeDos", "odontologo_id": "2"})
        admin.post("/ordenes/nueva", data={"odontologo_id": "1", "paciente_id": "1", "servicio_id": "1"})
        admin.post("/ordenes/nueva", data={"odontologo_id": "2", "paciente_id": "2", "servicio_id": "1"})
        return admin


class PrimerAcceso(BaseLogin):
    def test_sin_administrador_todo_lleva_a_crearlo(self):
        c = self.cliente_http()
        for ruta in ("/", "/login", "/ordenes/"):
            r = c.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertIn("/primer-acceso", r.headers["Location"], ruta)

    def test_validaciones_de_la_contrasena(self):
        c = self.cliente_http()
        corta = c.post("/primer-acceso", data={"nombre": "A", "usuario": "a", "clave": "abc", "clave2": "abc"})
        self.assertIn("al menos", corta.get_data(as_text=True))
        distinta = c.post("/primer-acceso", data={"nombre": "A", "usuario": "a", "clave": CLAVE, "clave2": CLAVE + "x"})
        self.assertIn("no coinciden", distinta.get_data(as_text=True))
        self.assertFalse(self.hay_usuarios())

    def hay_usuarios(self):
        with self.app.app_context():
            return database.get_db().execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] > 0

    def test_crea_admin_entra_y_la_pantalla_deja_de_existir(self):
        c = self.crear_admin()
        self.assertEqual(c.get("/").status_code, 200)
        r = self.cliente_http().get("/primer-acceso")
        self.assertIn("/login", r.headers["Location"])          # ya no se puede "crear otro admin"
        r = self.cliente_http().post("/primer-acceso", data={"nombre": "Intruso", "usuario": "x",
                                                            "clave": CLAVE, "clave2": CLAVE})
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            n = database.get_db().execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        self.assertEqual(n, 1)


class LoginPersonal(BaseLogin):
    def test_contrasena_incorrecta_y_correcta(self):
        self.crear_admin()
        _, r = self.entrar("admin", "incorrecta1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("incorrectos", r.get_data(as_text=True))
        c, r = self.entrar("ADMIN ")        # el usuario no distingue mayúsculas ni espacios
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)

    def test_usuario_inexistente_da_el_mismo_mensaje(self):
        self.crear_admin()
        _, r = self.entrar("fantasma")
        self.assertIn("incorrectos", r.get_data(as_text=True))

    def test_sin_sesion_redirige_y_recuerda_a_donde_ir(self):
        self.crear_admin()
        r = self.cliente_http().get("/inventario/")
        self.assertIn("/login", r.headers["Location"])
        self.assertIn("next=/inventario/", r.headers["Location"])

    def test_next_externo_no_se_obedece(self):
        self.crear_admin()
        for malo in ("https://evil.com", "//evil.com", "/\\evil.com", "javascript:alert(1)"):
            c = self.cliente_http()
            r = c.post("/login", query_string={"next": malo}, data={"usuario": "admin", "clave": CLAVE})
            self.assertEqual(r.status_code, 302)
            self.assertNotIn("evil", r.headers["Location"], malo)
            self.assertNotIn("javascript", r.headers["Location"], malo)

    def test_next_interno_si_se_obedece(self):
        self.crear_admin()
        r = self.cliente_http().post("/login", query_string={"next": "/inventario/"},
                                     data={"usuario": "admin", "clave": CLAVE})
        self.assertTrue(r.headers["Location"].endswith("/inventario/"))

    def test_bloqueo_tras_cinco_intentos_fallidos(self):
        self.crear_admin()
        c = self.cliente_http()
        for _ in range(config.INTENTOS_MAX):
            c.post("/login", data={"usuario": "admin", "clave": "mala-mala-1"})
        r = c.post("/login", data={"usuario": "admin", "clave": CLAVE})      # ni la correcta pasa
        self.assertEqual(r.status_code, 429)
        self.assertEqual(c.get("/").status_code, 302)

    def test_logout_solo_por_post(self):
        c = self.crear_admin()
        self.assertEqual(c.get("/logout").status_code, 405)
        self.assertEqual(c.get("/").status_code, 200)       # un enlace ajeno no te cierra la sesión
        c.post("/logout")
        self.assertEqual(c.get("/").status_code, 302)

    def test_la_clave_secreta_no_es_la_antigua_ni_corta(self):
        self.assertNotEqual(config.SECRET_KEY, "cambia-esta-clave-en-produccion")
        self.assertGreaterEqual(len(config.SECRET_KEY), 32)

    def test_cookie_con_otra_clave_no_sirve(self):
        """Quien no conoce la clave secreta no puede fabricar una sesión de administrador."""
        from flask.sessions import SecureCookieSessionInterface
        self.crear_admin()
        falsa = self.app.test_client()
        otra = type(self.app)(__name__)
        otra.secret_key = "clave-del-atacante"
        cookie = SecureCookieSessionInterface().get_signing_serializer(otra).dumps({"usuario_id": 1})
        falsa.set_cookie("session", cookie)
        r = falsa.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])


class Roles(BaseLogin):
    def crear_tecnico(self, admin):
        r = admin.post("/catalogos/usuario", data={"nombre": "Tec", "rol": "Técnico",
                                                  "usuario": "tec", "clave": CLAVE})
        self.assertEqual(r.status_code, 302)

    def test_tecnico_no_entra_a_zonas_de_administrador(self):
        admin = self.crear_admin()
        self.crear_tecnico(admin)
        tec, r = self.entrar("tec")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(tec.get("/ordenes/").status_code, 200)          # su trabajo normal, sí
        self.assertEqual(tec.get("/inventario/").status_code, 200)
        for ruta in ("/ajustes/", "/respaldo"):
            self.assertEqual(tec.get(ruta).status_code, 403, ruta)
        self.assertEqual(tec.post("/ajustes/borrar-datos", data={"confirmar": "BORRAR"}).status_code, 403)
        self.assertEqual(tec.post("/catalogos/usuario", data={"nombre": "X", "rol": "Administrador",
                                                              "usuario": "x", "clave": CLAVE}).status_code, 403)
        self.assertEqual(tec.post("/catalogos/usuario/1/editar", data={"nombre": "Admin", "rol": "Técnico"}).status_code, 403)
        self.assertEqual(tec.post("/catalogos/usuario/1/eliminar").status_code, 403)
        pagina = tec.get("/catalogos/?tab=usuarios").get_data(as_text=True)
        self.assertNotIn("Admin Uno", pagina)                            # ni siquiera ve la lista del equipo
        for ruta in ("/", "/ayuda"):                                          # ni un solo enlace a Ajustes
            self.assertNotIn("/ajustes/", tec.get(ruta).get_data(as_text=True), ruta)
        self.assertIn("/ajustes/", admin.get("/").get_data(as_text=True))     # el admin sí lo ve

    def test_admin_no_puede_borrarse_a_si_mismo_ni_quitarse_el_rol(self):
        admin = self.crear_admin()
        admin.post("/catalogos/usuario/1/eliminar")
        admin.post("/catalogos/usuario/1/editar", data={"nombre": "Admin Uno", "rol": "Técnico",
                                                        "usuario": "admin", "clave": ""})
        with self.app.app_context():
            fila = database.get_db().execute("SELECT rol FROM usuarios WHERE id = 1").fetchone()
        self.assertIsNotNone(fila)
        self.assertEqual(fila["rol"], "Administrador")

    def test_ya_no_se_puede_dejar_al_sistema_sin_administrador_con_acceso(self):
        admin = self.crear_admin()
        # un 2.º admin SIN contraseña no cuenta como administrador utilizable
        admin.post("/catalogos/usuario", data={"nombre": "Otro", "rol": "Administrador"})
        r = admin.post("/catalogos/usuario/1/editar", data={"nombre": "Admin Uno", "rol": "Administrador",
                                                            "usuario": "", "clave": ""})   # intenta quitarse el acceso
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            fila = database.get_db().execute("SELECT usuario FROM usuarios WHERE id = 1").fetchone()
        self.assertEqual(fila["usuario"], "admin")

    def test_sesion_deja_de_valer_si_borran_la_cuenta(self):
        admin = self.crear_admin()
        self.crear_tecnico(admin)
        tec, _ = self.entrar("tec")
        self.assertEqual(tec.get("/ordenes/").status_code, 200)
        admin.post("/catalogos/usuario/2/eliminar")
        self.assertEqual(tec.get("/ordenes/").status_code, 302)

    def test_cambio_de_rol_aplica_de_inmediato(self):
        admin = self.crear_admin()
        admin.post("/catalogos/usuario", data={"nombre": "Segundo", "rol": "Administrador",
                                               "usuario": "seg", "clave": CLAVE})
        seg, _ = self.entrar("seg")
        self.assertEqual(seg.get("/ajustes/").status_code, 200)
        admin.post("/catalogos/usuario/2/editar", data={"nombre": "Segundo", "rol": "Técnico",
                                                        "usuario": "seg", "clave": ""})
        self.assertEqual(seg.get("/ajustes/").status_code, 403)

    def test_borrar_datos_conserva_las_cuentas_del_equipo(self):
        admin = self.crear_admin()
        admin.post("/ajustes/borrar-datos", data={"confirmar": "BORRAR"})
        _, r = self.entrar("admin")
        self.assertEqual(r.status_code, 302)           # sigue pudiendo entrar


class PortalCliente(BaseLogin):
    def test_cliente_ve_solo_sus_ordenes(self):
        self.datos_con_admin()
        uno, r = self.entrar("uno", portal=True)
        self.assertEqual(r.status_code, 302)
        pagina = uno.get("/portal/").get_data(as_text=True)
        self.assertIn("Paciente DeUno", pagina)
        self.assertNotIn("Paciente DeDos", pagina)
        self.assertNotIn("380", pagina)                # sin precios

    def test_cliente_no_entra_al_panel_interno(self):
        self.datos_con_admin()
        uno, _ = self.entrar("uno", portal=True)
        for ruta in ("/", "/ordenes/", "/ordenes/1", "/inventario/", "/ajustes/", "/respaldo", "/catalogos/"):
            r = uno.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertIn("/portal/", r.headers["Location"], ruta)
        self.assertEqual(uno.post("/ordenes/1/avanzar").status_code, 302)
        with self.app.app_context():
            estado = database.get_db().execute("SELECT estado FROM ordenes WHERE id = 1").fetchone()[0]
        self.assertEqual(estado, "Recibida")           # la acción NO se ejecutó

    def test_personal_no_entra_al_portal_y_sin_sesion_tampoco(self):
        admin = self.datos_con_admin()
        r = admin.get("/portal/")
        self.assertIn("/portal/login", r.headers["Location"])
        r = self.cliente_http().get("/portal/")
        self.assertIn("/portal/login", r.headers["Location"])

    def test_credenciales_del_cliente_validadas(self):
        admin = self.crear_admin()
        corta = admin.post("/catalogos/odontologo", data={"nombre": "A", "usuario": "a", "clave": "corta"},
                           follow_redirects=True)
        self.assertIn("al menos", corta.get_data(as_text=True))
        sin_clave = admin.post("/catalogos/odontologo", data={"nombre": "B", "usuario": "b"}, follow_redirects=True)
        self.assertIn("escribe también una contraseña", sin_clave.get_data(as_text=True))
        admin.post("/catalogos/odontologo", data={"nombre": "C", "usuario": "c", "clave": CLAVE})
        repetido = admin.post("/catalogos/odontologo", data={"nombre": "D", "usuario": "C", "clave": CLAVE},
                              follow_redirects=True)
        self.assertIn("ya está en uso", repetido.get_data(as_text=True))
        with self.app.app_context():
            n = database.get_db().execute("SELECT COUNT(*) FROM odontologos").fetchone()[0]
        self.assertEqual(n, 1)

    def test_quitar_acceso_o_cambiar_clave_surte_efecto(self):
        admin = self.datos_con_admin()
        uno, _ = self.entrar("uno", portal=True)
        self.assertEqual(uno.get("/portal/").status_code, 200)
        admin.post("/catalogos/odontologo/1/editar", data={"nombre": "Dra. Uno", "clinica": "C", "telefono": "1",
                                                           "usuario": "uno", "clave": "otra-clave-999"})
        self.assertEqual(self.entrar("uno", CLAVE, portal=True)[1].status_code, 200)       # la vieja ya no sirve
        self.assertEqual(self.entrar("uno", "otra-clave-999", portal=True)[1].status_code, 302)
        admin.post("/catalogos/odontologo/1/editar", data={"nombre": "Dra. Uno", "clinica": "C", "telefono": "1",
                                                           "usuario": "", "clave": ""})     # sin acceso
        self.assertEqual(uno.get("/portal/").status_code, 302)                              # sesión abierta se cae
        self.assertEqual(self.entrar("uno", "otra-clave-999", portal=True)[1].status_code, 200)

    def test_editar_sin_clave_conserva_la_actual(self):
        admin = self.datos_con_admin()
        admin.post("/catalogos/odontologo/1/editar", data={"nombre": "Dra. Uno Editada", "clinica": "Nueva",
                                                           "telefono": "9", "usuario": "uno", "clave": ""})
        self.assertEqual(self.entrar("uno", CLAVE, portal=True)[1].status_code, 302)

    def test_bloqueo_de_intentos_en_el_portal(self):
        self.datos_con_admin()
        c = self.cliente_http()
        for _ in range(config.INTENTOS_MAX):
            c.post("/portal/login", data={"usuario": "uno", "clave": "mala-mala-1"})
        self.assertEqual(c.post("/portal/login", data={"usuario": "uno", "clave": CLAVE}).status_code, 429)


class ConsultaPublica(BaseLogin):
    def test_consulta_por_codigo_sigue_sin_login_pero_la_etiqueta_no(self):
        admin = self.datos_con_admin()
        from services import seguimiento as seg
        with self.app.app_context():
            codigo = seg.codigo(1)
        publico = self.cliente_http()
        self.assertEqual(publico.get("/seguimiento/").status_code, 200)
        self.assertEqual(publico.get(f"/seguimiento/{codigo}").status_code, 200)
        self.assertEqual(publico.get("/seguimiento/LD-0001-AAAAA").status_code, 404)
        r = publico.get("/seguimiento/etiqueta/1")                 # enumerable por número: ahora exige login
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(admin.get("/seguimiento/etiqueta/1").status_code, 200)

    def test_cabeceras_de_seguridad(self):
        r = self.cliente_http().get("/seguimiento/")
        self.assertEqual(r.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["Cache-Control"], "no-store")


class Migracion(BaseLogin):
    def test_base_antigua_sin_columnas_de_login_se_actualiza_sola(self):
        conn = database.conectar()
        if conn.postgres:       # simula una base anterior al login quitando las columnas nuevas
            conn.execute("ALTER TABLE usuarios DROP COLUMN usuario, DROP COLUMN clave_hash")
            conn.execute("ALTER TABLE odontologos DROP COLUMN usuario, DROP COLUMN clave_hash")
            conn.execute("INSERT INTO usuarios (nombre, rol) VALUES ('Vieja Cuenta', 'Administrador')")
            conn.execute("INSERT INTO odontologos (nombre) VALUES ('Dr. Antiguo')")
        else:
            conn.executescript("""
                DROP TABLE usuarios; DROP TABLE odontologos;
                CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, rol TEXT NOT NULL);
                CREATE TABLE odontologos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, telefono TEXT, clinica TEXT);
                INSERT INTO usuarios (nombre, rol) VALUES ('Vieja Cuenta', 'Administrador');
                INSERT INTO odontologos (nombre) VALUES ('Dr. Antiguo');
            """)
        conn.commit()
        conn.close()
        database.asegurar_ajustes()
        database.asegurar_ajustes()                    # idempotente: correrla dos veces no falla
        c = self.cliente_http()
        self.assertIn("/primer-acceso", c.get("/").headers["Location"])   # cuenta vieja no tiene clave -> pide crear admin
        c = self.crear_admin()
        self.assertEqual(c.get("/").status_code, 200)
        with self.app.app_context():
            nombres = [f[0] for f in database.get_db().execute("SELECT nombre FROM odontologos")]
        self.assertEqual(nombres, ["Dr. Antiguo"])     # datos viejos intactos


class FormatoPesos(unittest.TestCase):
    def test_formato_colombiano(self):
        from app import pesos
        self.assertEqual(pesos(380000), "$380.000")
        self.assertEqual(pesos(8200000), "$8.200.000")
        self.assertEqual(pesos(1234.6), "$1.235")
        self.assertEqual(pesos(0), "$0")
        self.assertEqual(pesos(None), "$0")
        self.assertEqual(pesos(-54000), "-$54.000")


if __name__ == "__main__":
    unittest.main()
