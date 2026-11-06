"""SECCIÓN 9 - Punto de entrada. Ejecuta:  python app.py"""
from datetime import timedelta

from flask import Flask, abort, g, redirect, request, session, url_for

import config
import database
from database import asegurar_ajustes, close_db, get_ajuste, get_db, hay_administrador, init_db
from routes import ajustes, auth, catalogos, inventario, ordenes, panel, portal, seguimiento, solicitudes
from services import acceso
from services import seguimiento as seg_svc
from services import pacientes as pac_svc
from services import solicitudes as sol_svc

# Páginas que se pueden abrir SIN iniciar sesión:
#  - los dos formularios de login y la creación del primer administrador
#  - la consulta pública por código/QR (a propósito: la clínica escanea y ve el avance)
# OJO: la etiqueta imprimible (seguimiento.etiqueta) NO es pública: muestra el código de
# cualquier orden por su número, así que solo la ve el personal.
RUTAS_PUBLICAS = {
    "auth.login", "auth.logout", "auth.primer_acceso",
    "portal.login", "portal.logout",
    "seguimiento.buscar", "seguimiento.publica",
    "static",
}
# Solo el rol Administrador (Técnico y Recepción reciben "403 Prohibido").
PREFIJOS_SOLO_ADMIN = ("ajustes.",)
ENDPOINTS_SOLO_ADMIN = {"panel.respaldo"}


def pesos(valor):
    """Formato colombiano: 380000 -> $380.000 (punto para los miles, sin decimales)."""
    try:
        n = round(float(valor or 0))
    except (TypeError, ValueError):
        n = 0
    texto = f"{abs(n):,}".replace(",", ".")
    return f"-${texto}" if n < 0 else f"${texto}"


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",          # el navegador no envía la sesión en formularios de otros sitios
        SESSION_COOKIE_SECURE=config.SOLO_HTTPS,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=config.HORAS_SESION),
    )
    app.teardown_appcontext(close_db)
    for modulo in (panel, ordenes, solicitudes, inventario, catalogos, seguimiento, ajustes, auth, portal):
        app.register_blueprint(modulo.bp)
    app.jinja_env.filters["fecha_larga"] = seg_svc.fecha_larga
    app.jinja_env.filters["pesos"] = pesos

    @app.before_request
    def controlar_acceso():
        ep = request.endpoint or ""
        if ep == "static":              # archivos CSS/JS: no hace falta abrir la base de datos
            return None
        db = get_db()
        # Quién es: siempre se consulta en la base (si borras o desactivas una cuenta,
        # su sesión deja de valer en el acto).
        g.usuario = g.cliente = None
        if session.get("usuario_id"):
            g.usuario = db.execute(
                "SELECT id, nombre, rol FROM usuarios WHERE id = ? AND usuario IS NOT NULL "
                "AND clave_hash IS NOT NULL", (session["usuario_id"],)).fetchone()
        if session.get("odontologo_id"):
            g.cliente = db.execute(
                "SELECT id, nombre, clinica FROM odontologos WHERE id = ? AND usuario IS NOT NULL "
                "AND clave_hash IS NOT NULL", (session["odontologo_id"],)).fetchone()
        if (session.get("usuario_id") and not g.usuario) or (session.get("odontologo_id") and not g.cliente):
            session.clear()

        if ep in RUTAS_PUBLICAS:
            return None

        volver = request.path if request.method == "GET" else None   # a dónde regresar tras entrar

        # Zona del CLIENTE (odontólogo)
        if ep.startswith("portal."):
            if not g.cliente:
                return redirect(url_for("portal.login", next=volver))
            return None

        # Zona del PERSONAL del laboratorio
        if not hay_administrador():
            return redirect(url_for("auth.primer_acceso"))
        if g.cliente:                      # un cliente no puede entrar al panel interno
            return redirect(url_for("portal.mis_ordenes"))
        if not g.usuario:
            return redirect(url_for("auth.login", next=volver))
        if (ep in ENDPOINTS_SOLO_ADMIN or ep.startswith(PREFIJOS_SOLO_ADMIN)) and not acceso.es_admin():
            abort(403)
        return None

    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint != "static":
            # Con sesión iniciada, que el botón "atrás" no muestre páginas privadas guardadas.
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.errorhandler(403)
    def prohibido(_):
        return ("<h1>403 · Sin permiso</h1><p>Esta sección es solo para administradores.</p>"
                "<p><a href='/'>Volver al panel</a></p>"), 403

    @app.context_processor
    def datos_para_plantillas():
        usuario, cliente = g.get("usuario"), g.get("cliente")
        return {"lab_nombre": get_ajuste("lab_nombre", config.LAB_NOMBRE),
                "lab_whatsapp": get_ajuste("lab_whatsapp", ""),
                "usuario": usuario, "cliente": cliente,
                "es_admin": acceso.es_admin(),
                "tipos_documento": pac_svc.TIPOS_DOCUMENTO,
                # contador del menú «Solicitudes» (solo lo ve el personal del laboratorio)
                "n_solicitudes": sol_svc.contar_pendientes(get_db()) if usuario else 0}
    return app


if __name__ == "__main__":
    if not database.usa_postgres() and not database.DB_PATH.exists():
        init_db()
        print("Base de datos nueva y vacía creada.")
    asegurar_ajustes()
    print("Base de datos:", "PostgreSQL / Supabase (DATABASE_URL)" if database.usa_postgres() else "SQLite local (labdent_datos.db)")
    print("Abre http://127.0.0.1:5000 en tu navegador "
          "(la primera vez te pedirá crear tu cuenta de administrador).")
    create_app().run(debug=True)
