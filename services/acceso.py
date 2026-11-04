"""SECCIÓN 11 - Piezas compartidas del login (administrador y cliente):
contraseñas, redirecciones seguras, límite de intentos y permiso de administrador."""
import threading
import time
from functools import wraps

from flask import abort, g, request
from werkzeug.security import check_password_hash, generate_password_hash

import config

# Hash de relleno: si el usuario no existe igual comparamos contra algo, para que
# la respuesta tarde lo mismo y no se pueda adivinar qué usuarios existen.
_HASH_RELLENO = generate_password_hash("relleno-no-es-una-clave-real")


def normalizar_usuario(texto):
    """Los nombres de usuario no distinguen mayúsculas ni espacios en los bordes."""
    return (texto or "").strip().lower() or None


def validar_clave(clave):
    """Devuelve un mensaje de error si la contraseña no sirve, o None si está bien."""
    if len(clave) < config.CLAVE_MIN:
        return f"La contraseña debe tener al menos {config.CLAVE_MIN} caracteres."
    return None


def hash_clave(clave):
    return generate_password_hash(clave)


def clave_correcta(clave_hash, clave):
    """Compara siempre contra un hash (el real o el de relleno)."""
    ok = check_password_hash(clave_hash or _HASH_RELLENO, clave)
    return bool(clave_hash) and ok


def destino_seguro(destino, defecto):
    """Solo se permite volver a una ruta de ESTE sitio (evita que un enlace de login
    mande a la persona a una página externa después de entrar)."""
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return defecto


# ---------- Límite de intentos fallidos (en memoria, por IP) ----------
_fallos = {}
_candado = threading.Lock()


def _clave_ip(ambito):
    return f"{ambito}:{request.remote_addr}"


def bloqueado(ambito):
    """True si esta IP ya agotó sus intentos en la ventana de tiempo."""
    ahora = time.time()
    ventana = config.MINUTOS_BLOQUEO * 60
    with _candado:
        marcas = [t for t in _fallos.get(_clave_ip(ambito), []) if ahora - t < ventana]
        _fallos[_clave_ip(ambito)] = marcas
        return len(marcas) >= config.INTENTOS_MAX


def registrar_fallo(ambito):
    with _candado:
        _fallos.setdefault(_clave_ip(ambito), []).append(time.time())


def limpiar_fallos(ambito):
    with _candado:
        _fallos.pop(_clave_ip(ambito), None)


# ---------- Permisos ----------
def es_admin():
    """El rol sale de la base de datos en cada petición (app.py), no de la cookie:
    si le quitas el rol de administrador a alguien, el cambio aplica de inmediato."""
    usuario = g.get("usuario")
    return bool(usuario) and usuario["rol"] == config.ROL_ADMIN


def solo_admin(vista):
    """Decorador: la ruta solo la puede usar un Administrador."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not es_admin():
            abort(403)
        return vista(*args, **kwargs)
    return envoltura
