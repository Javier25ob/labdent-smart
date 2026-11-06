"""SECCIÓN 6B - Bandeja de SOLICITUDES (panel del laboratorio).
Lo que los odontólogos piden desde su portal llega aquí; el personal la acepta
(se crea la orden con su QR) o la rechaza con un motivo."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import get_db
from services import ordenes as ord_svc
from services import solicitudes as sol

bp = Blueprint("solicitudes", __name__, url_prefix="/solicitudes")


@bp.route("/")
def lista():
    db = get_db()
    pendientes = [dict(s) for s in sol.pendientes(db)]
    for s in pendientes:   # avisar ANTES de aceptar si falta material para ese servicio
        s["faltan"] = [m["nombre"] for m in ord_svc.materiales_requeridos(db, s["servicio_id"])
                       if m["stock"] < m["cantidad"]]
    return render_template("solicitudes.html", pendientes=pendientes, recientes=sol.recientes(db))


@bp.route("/<int:solicitud_id>/aceptar", methods=["POST"])
def aceptar(solicitud_id):
    orden_id, error = sol.aceptar(get_db(), solicitud_id)
    if error:
        flash(error, "danger")
        return redirect(url_for("solicitudes.lista"))
    flash(f"Solicitud aceptada: se creó la orden #{orden_id}. Ya puedes imprimir su etiqueta con QR.", "success")
    return redirect(url_for("ordenes.detalle", orden_id=orden_id))


@bp.route("/<int:solicitud_id>/rechazar", methods=["POST"])
def rechazar(solicitud_id):
    ok, msg = sol.rechazar(get_db(), solicitud_id, request.form.get("motivo"))
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("solicitudes.lista"))
