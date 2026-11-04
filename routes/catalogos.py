"""SECCIÓN 8 - Registro de odontólogos, pacientes, servicios (con sus materiales) y usuarios."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

import config
from database import ErrorIntegridad, get_db, hay_administrador
from services import acceso

bp = Blueprint("catalogos", __name__, url_prefix="/catalogos")
TABLAS = {"usuario": "usuarios", "odontologo": "odontologos", "paciente": "pacientes", "servicio": "servicios"}
TABS = {"servicio": "servicios", "odontologo": "odontologos", "paciente": "pacientes", "usuario": "usuarios"}


def volver(tipo):
    return redirect(url_for("catalogos.lista", tab=TABS.get(tipo, "servicios")))


def _solo_admin_si_usuario(tipo):
    """Las cuentas del equipo (quién entra al panel y con qué rol) las gestiona solo un administrador."""
    if tipo == "usuario" and not acceso.es_admin():
        abort(403)


def _credenciales(db, tabla, registro_id, f):
    """Lee usuario y contraseña del formulario (para el login del equipo o del odontólogo).
    Devuelve (usuario, clave_hash, error).
      - sin usuario -> la persona queda SIN acceso (usuario y clave en None)
      - con usuario y sin clave nueva -> se conserva la clave que ya tenía
    """
    usuario = acceso.normalizar_usuario(f.get("usuario"))
    clave = f.get("clave", "")
    if not usuario:
        if clave:
            return None, None, "Escribiste una contraseña pero falta el usuario."
        return None, None, None
    if clave:
        error = acceso.validar_clave(clave)
        return usuario, (None if error else acceso.hash_clave(clave)), error
    actual = None
    if registro_id is not None:
        fila = db.execute(f"SELECT clave_hash FROM {tabla} WHERE id = ?", (registro_id,)).fetchone()
        actual = fila["clave_hash"] if fila else None
    if actual:
        return usuario, actual, None
    return usuario, None, "Para dar acceso escribe también una contraseña."


@bp.route("/")
def lista():
    db = get_db()
    tab = request.args.get("tab", "servicios")
    if tab == "usuarios" and not acceso.es_admin():
        tab = "servicios"
    servicios = [dict(s) for s in db.execute("SELECT * FROM servicios ORDER BY nombre")]
    recetas = db.execute("SELECT sm.servicio_id, sm.material_id, m.nombre, m.unidad, sm.cantidad "
                         "FROM servicio_materiales sm JOIN materiales m ON m.id = sm.material_id "
                         "ORDER BY m.nombre").fetchall()
    for s in servicios:
        s["receta"] = [r for r in recetas if r["servicio_id"] == s["id"]]
    # Nunca se envía clave_hash a la plantilla: solo si la persona tiene acceso y su usuario.
    usuarios = db.execute("SELECT id, nombre, rol, usuario FROM usuarios ORDER BY nombre").fetchall() \
        if acceso.es_admin() else []
    return render_template(
        "catalogos.html", tab=tab, servicios=servicios, usuarios=usuarios, roles=config.ROLES,
        min_clave=config.CLAVE_MIN,
        odontologos=db.execute("SELECT id, nombre, telefono, clinica, usuario, "
                               "(clave_hash IS NOT NULL) AS tiene_clave FROM odontologos ORDER BY nombre").fetchall(),
        pacientes=db.execute("SELECT p.*, o.nombre AS odontologo FROM pacientes p "
                             "LEFT JOIN odontologos o ON o.id = p.odontologo_id ORDER BY p.nombre").fetchall(),
        materiales=db.execute("SELECT * FROM materiales ORDER BY nombre").fetchall())


@bp.route("/receta", methods=["POST"])
def receta():
    db, f = get_db(), request.form
    db.execute("INSERT INTO servicio_materiales (servicio_id, material_id, cantidad) VALUES (?, ?, ?) "
               "ON CONFLICT (servicio_id, material_id) DO UPDATE SET cantidad = excluded.cantidad",
               (int(f["servicio_id"]), int(f["material_id"]), float(f["cantidad"])))
    db.commit()
    flash("Material agregado al servicio.", "success")
    return volver("servicio")


@bp.route("/receta/quitar", methods=["POST"])
def receta_quitar():
    db, f = get_db(), request.form
    db.execute("DELETE FROM servicio_materiales WHERE servicio_id = ? AND material_id = ?",
               (int(f["servicio_id"]), int(f["material_id"])))
    db.commit()
    return volver("servicio")


@bp.route("/<tipo>/<int:registro_id>/editar", methods=["POST"])
def editar(tipo, registro_id):
    if tipo not in TABLAS:
        return redirect(url_for("catalogos.lista"))
    _solo_admin_si_usuario(tipo)
    db, f = get_db(), request.form
    try:
        if tipo == "usuario":
            rol = f.get("rol")
            usuario, clave_hash, error = _credenciales(db, "usuarios", registro_id, f)
            if rol not in config.ROLES:
                error = "Rol no válido."
            if error:
                flash(error, "danger")
                return volver(tipo)
            db.execute("UPDATE usuarios SET nombre = ?, rol = ?, usuario = ?, clave_hash = ? WHERE id = ?",
                       (f["nombre"].strip(), rol, usuario, clave_hash, registro_id))
            if not hay_administrador():          # no te quedes sin nadie que pueda administrar
                db.rollback()
                flash("Tiene que quedar al menos un administrador con usuario y contraseña.", "danger")
                return volver(tipo)
        elif tipo == "odontologo":
            usuario, clave_hash, error = _credenciales(db, "odontologos", registro_id, f)
            if error:
                flash(error, "danger")
                return volver(tipo)
            db.execute("UPDATE odontologos SET nombre = ?, telefono = ?, clinica = ?, usuario = ?, "
                       "clave_hash = ? WHERE id = ?",
                       (f["nombre"].strip(), f.get("telefono", ""), f.get("clinica", ""),
                        usuario, clave_hash, registro_id))
        elif tipo == "paciente":
            db.execute("UPDATE pacientes SET nombre = ?, odontologo_id = ? WHERE id = ?",
                       (f["nombre"].strip(), int(f["odontologo_id"]), registro_id))
        elif tipo == "servicio":
            db.execute("UPDATE servicios SET nombre = ?, precio = ?, dias_estimados = ? WHERE id = ?",
                       (f["nombre"].strip(), float(f["precio"] or 0), int(f["dias"]), registro_id))
        db.commit()
        flash("Cambios guardados.", "success")
    except ErrorIntegridad:
        db.rollback()
        flash("Ese nombre de usuario ya está en uso. Elige otro.", "danger")
    return volver(tipo)


@bp.route("/<tipo>", methods=["POST"])
def agregar(tipo):
    if tipo not in TABLAS:
        return redirect(url_for("catalogos.lista"))
    _solo_admin_si_usuario(tipo)
    db, f = get_db(), request.form
    try:
        if tipo == "usuario":
            usuario, clave_hash, error = _credenciales(db, "usuarios", None, f)
            if f.get("rol") not in config.ROLES:
                error = "Rol no válido."
            if error:
                flash(error, "danger")
                return volver(tipo)
            db.execute("INSERT INTO usuarios (nombre, rol, usuario, clave_hash) VALUES (?, ?, ?, ?)",
                       (f["nombre"].strip(), f["rol"], usuario, clave_hash))
        elif tipo == "odontologo":
            usuario, clave_hash, error = _credenciales(db, "odontologos", None, f)
            if error:
                flash(error, "danger")
                return volver(tipo)
            db.execute("INSERT INTO odontologos (nombre, telefono, clinica, usuario, clave_hash) "
                       "VALUES (?, ?, ?, ?, ?)",
                       (f["nombre"].strip(), f.get("telefono", ""), f.get("clinica", ""), usuario, clave_hash))
        elif tipo == "paciente":
            db.execute("INSERT INTO pacientes (nombre, odontologo_id) VALUES (?, ?)",
                       (f["nombre"].strip(), int(f["odontologo_id"])))
        elif tipo == "servicio":
            db.execute("INSERT INTO servicios (nombre, precio, dias_estimados) VALUES (?, ?, ?)",
                       (f["nombre"].strip(), float(f["precio"] or 0), int(f["dias"])))
        db.commit()
        flash("Guardado correctamente.", "success")
    except ErrorIntegridad:
        db.rollback()
        flash("Ese nombre de usuario ya está en uso. Elige otro.", "danger")
    return volver(tipo)


@bp.route("/<tipo>/<int:registro_id>/eliminar", methods=["POST"])
def eliminar(tipo, registro_id):
    db = get_db()
    if tipo not in TABLAS:
        return redirect(url_for("catalogos.lista"))
    _solo_admin_si_usuario(tipo)
    if tipo == "usuario" and registro_id == g.usuario["id"]:
        flash("No puedes eliminar tu propia cuenta mientras la estás usando.", "danger")
        return volver(tipo)
    try:
        if tipo == "servicio":
            db.execute("DELETE FROM servicio_materiales WHERE servicio_id = ?", (registro_id,))
        db.execute(f"DELETE FROM {TABLAS[tipo]} WHERE id = ?", (registro_id,))
        if tipo == "usuario" and not hay_administrador():
            db.rollback()
            flash("Tiene que quedar al menos un administrador con usuario y contraseña.", "danger")
            return volver(tipo)
        db.commit()
        flash("Eliminado.", "success")
    except ErrorIntegridad:
        db.rollback()
        flash("No se puede eliminar: ya tiene órdenes u otros registros asociados.", "danger")
    return volver(tipo)
