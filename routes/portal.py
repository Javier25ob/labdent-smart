"""Portal del CLIENTE (odontólogo): inicia sesión una vez y ve solo SUS órdenes,
en vez de tener que buscar el código de cada una por separado."""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from database import get_db
from services import acceso
from services import seguimiento as seg

bp = Blueprint("portal", __name__, url_prefix="/portal")

MSG_BLOQUEO = "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo."


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if acceso.bloqueado("cliente"):
            return render_template("portal_login.html", error=MSG_BLOQUEO), 429
        usuario = acceso.normalizar_usuario(request.form.get("usuario"))
        clave = request.form.get("clave", "")
        o = get_db().execute("SELECT * FROM odontologos WHERE usuario = ?", (usuario,)).fetchone()
        if acceso.clave_correcta(o["clave_hash"] if o else None, clave):
            acceso.limpiar_fallos("cliente")
            session.clear()
            session.permanent = True
            session["odontologo_id"] = o["id"]
            return redirect(acceso.destino_seguro(request.args.get("next"), url_for("portal.mis_ordenes")))
        acceso.registrar_fallo("cliente")
        error = "Usuario o contraseña incorrectos."
    return render_template("portal_login.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("portal.login"))


@bp.route("/")
def mis_ordenes():
    """Solo órdenes del odontólogo que inició sesión (app.py ya verificó que existe)."""
    cliente = g.cliente
    ordenes = [o for o in seg.ordenes_con_riesgo(get_db()) if o["odontologo_id"] == cliente["id"]]
    activas = [o for o in ordenes if o["estado"] != "Entregada"]
    return render_template("portal_ordenes.html", cliente=cliente, ordenes=ordenes, n_activas=len(activas))
