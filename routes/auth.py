"""Login del PERSONAL del laboratorio (panel interno: órdenes, inventario, catálogos, ajustes)."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

import config
from database import ErrorIntegridad, get_db, hay_administrador
from services import acceso

bp = Blueprint("auth", __name__)

MSG_BLOQUEO = f"Demasiados intentos fallidos. Espera {config.MINUTOS_BLOQUEO} minutos e inténtalo de nuevo."


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not hay_administrador():
        return redirect(url_for("auth.primer_acceso"))
    error = None
    if request.method == "POST":
        if acceso.bloqueado("staff"):
            return render_template("login.html", error=MSG_BLOQUEO), 429
        usuario = acceso.normalizar_usuario(request.form.get("usuario"))
        clave = request.form.get("clave", "")
        u = get_db().execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        if acceso.clave_correcta(u["clave_hash"] if u else None, clave):
            acceso.limpiar_fallos("staff")
            session.clear()
            session.permanent = True
            session["usuario_id"] = u["id"]
            return redirect(acceso.destino_seguro(request.args.get("next"), url_for("panel.dashboard")))
        acceso.registrar_fallo("staff")
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/primer-acceso", methods=["GET", "POST"])
def primer_acceso():
    """Pantalla de arranque: crea el primer administrador. Solo existe mientras no haya uno."""
    if hay_administrador():
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        f = request.form
        nombre, usuario = f.get("nombre", "").strip(), acceso.normalizar_usuario(f.get("usuario"))
        error = (("Escribe tu nombre y un usuario." if not nombre or not usuario else None)
                 or acceso.validar_clave(f.get("clave", ""))
                 or (None if f.get("clave") == f.get("clave2") else "Las dos contraseñas no coinciden."))
        if not error:
            db = get_db()
            try:
                nuevo_id = db.insertar("INSERT INTO usuarios (nombre, rol, usuario, clave_hash) VALUES (?, ?, ?, ?)",
                                       (nombre, config.ROL_ADMIN, usuario, acceso.hash_clave(f["clave"])))
                db.commit()
            except ErrorIntegridad:
                db.rollback()
                error = "Ese usuario ya existe. Elige otro."
            else:
                session.clear()
                session.permanent = True
                session["usuario_id"] = nuevo_id
                flash("Listo: tu cuenta de administrador está creada.", "success")
                return redirect(url_for("panel.dashboard"))
    return render_template("primer_acceso.html", error=error, min=config.CLAVE_MIN)
