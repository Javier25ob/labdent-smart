"""SECCIÓN 2 - Lógica de INVENTARIO.
Entradas, salidas y alertas de stock bajo."""
from datetime import datetime


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def registrar_entrada(db, material_id, cantidad, nota="Compra"):
    """Suma stock y deja el movimiento registrado."""
    db.execute("UPDATE materiales SET stock = stock + ? WHERE id = ?", (cantidad, material_id))
    db.execute(
        "INSERT INTO movimientos_inventario (material_id, tipo, cantidad, fecha, nota) "
        "VALUES (?, 'ENTRADA', ?, ?, ?)",
        (material_id, cantidad, ahora(), nota),
    )


def registrar_salida(db, material_id, cantidad, orden_id=None, nota="Consumo"):
    """Resta stock (actualización automática del inventario)."""
    db.execute("UPDATE materiales SET stock = stock - ? WHERE id = ?", (cantidad, material_id))
    db.execute(
        "INSERT INTO movimientos_inventario (material_id, tipo, cantidad, fecha, orden_id, nota) "
        "VALUES (?, 'SALIDA', ?, ?, ?, ?)",
        (material_id, cantidad, ahora(), orden_id, nota),
    )


def alertas_stock(db):
    """Materiales cuyo stock está en el mínimo o por debajo."""
    return db.execute(
        "SELECT * FROM materiales WHERE stock <= stock_minimo ORDER BY stock - stock_minimo"
    ).fetchall()
