"""SECCIÓN 3B - SOLICITUDES DE TRABAJO desde el portal del odontólogo.

El odontólogo pide un trabajo; la solicitud queda «Pendiente» hasta que el laboratorio:
  * la ACEPTA  -> se crea la orden de verdad (con su QR, materiales y fechas), o
  * la RECHAZA -> con un motivo que el odontólogo ve en su historial.
Mientras siga pendiente, el odontólogo la puede CANCELAR.

Así el cliente puede pedir trabajos sin tocar el inventario ni la producción: eso sigue
siendo decisión del laboratorio.
"""
from services import inventario
from services import ordenes as ord_svc

PENDIENTE, ACEPTADA, RECHAZADA, CANCELADA = "Pendiente", "Aceptada", "Rechazada", "Cancelada"

CONSULTA = """
SELECT s.*, od.nombre AS odontologo, od.clinica, p.nombre AS paciente,
       sv.nombre AS servicio, sv.precio, sv.dias_estimados
FROM solicitudes s
JOIN odontologos od ON od.id = s.odontologo_id
JOIN pacientes p ON p.id = s.paciente_id
JOIN servicios sv ON sv.id = s.servicio_id
"""


def crear(db, odontologo_id, paciente_id, servicio_id, observaciones=""):
    """Crea la solicitud. Devuelve (id, None) o (None, mensaje de error).
    Verifica que el paciente sea DEL odontólogo y que el servicio exista."""
    paciente = db.execute("SELECT id FROM pacientes WHERE id = ? AND odontologo_id = ?",
                          (paciente_id, odontologo_id)).fetchone()
    if paciente is None:
        return None, "Elige uno de tus pacientes."
    if db.execute("SELECT id FROM servicios WHERE id = ?", (servicio_id,)).fetchone() is None:
        return None, "Elige un servicio de la lista."
    sid = db.insertar(
        "INSERT INTO solicitudes (odontologo_id, paciente_id, servicio_id, observaciones, "
        "fecha_solicitud, estado) VALUES (?, ?, ?, ?, ?, ?)",
        (odontologo_id, paciente_id, servicio_id, (observaciones or "").strip()[:500],
         inventario.ahora(), PENDIENTE))
    db.commit()
    return sid, None


def de_cliente(db, odontologo_id, estados=None):
    sql, params = CONSULTA + " WHERE s.odontologo_id = ?", [odontologo_id]
    if estados:
        sql += " AND s.estado IN (" + ", ".join("?" for _ in estados) + ")"
        params += list(estados)
    return db.execute(sql + " ORDER BY s.id DESC", params).fetchall()


def pendientes(db):
    return db.execute(CONSULTA + " WHERE s.estado = ? ORDER BY s.id", (PENDIENTE,)).fetchall()


def recientes(db, limite=15):
    """Las últimas ya respondidas (para que el laboratorio vea qué se hizo)."""
    return db.execute(CONSULTA + " WHERE s.estado <> ? ORDER BY s.id DESC LIMIT ?",
                      (PENDIENTE, limite)).fetchall()


def contar_pendientes(db):
    return db.execute("SELECT COUNT(*) FROM solicitudes WHERE estado = ?", (PENDIENTE,)).fetchone()[0]


def _pendiente(db, solicitud_id):
    return db.execute("SELECT * FROM solicitudes WHERE id = ? AND estado = ?",
                      (solicitud_id, PENDIENTE)).fetchone()


def aceptar(db, solicitud_id):
    """Crea la orden a partir de la solicitud. Devuelve (orden_id, None) o (None, error)."""
    s = _pendiente(db, solicitud_id)
    if s is None:
        return None, "Esa solicitud ya no está pendiente."
    nota = "Solicitada desde el portal" + (f": {s['observaciones']}" if s["observaciones"] else "")
    orden_id = ord_svc.crear_orden(db, s["odontologo_id"], s["paciente_id"], s["servicio_id"], nota)
    db.execute("UPDATE solicitudes SET estado = ?, orden_id = ?, fecha_respuesta = ? WHERE id = ?",
               (ACEPTADA, orden_id, inventario.ahora(), solicitud_id))
    db.commit()
    return orden_id, None


def rechazar(db, solicitud_id, motivo):
    motivo = (motivo or "").strip()[:300]
    if not motivo:
        return False, "Escribe el motivo del rechazo: el odontólogo lo verá."
    if _pendiente(db, solicitud_id) is None:
        return False, "Esa solicitud ya no está pendiente."
    db.execute("UPDATE solicitudes SET estado = ?, motivo = ?, fecha_respuesta = ? WHERE id = ?",
               (RECHAZADA, motivo, inventario.ahora(), solicitud_id))
    db.commit()
    return True, "Solicitud rechazada. El odontólogo verá el motivo en su portal."


def cancelar(db, solicitud_id, odontologo_id):
    """Solo el dueño, y solo mientras siga pendiente."""
    s = _pendiente(db, solicitud_id)
    if s is None or s["odontologo_id"] != odontologo_id:
        return False, "Esa solicitud ya no se puede cancelar."
    db.execute("UPDATE solicitudes SET estado = ?, fecha_respuesta = ? WHERE id = ?",
               (CANCELADA, inventario.ahora(), solicitud_id))
    db.commit()
    return True, "Solicitud cancelada."
