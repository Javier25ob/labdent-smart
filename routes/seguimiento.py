"""SECCIÓN 6B - Portal público del odontólogo (seguimiento por QR) y etiqueta imprimible."""
from flask import Blueprint, abort, redirect, render_template, request, url_for

from config import ESTADOS
from database import get_ajuste, get_db
from services import ordenes as svc
from services import seguimiento as seg

bp = Blueprint("seguimiento", __name__, url_prefix="/seguimiento")


def url_orden(orden_id):
    ruta = url_for("seguimiento.publica", codigo=seg.codigo(orden_id))
    base = get_ajuste("url_publica").rstrip("/") or request.url_root.rstrip("/")
    return base + ruta


@bp.route("/", methods=["GET", "POST"])
def buscar():
    error = None
    if request.method == "POST":
        cod = request.form.get("codigo", "")
        if seg.resolver(cod):
            return redirect(url_for("seguimiento.publica", codigo=cod.strip().upper()))
        error = "No encontramos ese código. Revisa la etiqueta de la caja."
    return render_template("seguimiento_buscar.html", error=error)


@bp.route("/<codigo>")
def publica(codigo):
    oid = seg.resolver(codigo)
    if oid is None:
        abort(404)
    db = get_db()
    o = svc.obtener(db, oid)
    if o is None:
        abort(404)
    historial = {h["estado"]: h["fecha"] for h in
                 db.execute("SELECT * FROM historial_estados WHERE orden_id = ? ORDER BY id", (oid,))}
    clinica = db.execute("SELECT clinica FROM odontologos WHERE id = ?", (o["odontologo_id"],)).fetchone()[0]
    nivel, _ = seg.riesgo(db, o)
    return render_template("seguimiento.html", o=o, codigo=seg.codigo(oid), estados=ESTADOS,
                           historial=historial, clinica=clinica, iniciales=seg.iniciales(o["paciente"]),
                           actual=ESTADOS.index(o["estado"]), dias=seg.dias_para_entrega(o), nivel=nivel)


@bp.route("/etiqueta/<int:orden_id>")
def etiqueta(orden_id):
    db = get_db()
    o = svc.obtener(db, orden_id)
    if o is None:
        abort(404)
    return render_template("etiqueta.html", o=o, codigo=seg.codigo(orden_id), url=url_orden(orden_id))
