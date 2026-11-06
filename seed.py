"""SECCIÓN 10 - Datos de ejemplo.  Uso:  python seed.py  (reinicia la base de datos)"""
import random
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

import database
from database import asegurar_ajustes, conectar, init_db

FMT = "%Y-%m-%d %H:%M:%S"


def cargar():
    random.seed(7)
    c = conectar()
    q = c.execute
    # Cuentas de DEMO: cada ejecución genera contraseñas al azar y las imprime
    # (no hay contraseñas fijas que alguien pueda adivinar si esto llega a un servidor).
    cuentas = []
    for n, r, u in [("Ana Pérez", "Administrador", "ana"), ("Luis Gómez", "Técnico", "luis"),
                    ("Marta Ruiz", "Recepción", "marta")]:
        clave = secrets.token_urlsafe(8)
        cuentas.append(("Panel", r, u, clave))
        q("INSERT INTO usuarios (nombre, rol, usuario, clave_hash) VALUES (?, ?, ?, ?)",
          (n, r, u, generate_password_hash(clave)))
    for n, t, cl, u in [("Dra. Carolina Mejía", "3001112233", "Clínica Sonrisa", "carolina"),
                        ("Dr. Andrés Cabrera", "3004445566", "OdontoCentro", "andres"),
                        ("Dra. Laura Vélez", "3007778899", "Dental Plus", "laura")]:
        clave = secrets.token_urlsafe(8)
        cuentas.append(("Portal cliente", cl, u, clave))
        q("INSERT INTO odontologos (nombre, telefono, clinica, usuario, clave_hash) VALUES (?, ?, ?, ?, ?)",
          (n, t, cl, u, generate_password_hash(clave)))
    pacientes = [("Juan Torres", "CC", "1065234567", "3011234567"), ("María López", "CC", "1065987654", "3029876543"),
                 ("Pedro Díaz", "TI", "1067123456", ""), ("Sofía Rojas", "CC", "49765432", "3154567890"),
                 ("Camilo Silva", "CE", "E2345678", "3168889900"), ("Lucía Mora", "CC", "1065555123", "")]
    for i, (n, tipo, doc, tel) in enumerate(pacientes):
        q("INSERT INTO pacientes (nombre, odontologo_id, tipo_documento, documento, telefono) VALUES (?, ?, ?, ?, ?)",
          (n, i % 3 + 1, tipo, doc, tel or None))
    servicios = [("Corona de zirconio", 380000, 6), ("Prótesis acrílica", 450000, 8),
                 ("Carilla de porcelana", 320000, 7), ("Guarda oclusal", 120000, 3)]
    for s in servicios:
        q("INSERT INTO servicios (nombre, precio, dias_estimados) VALUES (?, ?, ?)", s)
    materiales = [("Disco de zirconio", "und", 12, 4, 90000), ("Acrílico (polvo)", "g", 900, 300, 150),
                  ("Yeso tipo IV", "kg", 15, 5, 12000), ("Porcelana", "g", 120, 50, 1800),
                  ("Resina para guardas", "g", 600, 200, 220)]
    for m in materiales:
        q("INSERT INTO materiales (nombre, unidad, stock, stock_minimo, costo_unitario) VALUES (?, ?, ?, ?, ?)", m)
    # Recetas: servicio_id, material_id, cantidad
    for r in [(1, 1, 1), (1, 3, 0.3), (2, 2, 120), (2, 3, 0.5), (3, 4, 15), (3, 3, 0.2), (4, 5, 40)]:
        q("INSERT INTO servicio_materiales VALUES (?, ?, ?)", r)

    # Historial de 30 días: órdenes entregadas + consumos (para el modelo predictivo)
    hoy = datetime.now()
    for _ in range(25):
        servicio_id = random.randint(1, 4)
        ingreso = hoy - timedelta(days=random.randint(8, 30))
        dias = servicios[servicio_id - 1][2]
        est = ingreso + timedelta(days=dias)
        real = est + timedelta(days=random.choice([0, 0, 0, 1, 2]))
        pac = random.randint(1, 6)
        oid = c.insertar("INSERT INTO ordenes (odontologo_id, paciente_id, servicio_id, estado, fecha_ingreso, "
                         "fecha_entrega_estimada, fecha_entrega_real, consumo_registrado) VALUES (?, ?, ?, 'Entregada', ?, ?, ?, 1)",
                         ((pac - 1) % 3 + 1, pac, servicio_id, ingreso.strftime(FMT), est.strftime("%Y-%m-%d"),
                          real.strftime("%Y-%m-%d")))
        for estado in ["Recibida", "En producción", "Terminada", "Entregada"]:
            q("INSERT INTO historial_estados (orden_id, estado, fecha) VALUES (?, ?, ?)",
              (oid, estado, ingreso.strftime(FMT)))
        for mat, cant in q("SELECT material_id, cantidad FROM servicio_materiales WHERE servicio_id = ?",
                           (servicio_id,)).fetchall():
            q("INSERT INTO movimientos_inventario (material_id, tipo, cantidad, fecha, orden_id, nota) "
              "VALUES (?, 'SALIDA', ?, ?, ?, ?)", (mat, cant, ingreso.strftime(FMT), oid, f"Consumo orden #{oid}"))

    # Órdenes activas
    for servicio_id, estado, dias_atras in [(1, "Recibida", 1), (2, "En producción", 5), (3, "Terminada", 6),
                                            (4, "En producción", 2), (1, "En producción", 9)]:
        ingreso = hoy - timedelta(days=dias_atras)
        est = ingreso + timedelta(days=servicios[servicio_id - 1][2])
        pac = random.randint(1, 6)
        oid = c.insertar("INSERT INTO ordenes (odontologo_id, paciente_id, servicio_id, estado, fecha_ingreso, "
                         "fecha_entrega_estimada, consumo_registrado) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         ((pac - 1) % 3 + 1, pac, servicio_id, estado, ingreso.strftime(FMT), est.strftime("%Y-%m-%d"),
                          0 if estado == "Recibida" else 1))
        q("INSERT INTO historial_estados (orden_id, estado, fecha) VALUES (?, ?, ?)",
          (oid, estado, ingreso.strftime(FMT)))
    c.commit()
    c.close()
    return cuentas


if __name__ == "__main__":
    if database.usa_postgres():
        # Con PostgreSQL/Supabase la base la comparte todo el equipo: pedir confirmación antes de borrarla.
        print("ATENCIÓN: esto BORRA todas las tablas de la base PostgreSQL configurada en DATABASE_URL")
        print("y las recrea con datos de ejemplo. Los datos reales del equipo se perderían.")
        if input("Escribe BORRAR para continuar: ").strip().upper() != "BORRAR":
            raise SystemExit("Cancelado: no se tocó nada.")
    if not database.usa_postgres() and database.DB_PATH.exists():
        database.DB_PATH.unlink()
    init_db()          # PostgreSQL: borra y recrea las tablas (¡los datos actuales se pierden!)
    asegurar_ajustes()
    cuentas = cargar()
    print("Base de datos reiniciada con datos de ejemplo.\n")
    print("Cuentas de demostración (anótalas; solo se muestran ahora):")
    for donde, detalle, usuario, clave in cuentas:
        print(f"  {donde:<15} {usuario:<10} {clave:<14} ({detalle})")
