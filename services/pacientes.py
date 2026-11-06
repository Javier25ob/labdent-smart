"""SECCIÓN 8B - Datos de los PACIENTES (nombre, documento de identidad y teléfono).

Todo el sistema crea y edita pacientes por aquí (catálogos, nueva orden y portal del
odontólogo), para que las reglas sean las mismas en todas partes:
  * nombre obligatorio,
  * tipo y número de documento opcionales, pero si se escribe un número debe ser válido
    y NO puede repetirse entre los pacientes del mismo odontólogo,
  * teléfono opcional, con un número de dígitos razonable.
"""
import re

# Tipos de documento de identidad usados en Colombia
TIPOS_DOCUMENTO = {
    "CC": "Cédula de ciudadanía",
    "TI": "Tarjeta de identidad",
    "RC": "Registro civil",
    "CE": "Cédula de extranjería",
    "PA": "Pasaporte",
    "PPT": "Permiso por protección temporal",
}
TIPO_DEFECTO = "CC"
SOLO_NUMEROS = {"CC", "TI", "RC"}      # los demás pueden llevar letras (ej. pasaporte)


def limpiar_documento(texto):
    """Quita espacios, puntos y guiones: '1.065.234-5' -> '10652345'."""
    return re.sub(r"[\s.\-]", "", texto or "").upper()


def leer(form, prefijo=""):
    """Lee nombre, documento y teléfono de un formulario. Devuelve (datos, error).
    `prefijo` sirve cuando el paciente se crea dentro de otro formulario (ej. 'paciente_')."""
    nombre = (form.get(prefijo + "nombre") or "").strip()[:120]
    tipo = (form.get(prefijo + "tipo_documento") or TIPO_DEFECTO).strip().upper()
    documento = limpiar_documento(form.get(prefijo + "documento"))
    telefono = (form.get(prefijo + "telefono") or "").strip()[:30]

    if not nombre:
        return None, "Escribe el nombre del paciente."
    if tipo not in TIPOS_DOCUMENTO:
        return None, "Elige un tipo de documento de la lista."
    if documento:
        if tipo in SOLO_NUMEROS and not documento.isdigit():
            return None, f"El número de {TIPOS_DOCUMENTO[tipo].lower()} solo lleva números."
        if not re.fullmatch(r"[0-9A-Z]{4,20}", documento):
            return None, "El número de documento debe tener entre 4 y 20 letras o números."
    if telefono:
        digitos = re.sub(r"\D", "", telefono)
        if not re.fullmatch(r"[0-9+\s()\-]+", telefono) or not 7 <= len(digitos) <= 15:
            return None, "El teléfono debe tener entre 7 y 15 dígitos (ej. 300 123 4567)."
    return {"nombre": nombre, "tipo_documento": tipo if documento else None,
            "documento": documento or None, "telefono": telefono or None}, None


def _documento_repetido(db, odontologo_id, datos, excepto_id=None):
    if not datos["documento"]:
        return False
    fila = db.execute(
        "SELECT id FROM pacientes WHERE odontologo_id = ? AND tipo_documento = ? AND documento = ? "
        "AND id <> ?", (odontologo_id, datos["tipo_documento"], datos["documento"], excepto_id or 0)).fetchone()
    return fila is not None


MSG_REPETIDO = "Ya hay un paciente de ese odontólogo con ese mismo documento."


def crear(db, odontologo_id, datos):
    """Inserta el paciente (sin commit, así se puede deshacer junto con lo demás).
    Devuelve (id, None) o (None, error)."""
    if _documento_repetido(db, odontologo_id, datos):
        return None, MSG_REPETIDO
    pid = db.insertar(
        "INSERT INTO pacientes (nombre, odontologo_id, tipo_documento, documento, telefono) "
        "VALUES (?, ?, ?, ?, ?)",
        (datos["nombre"], odontologo_id, datos["tipo_documento"], datos["documento"], datos["telefono"]))
    return pid, None


def actualizar(db, paciente_id, odontologo_id, datos):
    """Actualiza todos los datos (sin commit). Devuelve un error o None."""
    if _documento_repetido(db, odontologo_id, datos, excepto_id=paciente_id):
        return MSG_REPETIDO
    db.execute("UPDATE pacientes SET nombre = ?, odontologo_id = ?, tipo_documento = ?, documento = ?, "
               "telefono = ? WHERE id = ?",
               (datos["nombre"], odontologo_id, datos["tipo_documento"], datos["documento"],
                datos["telefono"], paciente_id))
    return None


def etiqueta_documento(p):
    """'CC 1065234567' para mostrar en listas, o '' si no tiene."""
    return f"{p['tipo_documento'] or TIPO_DEFECTO} {p['documento']}" if p["documento"] else ""
