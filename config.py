"""SECCIÓN 0 - Configuración general del sistema."""
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

# Estados por los que pasa una orden de trabajo (en orden)
ESTADOS = ["Recibida", "En producción", "Terminada", "Entregada"]

# Estado en el que se descuentan automáticamente los materiales
ESTADO_CONSUMO = "En producción"

# Ventana (días) usada para calcular el consumo promedio de cada material
DIAS_HISTORICO = 30

# Horizonte (días) para sugerir compras en el modelo predictivo
DIAS_HORIZONTE_COMPRA = 15


def _cargar_dotenv():
    """Lee el archivo `.env` (si existe) y deja sus variables en el entorno.
    Sirve para guardar ahí la conexión a la base de datos y la clave secreta sin escribirlas
    en el código. Una variable de entorno real siempre manda sobre el `.env`. El `.env` NO se
    sube a GitHub (está en .gitignore)."""
    archivo = Path(__file__).parent / ".env"
    if not archivo.exists():
        return
    # utf-8-sig: el Bloc de notas de Windows a veces guarda un carácter invisible (BOM) al inicio; se ignora
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        nombre, valor = linea.split("=", 1)
        os.environ.setdefault(nombre.strip(), valor.strip().strip('"').strip("'"))


_cargar_dotenv()


def _url_base_de_datos():
    """Dirección de PostgreSQL / Supabase (variable DATABASE_URL). Vacía = se usa SQLite local."""
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):                      # así la entregan algunos servicios
        url = "postgresql://" + url[len("postgres://"):]
    partes = urlsplit(url)
    remoto = partes.hostname not in (None, "", "localhost", "127.0.0.1", "::1")
    if remoto and "sslmode=" not in url:                   # Supabase y similares exigen conexión cifrada
        url += ("&" if partes.query else "?") + "sslmode=require"
    return url


def _cargar_clave_secreta():
    """Clave que firma las sesiones de login y los códigos QR.

    Nunca va escrita en el código (si lo estuviera, cualquiera podría fabricar una
    sesión de administrador). Orden de búsqueda:
      1. Variable de entorno LABDENT_SECRET_KEY (recomendado al publicar la app).
      2. Archivo local `clave_secreta.key`, que se crea solo la primera vez.
    """
    de_entorno = os.environ.get("LABDENT_SECRET_KEY")
    if de_entorno:
        return de_entorno
    archivo = Path(__file__).parent / "clave_secreta.key"
    if archivo.exists():
        return archivo.read_text(encoding="utf-8").strip()
    clave = secrets.token_hex(32)
    archivo.write_text(clave, encoding="utf-8")
    try:
        archivo.chmod(0o600)
    except OSError:
        pass
    return clave


SECRET_KEY = _cargar_clave_secreta()
DATABASE_URL = _url_base_de_datos()

# ---- Sesión / login ----
HORAS_SESION = 12                                   # tras este tiempo hay que volver a entrar
SOLO_HTTPS = os.environ.get("LABDENT_HTTPS") == "1"   # ponlo en 1 cuando publiques con https
CLAVE_MIN = 8                                       # largo mínimo de contraseña
INTENTOS_MAX = 5                                    # intentos fallidos de login permitidos...
MINUTOS_BLOQUEO = 10                                # ...por IP, en esta ventana de minutos

# Roles del personal del laboratorio. Solo "Administrador" entra a Ajustes, Respaldo y Mi equipo.
ROLES = ["Administrador", "Técnico", "Recepción"]
ROL_ADMIN = "Administrador"

# ---- Identidad (se cambian desde la pantalla "Ajustes" dentro de la app) ----
LAB_NOMBRE = "Mi Laboratorio Dental"
