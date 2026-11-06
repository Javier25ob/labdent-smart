"""Portal del CLIENTE (odontólogo).

Más que una consulta y menos que el panel del laboratorio. El odontólogo puede:
  * ver sus órdenes activas y el detalle de cada una con su línea de tiempo,
  * SOLICITAR trabajos (quedan pendientes hasta que el laboratorio los acepte),
  * registrar y editar SUS pacientes,
  * ver su historial (entregadas y solicitudes respondidas) y cancelar lo pendiente,
  * editar su perfil y cambiar su contraseña.
No ve inventario, costos internos, simulación ni datos de otros odontólogos.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

import config
from config import ESTADOS
from database import ErrorIntegridad, get_db
from services import acceso
from services import ordenes as ord_svc
from services import seguimiento as seg
from services import solicitudes as sol

bp = Blueprint("portal", __name__, url_prefix="/portal")

MSG_BLOQUEO = "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo."


# ---------------------------------------------------------------------------
# Entrar / salir
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Ayudas (todas filtran por el odontólogo que inició sesión: app.py ya verificó que existe)
# ---------------------------------------------------------------------------
def _mis_ordenes(db):
    return [o for o in seg.ordenes_con_riesgo(db) if o["odontologo_id"] == g.cliente["id"]]


def _mis_pacientes(db):
    return db.execute(
        "SELECT p.id, p.nombre, "
        "(SELECT COUNT(*) FROM ordenes o WHERE o.paciente_id = p.id) AS n_ordenes, "
        "(SELECT COUNT(*) FROM solicitudes s WHERE s.paciente_id = p.id) AS n_solicitudes "
        "FROM pacientes p WHERE p.odontologo_id = ? ORDER BY p.nombre", (g.cliente["id"],)).fetchall()


def _mi_paciente(db, paciente_id):
    return db.execute("SELECT * FROM pacientes WHERE id = ? AND odontologo_id = ?",
                      (paciente_id, g.cliente["id"])).fetchone()


def _contadores(db):
    """Números que se muestran en las pestañas del portal."""
    return {"pendientes": len(sol.de_cliente(db, g.cliente["id"], [sol.PENDIENTE]))}


def _vista(plantilla, activa, **datos):
    db = get_db()
    return render_template(plantilla, activa=activa, cont=_contadores(db), **datos)


# ---------------------------------------------------------------------------
# Inicio: órdenes activas + solicitudes pendientes
# ---------------------------------------------------------------------------
@bp.route("/")
def mis_ordenes():
    db = get_db()
    ordenes = _mis_ordenes(db)
    activas = [o for o in ordenes if o["estado"] != "Entregada"]
    pendientes = sol.de_cliente(db, g.cliente["id"], [sol.PENDIENTE])
    resumen = {
        "activas": len(activas),
        "atrasadas": sum(1 for o in activas if o["dias"] < 0),
        "pendientes": len(pendientes),
        "entregadas": len(ordenes) - len(activas),
    }
    return _vista("portal_inicio.html", "inicio", activas=activas, pendientes=pendientes,
                  resumen=resumen, hay_algo=bool(ordenes or pendientes))


# ---------------------------------------------------------------------------
# Detalle de una orden con su línea de tiempo
# ---------------------------------------------------------------------------
@bp.route("/orden/<int:orden_id>")
def orden(orden_id):
    db = get_db()
    o = ord_svc.obtener(db, orden_id)
    if o is None or o["odontologo_id"] != g.cliente["id"]:     # orden ajena = como si no existiera
        abort(404)
    historial = db.execute("SELECT estado, fecha FROM historial_estados WHERE orden_id = ? ORDER BY id",
                           (orden_id,)).fetchall()
    fechas = {h["estado"]: h["fecha"] for h in historial}
    solicitud = db.execute("SELECT fecha_solicitud FROM solicitudes WHERE orden_id = ?", (orden_id,)).fetchone()
    return _vista("portal_orden.html", "inicio", o=o, codigo=seg.codigo(orden_id), estados=ESTADOS,
                  actual=ESTADOS.index(o["estado"]), fechas=fechas, historial=historial,
                  dias=seg.dias_para_entrega(o), solicitud=solicitud)


# ---------------------------------------------------------------------------
# Solicitar un trabajo
# ---------------------------------------------------------------------------
@bp.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    db = get_db()
    servicios = db.execute("SELECT id, nombre, precio, dias_estimados FROM servicios ORDER BY nombre").fetchall()
    if request.method == "POST":
        f = request.form
        try:
            servicio_id = int(f.get("servicio_id", ""))
        except ValueError:
            servicio_id = None
        paciente_id = None
        if f.get("paciente_id") == "nuevo":
            nombre = f.get("paciente_nuevo", "").strip()
            if not nombre:
                flash("Escribe el nombre del paciente nuevo.", "danger")
                return _vista("portal_solicitar.html", "solicitar", servicios=servicios,
                              pacientes=_mis_pacientes(db), f=f)
            paciente_id = db.insertar("INSERT INTO pacientes (nombre, odontologo_id) VALUES (?, ?)",
                                      (nombre[:120], g.cliente["id"]))
        else:
            try:
                paciente_id = int(f.get("paciente_id", ""))
            except ValueError:
                paciente_id = None
        sid, error = sol.crear(db, g.cliente["id"], paciente_id, servicio_id, f.get("observaciones", ""))
        if error:
            db.rollback()
            flash(error, "danger")
            return _vista("portal_solicitar.html", "solicitar", servicios=servicios,
                          pacientes=_mis_pacientes(db), f=f)
        flash(f"Solicitud #{sid} enviada. Te avisamos aquí cuando el laboratorio la acepte.", "success")
        return redirect(url_for("portal.mis_ordenes"))
    return _vista("portal_solicitar.html", "solicitar", servicios=servicios, pacientes=_mis_pacientes(db),
                  f={"paciente_id": request.args.get("paciente", "")})


@bp.route("/solicitudes/<int:solicitud_id>/cancelar", methods=["POST"])
def cancelar_solicitud(solicitud_id):
    ok, msg = sol.cancelar(get_db(), solicitud_id, g.cliente["id"])
    flash(msg, "success" if ok else "danger")
    destino = "portal.historial" if request.form.get("volver") == "historial" else "portal.mis_ordenes"
    return redirect(url_for(destino))


# ---------------------------------------------------------------------------
# Mis pacientes
# ---------------------------------------------------------------------------
@bp.route("/pacientes", methods=["GET", "POST"])
def pacientes():
    db = get_db()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("Escribe el nombre del paciente.", "danger")
        else:
            db.insertar("INSERT INTO pacientes (nombre, odontologo_id) VALUES (?, ?)", (nombre[:120], g.cliente["id"]))
            db.commit()
            flash(f"Paciente «{nombre}» registrado.", "success")
        return redirect(url_for("portal.pacientes"))
    return _vista("portal_pacientes.html", "pacientes", pacientes=_mis_pacientes(db))


@bp.route("/pacientes/<int:paciente_id>/editar", methods=["POST"])
def editar_paciente(paciente_id):
    db = get_db()
    if _mi_paciente(db, paciente_id) is None:
        abort(404)
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("El nombre no puede quedar vacío.", "danger")
    else:
        db.execute("UPDATE pacientes SET nombre = ? WHERE id = ? AND odontologo_id = ?",
                   (nombre[:120], paciente_id, g.cliente["id"]))
        db.commit()
        flash("Paciente actualizado.", "success")
    return redirect(url_for("portal.pacientes"))


@bp.route("/pacientes/<int:paciente_id>/eliminar", methods=["POST"])
def eliminar_paciente(paciente_id):
    db = get_db()
    if _mi_paciente(db, paciente_id) is None:
        abort(404)
    try:
        db.execute("DELETE FROM pacientes WHERE id = ? AND odontologo_id = ?", (paciente_id, g.cliente["id"]))
        db.commit()
        flash("Paciente eliminado.", "success")
    except ErrorIntegridad:
        db.rollback()
        flash("No se puede eliminar: ese paciente ya tiene órdenes o solicitudes.", "danger")
    return redirect(url_for("portal.pacientes"))


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------
@bp.route("/historial")
def historial():
    db = get_db()
    entregadas = [o for o in _mis_ordenes(db) if o["estado"] == "Entregada"]
    entregadas.sort(key=lambda o: o["fecha_entrega_real"] or "", reverse=True)
    solicitudes = sol.de_cliente(db, g.cliente["id"])
    a_tiempo = sum(1 for o in entregadas if o["fecha_entrega_real"] and o["fecha_entrega_real"] <= o["fecha_entrega_estimada"])
    return _vista("portal_historial.html", "historial", entregadas=entregadas, solicitudes=solicitudes,
                  a_tiempo=a_tiempo)


# ---------------------------------------------------------------------------
# Mi perfil
# ---------------------------------------------------------------------------
@bp.route("/perfil", methods=["GET", "POST"])
def perfil():
    db = get_db()
    yo = db.execute("SELECT id, nombre, telefono, clinica, usuario, clave_hash FROM odontologos WHERE id = ?",
                    (g.cliente["id"],)).fetchone()
    if request.method == "POST":
        f = request.form
        if f.get("accion") == "clave":
            error = None
            if not acceso.clave_correcta(yo["clave_hash"], f.get("actual", "")):
                error = "Tu contraseña actual no es correcta."
            error = error or acceso.validar_clave(f.get("nueva", ""))
            if not error and f.get("nueva") != f.get("nueva2"):
                error = "Las dos contraseñas nuevas no coinciden."
            if error:
                flash(error, "danger")
            else:
                db.execute("UPDATE odontologos SET clave_hash = ? WHERE id = ?",
                           (acceso.hash_clave(f["nueva"]), yo["id"]))
                db.commit()
                flash("Contraseña cambiada.", "success")
        else:
            nombre = f.get("nombre", "").strip()
            if not nombre:
                flash("Tu nombre no puede quedar vacío.", "danger")
            else:
                db.execute("UPDATE odontologos SET nombre = ?, telefono = ?, clinica = ? WHERE id = ?",
                           (nombre[:120], f.get("telefono", "").strip()[:30], f.get("clinica", "").strip()[:120],
                            yo["id"]))
                db.commit()
                flash("Datos actualizados.", "success")
        return redirect(url_for("portal.perfil"))
    return _vista("portal_perfil.html", "perfil", yo=yo, min_clave=config.CLAVE_MIN)
