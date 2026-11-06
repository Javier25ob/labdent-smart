"""SECCIÓN 6 - Rutas de ÓRDENES DE TRABAJO."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from config import ESTADOS
from database import get_db
from routes.seguimiento import url_orden
from services import ordenes as svc
from services import pacientes as pac_svc
from services import seguimiento as seg

bp = Blueprint("ordenes", __name__, url_prefix="/ordenes")


@bp.route("/")
def lista():
    db = get_db()
    estado = request.args.get("estado")
    return render_template("ordenes.html", ordenes=seg.ordenes_con_riesgo(db, estado),
                           estados=ESTADOS, filtro=estado)


@bp.route("/nueva", methods=["GET", "POST"])
def nueva():
    db = get_db()
    if request.method == "POST":
        f = request.form
        odontologo_id = int(f["odontologo_id"])
        if f["paciente_id"] == "nuevo":      # paciente nuevo escrito en el mismo formulario
            datos, error = pac_svc.leer(f, prefijo="paciente_")
            if not error:
                paciente_id, error = pac_svc.crear(db, odontologo_id, datos)
            if error:
                db.rollback()
                flash(error, "danger")
                return redirect(url_for("ordenes.nueva"))
            db.commit()
        else:
            paciente_id = int(f["paciente_id"])
        oid = svc.crear_orden(db, odontologo_id, paciente_id, int(f["servicio_id"]), f.get("observaciones", ""))
        flash(f"Orden #{oid} creada. Ya puedes imprimir su etiqueta con QR.", "success")
        return redirect(url_for("ordenes.detalle", orden_id=oid))
    return render_template(
        "orden_nueva.html",
        odontologos=db.execute("SELECT * FROM odontologos ORDER BY nombre").fetchall(),
        pacientes_js=[{"id": p["id"], "nombre": p["nombre"], "od": p["odontologo_id"],
                       "doc": pac_svc.etiqueta_documento(p)}
                      for p in db.execute("SELECT * FROM pacientes ORDER BY nombre")],
        servicios=db.execute("SELECT * FROM servicios ORDER BY nombre").fetchall())


@bp.route("/<int:orden_id>")
def detalle(orden_id):
    db = get_db()
    orden = svc.obtener(db, orden_id)
    if orden is None:
        abort(404)
    historial = db.execute("SELECT * FROM historial_estados WHERE orden_id = ? ORDER BY id",
                           (orden_id,)).fetchall()
    nivel, motivo = seg.riesgo(db, orden)
    return render_template("orden_detalle.html", o=orden, historial=historial,
                           codigo=seg.codigo(orden_id), riesgo=nivel, riesgo_motivo=motivo,
                           url_publica=url_orden(orden_id),
                           materiales=svc.materiales_requeridos(db, orden["servicio_id"]),
                           siguiente=svc.siguiente_estado(orden["estado"]))


@bp.route("/<int:orden_id>/avanzar", methods=["POST"])
def avanzar(orden_id):
    ok, msg = svc.avanzar_estado(get_db(), orden_id)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("ordenes.detalle", orden_id=orden_id))
