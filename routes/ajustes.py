"""Ajustes del laboratorio: nombre, WhatsApp, dirección pública y reinicio de datos."""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import borrar_todos_los_datos, get_ajuste, set_ajuste

bp = Blueprint("ajustes", __name__, url_prefix="/ajustes")


@bp.route("/", methods=["GET", "POST"])
def ver():
    if request.method == "POST":
        numero = re.sub(r"\D", "", request.form.get("whatsapp", ""))   # solo dígitos
        set_ajuste("lab_nombre", request.form.get("nombre", "").strip())
        set_ajuste("lab_whatsapp", numero)
        set_ajuste("url_publica", request.form.get("url_publica", "").strip())
        flash("Ajustes guardados.", "success")
        return redirect(url_for("ajustes.ver"))
    return render_template("ajustes.html", nombre=get_ajuste("lab_nombre"),
                           whatsapp=get_ajuste("lab_whatsapp"), url_publica=get_ajuste("url_publica"))


@bp.route("/borrar-datos", methods=["POST"])
def borrar():
    if request.form.get("confirmar", "").strip().upper() != "BORRAR":
        flash("No se borró nada: debes escribir la palabra BORRAR.", "danger")
    else:
        borrar_todos_los_datos()
        flash("Listo: el sistema quedó completamente vacío.", "success")
    return redirect(url_for("ajustes.ver"))
