"""SECCIÓN 4 - INTELIGENCIA DE NEGOCIOS.
Indicadores, alertas, recomendaciones por reglas, modelo predictivo de
consumo, simulación de escenarios y optimización de compras."""
from datetime import datetime, timedelta
from math import ceil

from config import DIAS_HISTORICO, DIAS_HORIZONTE_COMPRA
from services import inventario


# ---------- 4.1 Indicadores (KPIs) ----------
def indicadores(db):
    hoy = datetime.now().strftime("%Y-%m-%d")
    por_estado = {r["estado"]: r["n"] for r in
                  db.execute("SELECT estado, COUNT(*) n FROM ordenes GROUP BY estado")}
    atrasadas = db.execute(
        "SELECT COUNT(*) FROM ordenes WHERE estado != 'Entregada' AND fecha_entrega_estimada < ?",
        (hoy,)).fetchone()[0]
    entregadas = db.execute(
        "SELECT COUNT(*) total, "
        "SUM(CASE WHEN fecha_entrega_real <= fecha_entrega_estimada THEN 1 ELSE 0 END) a_tiempo "
        "FROM ordenes WHERE estado = 'Entregada'").fetchone()
    cumplimiento = round(100 * (entregadas["a_tiempo"] or 0) / entregadas["total"], 1) if entregadas["total"] else None
    ingresos = db.execute(
        "SELECT COALESCE(SUM(s.precio),0) FROM ordenes o JOIN servicios s ON s.id = o.servicio_id "
        "WHERE o.estado = 'Entregada'").fetchone()[0]
    return {
        "por_estado": por_estado,
        "total_ordenes": sum(por_estado.values()),
        "atrasadas": atrasadas,
        "cumplimiento": cumplimiento,
        "ingresos": ingresos,
        "materiales_alerta": len(inventario.alertas_stock(db)),
    }


# ---------- 4.2 Modelo predictivo simple (promedio histórico) ----------
def consumo_diario(db, material_id, dias=DIAS_HISTORICO):
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    total = db.execute(
        "SELECT COALESCE(SUM(cantidad),0) FROM movimientos_inventario "
        "WHERE material_id = ? AND tipo = 'SALIDA' AND fecha >= ?", (material_id, desde)).fetchone()[0]
    return total / dias


def prediccion_materiales(db, horizonte=DIAS_HORIZONTE_COMPRA):
    """Para cada material: consumo diario, días de stock restantes y compra sugerida."""
    resultado = []
    for m in db.execute("SELECT * FROM materiales ORDER BY nombre"):
        c = consumo_diario(db, m["id"])
        dias_restantes = round(m["stock"] / c, 1) if c > 0 else None
        necesario = c * horizonte + m["stock_minimo"]
        comprar = max(0, ceil(necesario - m["stock"]))
        resultado.append({"material": m, "consumo_diario": round(c, 2),
                          "dias_restantes": dias_restantes, "comprar": comprar,
                          "costo_compra": comprar * m["costo_unitario"]})
    return resultado


# ---------- 4.3 Simulación de escenarios ----------
def simular(db, factor_demanda=1.0, horizonte=30):
    """¿Qué pasa con el inventario si la demanda cambia por 'factor_demanda'
    durante 'horizonte' días? Devuelve stock final, faltante y compra óptima."""
    filas = []
    for m in db.execute("SELECT * FROM materiales ORDER BY nombre"):
        consumo = consumo_diario(db, m["id"]) * factor_demanda
        necesario = consumo * horizonte
        stock_final = m["stock"] - necesario
        faltante = max(0, -stock_final)
        # Optimización simple: comprar lo justo para cubrir el horizonte + stock mínimo
        compra = max(0, ceil(necesario + m["stock_minimo"] - m["stock"]))
        filas.append({"material": m, "necesario": round(necesario, 1),
                      "stock_final": round(stock_final, 1), "faltante": round(faltante, 1),
                      "compra": compra, "costo": compra * m["costo_unitario"],
                      "se_agota": stock_final < 0})
    return filas


# ---------- 4.4 Recomendaciones basadas en reglas ----------
def recomendaciones(db):
    recs = []
    for m in inventario.alertas_stock(db):
        recs.append(("danger", f"Stock bajo de {m['nombre']} ({m['stock']:g} {m['unidad']}). Realizar compra."))
    for p in prediccion_materiales(db):
        d = p["dias_restantes"]
        if d is not None and d < 7 and p["material"]["stock"] > p["material"]["stock_minimo"]:
            recs.append(("warning", f"{p['material']['nombre']} se agotaría en ~{d} días al ritmo actual."))
    hoy = datetime.now().strftime("%Y-%m-%d")
    n = db.execute("SELECT COUNT(*) FROM ordenes WHERE estado != 'Entregada' AND fecha_entrega_estimada < ?",
                   (hoy,)).fetchone()[0]
    if n:
        recs.append(("danger", f"Hay {n} orden(es) atrasada(s). Priorizarlas en producción."))
    terminadas = db.execute("SELECT COUNT(*) FROM ordenes WHERE estado = 'Terminada'").fetchone()[0]
    if terminadas >= 3:
        recs.append(("info", f"{terminadas} órdenes terminadas esperan entrega. Avisar a los odontólogos."))
    if not recs:
        recs.append(("success", "Todo en orden: sin alertas por ahora."))
    return recs
