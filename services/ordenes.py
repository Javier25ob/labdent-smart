"""SECCIÓN 3 - Lógica de ÓRDENES DE TRABAJO.
Crear órdenes, cambiar estados y descontar materiales automáticamente."""
from datetime import datetime, timedelta

from config import ESTADOS, ESTADO_CONSUMO
from services import inventario


def crear_orden(db, odontologo_id, paciente_id, servicio_id, observaciones=""):
    servicio = db.execute("SELECT * FROM servicios WHERE id = ?", (servicio_id,)).fetchone()
    hoy = datetime.now()
    entrega = hoy + timedelta(days=servicio["dias_estimados"])
    orden_id = db.insertar(
        "INSERT INTO ordenes (odontologo_id, paciente_id, servicio_id, estado, fecha_ingreso, "
        "fecha_entrega_estimada, observaciones) VALUES (?, ?, ?, 'Recibida', ?, ?, ?)",
        (odontologo_id, paciente_id, servicio_id,
         hoy.strftime("%Y-%m-%d %H:%M:%S"), entrega.strftime("%Y-%m-%d"), observaciones),
    )
    db.execute("INSERT INTO historial_estados (orden_id, estado, fecha) VALUES (?, 'Recibida', ?)",
               (orden_id, inventario.ahora()))
    db.commit()
    return orden_id


def materiales_requeridos(db, servicio_id):
    return db.execute(
        "SELECT m.id, m.nombre, m.unidad, m.stock, sm.cantidad "
        "FROM servicio_materiales sm JOIN materiales m ON m.id = sm.material_id "
        "WHERE sm.servicio_id = ?", (servicio_id,)
    ).fetchall()


def siguiente_estado(estado):
    i = ESTADOS.index(estado)
    return ESTADOS[i + 1] if i + 1 < len(ESTADOS) else None


def avanzar_estado(db, orden_id):
    """Pasa la orden al siguiente estado. Devuelve (ok, mensaje)."""
    orden = db.execute("SELECT * FROM ordenes WHERE id = ?", (orden_id,)).fetchone()
    if orden is None:
        return False, "Esa orden no existe."
    nuevo = siguiente_estado(orden["estado"])
    if nuevo is None:
        return False, "La orden ya fue entregada."

    # Al entrar a producción se descuentan los materiales (una sola vez)
    if nuevo == ESTADO_CONSUMO and not orden["consumo_registrado"]:
        requeridos = materiales_requeridos(db, orden["servicio_id"])
        faltantes = [r["nombre"] for r in requeridos if r["stock"] < r["cantidad"]]
        if faltantes:
            return False, "Stock insuficiente de: " + ", ".join(faltantes)
        for r in requeridos:
            inventario.registrar_salida(db, r["id"], r["cantidad"], orden_id,
                                        nota=f"Consumo orden #{orden_id}")
        db.execute("UPDATE ordenes SET consumo_registrado = 1 WHERE id = ?", (orden_id,))

    if nuevo == "Entregada":
        db.execute("UPDATE ordenes SET fecha_entrega_real = ? WHERE id = ?",
                   (datetime.now().strftime("%Y-%m-%d"), orden_id))

    db.execute("UPDATE ordenes SET estado = ? WHERE id = ?", (nuevo, orden_id))
    db.execute("INSERT INTO historial_estados (orden_id, estado, fecha) VALUES (?, ?, ?)",
               (orden_id, nuevo, inventario.ahora()))
    db.commit()
    return True, f"Orden #{orden_id} ahora está: {nuevo}"


CONSULTA_ORDENES = """
SELECT o.*, od.nombre AS odontologo, p.nombre AS paciente, s.nombre AS servicio,
       p.tipo_documento AS paciente_tipo_doc, p.documento AS paciente_documento, p.telefono AS paciente_telefono
FROM ordenes o
JOIN odontologos od ON od.id = o.odontologo_id
JOIN pacientes p ON p.id = o.paciente_id
JOIN servicios s ON s.id = o.servicio_id
"""


def listar(db, estado=None):
    if estado:
        return db.execute(CONSULTA_ORDENES + " WHERE o.estado = ? ORDER BY o.id DESC", (estado,)).fetchall()
    return db.execute(CONSULTA_ORDENES + " ORDER BY o.id DESC").fetchall()


def obtener(db, orden_id):
    return db.execute(CONSULTA_ORDENES + " WHERE o.id = ?", (orden_id,)).fetchone()
