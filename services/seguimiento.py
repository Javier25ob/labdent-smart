"""SECCIÓN 4B - DIFERENCIADOR: seguimiento por QR, riesgo por orden y Pulso del laboratorio."""
import hashlib
import hmac
from datetime import datetime

import config
from services import analitica, inventario
from services import ordenes as ord_svc

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ---------- Código público de cada orden (sin cambiar la base de datos) ----------
def codigo(orden_id):
    firma = hmac.new(config.SECRET_KEY.encode(), str(orden_id).encode(), hashlib.sha256).hexdigest()[:5]
    return f"LD-{orden_id:04d}-{firma.upper()}"


def resolver(cod):
    """Devuelve el id de la orden si el código es válido, si no None."""
    try:
        _, num, _ = cod.strip().upper().split("-")
        oid = int(num)
    except ValueError:
        return None
    return oid if hmac.compare_digest(codigo(oid), cod.strip().upper()) else None


def fecha_larga(texto):
    if not texto:
        return "—"
    d = datetime.strptime(texto[:10], "%Y-%m-%d")
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


def iniciales(nombre):
    return " ".join(p[0].upper() + "." for p in nombre.split()[:2])


# ---------- Riesgo de atraso por orden ----------
def dias_para_entrega(o):
    est = datetime.strptime(o["fecha_entrega_estimada"], "%Y-%m-%d").date()
    return (est - datetime.now().date()).days


def riesgo(db, o):
    """Devuelve (nivel, motivo). nivel: alto / medio / bajo / ok."""
    if o["estado"] == "Entregada":
        return "ok", "Entregada"
    d = dias_para_entrega(o)
    if d < 0:
        return "alto", f"Atrasada {abs(d)} día(s)"
    if o["estado"] == "Recibida":
        faltan = [r["nombre"] for r in ord_svc.materiales_requeridos(db, o["servicio_id"])
                  if r["stock"] < r["cantidad"]]
        if faltan:
            return "alto", "Falta material: " + ", ".join(faltan)
    if o["estado"] == "Recibida" and d <= 1:
        return "alto", "Vence pronto y no inicia producción"
    if o["estado"] == "En producción" and d <= 1:
        return "medio", "Vence en ≤1 día y sigue en producción"
    if d <= 2 and o["estado"] in ("Recibida", "En producción"):
        return "medio", f"Vence en {d} día(s)"
    return "bajo", "En tiempo"


def ordenes_con_riesgo(db, estado=None):
    filas = []
    for o in ord_svc.listar(db, estado):
        nivel, motivo = riesgo(db, o)
        filas.append({**dict(o), "riesgo": nivel, "riesgo_motivo": motivo,
                      "codigo": codigo(o["id"]), "dias": dias_para_entrega(o)})
    return filas


def en_riesgo(db, limite=5):
    orden = {"alto": 0, "medio": 1}
    filas = [f for f in ordenes_con_riesgo(db) if f["riesgo"] in orden]
    filas.sort(key=lambda f: (orden[f["riesgo"]], f["dias"]))
    return filas[:limite]


# ---------- Pulso del laboratorio (índice 0-100) ----------
def pulso(db):
    k = analitica.indicadores(db)
    if k["total_ordenes"] == 0:
        return {"score": None, "nivel": "Sin datos aún", "color": "#9fb8d1", "factores": [],
                "mensaje": "Crea tu primera orden y aquí verás la salud de tu laboratorio."}
    factores, score = [], 100.0
    pen = min(40, k["atrasadas"] * 10)
    score -= pen
    factores.append(("Órdenes atrasadas", k["atrasadas"], pen))
    n_alerta = k["materiales_alerta"]
    pen = min(30, n_alerta * 8)
    score -= pen
    factores.append(("Materiales en alerta", n_alerta, pen))
    cumpl = k["cumplimiento"]
    pen = round((100 - cumpl) * 0.3, 1) if cumpl is not None else 0
    score -= pen
    factores.append(("Entregas a tiempo", f"{cumpl:g}%" if cumpl is not None else "—", pen))
    score = max(0, round(score))
    if score >= 85:
        nivel, color, msg = "Excelente", "#17a673", "El laboratorio opera con fluidez."
    elif score >= 65:
        nivel, color, msg = "Estable", "#0fb5a6", "Todo bajo control, con puntos a vigilar."
    elif score >= 40:
        nivel, color, msg = "Atención", "#f5a524", "Hay factores que ya afectan las entregas."
    else:
        nivel, color, msg = "Crítico", "#e5484d", "Actúa hoy: atrasos y faltantes comprometen entregas."
    return {"score": score, "nivel": nivel, "color": color, "mensaje": msg, "factores": factores}
