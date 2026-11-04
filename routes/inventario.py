"""SECCIÓN 7 - Rutas de INVENTARIO."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import ErrorIntegridad, get_db
from services import inventario as svc

bp = Blueprint("inventario", __name__, url_prefix="/inventario")


@bp.route("/")
def lista():
    db = get_db()
    materiales = db.execute("SELECT * FROM materiales ORDER BY nombre").fetchall()
    movimientos = db.execute(
        "SELECT mv.*, m.nombre FROM movimientos_inventario mv "
        "JOIN materiales m ON m.id = mv.material_id ORDER BY mv.id DESC LIMIT 15").fetchall()
    return render_template("inventario.html", materiales=materiales, movimientos=movimientos)


@bp.route("/material", methods=["POST"])
def nuevo_material():
    db, f = get_db(), request.form
    material_id = db.insertar("INSERT INTO materiales (nombre, unidad, stock, stock_minimo, costo_unitario) "
                     "VALUES (?, ?, 0, ?, ?)",
                     (f["nombre"].strip(), f["unidad"], float(f["stock_minimo"] or 0), float(f["costo"] or 0)))
    inicial = float(f.get("stock") or 0)
    if inicial > 0:
        svc.registrar_entrada(db, material_id, inicial, "Stock inicial")
    db.commit()
    flash("Material agregado.", "success")
    return redirect(url_for("inventario.lista"))


@bp.route("/material/<int:material_id>/editar", methods=["POST"])
def editar_material(material_id):
    db, f = get_db(), request.form
    db.execute("UPDATE materiales SET nombre = ?, unidad = ?, stock_minimo = ?, costo_unitario = ? WHERE id = ?",
               (f["nombre"].strip(), f["unidad"], float(f["stock_minimo"] or 0), float(f["costo"] or 0), material_id))
    db.commit()
    flash("Material actualizado.", "success")
    return redirect(url_for("inventario.lista"))


@bp.route("/entrada", methods=["POST"])
def entrada():
    db = get_db()
    svc.registrar_entrada(db, int(request.form["material_id"]), float(request.form["cantidad"]),
                          request.form.get("nota") or "Compra")
    db.commit()
    flash("Compra registrada: el stock se actualizó.", "success")
    return redirect(url_for("inventario.lista"))


@bp.route("/material/<int:material_id>/eliminar", methods=["POST"])
def eliminar(material_id):
    db = get_db()
    try:
        db.execute("DELETE FROM servicio_materiales WHERE material_id = ?", (material_id,))
        db.execute("DELETE FROM materiales WHERE id = ?", (material_id,))
        db.commit()
        flash("Material eliminado.", "success")
    except ErrorIntegridad:
        db.rollback()
        flash("No se puede eliminar: ya tiene movimientos registrados.", "danger")
    return redirect(url_for("inventario.lista"))
