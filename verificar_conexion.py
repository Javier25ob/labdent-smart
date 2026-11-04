"""Comprueba a qué base de datos se conecta LABDENT SMART y si la conexión funciona.

Uso (en la carpeta del proyecto):   python verificar_conexion.py
No modifica nada y nunca muestra tu contraseña.
"""
import sys
from pathlib import Path
from urllib.parse import urlsplit

import config

AQUI = Path(__file__).parent


def ok(texto):
    print(f"  [OK] {texto}")


def mal(texto):
    print(f"  [X]  {texto}")


def ocultar(texto, url):
    """Quita la contraseña de cualquier mensaje de error."""
    clave = urlsplit(url).password
    return texto.replace(clave, "******") if clave else texto


def pista(error):
    e = error.lower()
    if "password authentication failed" in e:
        return "La contraseña o el usuario son incorrectos. Revisa la contraseña de la base de datos (no la de tu cuenta de Supabase)."
    if "does not exist" in e and "role" in e:
        return "Ese usuario no existe en el servidor. Revisa el usuario de la URI (en Supabase con pooler: postgres.TU_REF)."
    if "does not exist" in e and "database" in e:
        return "Esa base de datos no existe. En Supabase el nombre de la base es 'postgres' (al final de la URI)."
    if "tenant or user not found" in e:
        return "Con el pooler de Supabase el usuario debe ser 'postgres.TU_REF' (con el punto y la referencia del proyecto), no solo 'postgres'."
    if "translate host name" in e or "name or service not known" in e or "getaddrinfo" in e:
        return "El nombre del servidor (host) está mal escrito o tu red no lo resuelve. Copia de nuevo la URI desde el botón Connect."
    if "network is unreachable" in e or "no route to host" in e:
        return "Tu red no tiene IPv6 y la 'Direct connection' de Supabase solo usa IPv6. Usa la URI del *Session pooler*."
    if "timeout" in e or "timed out" in e:
        return "Se agotó el tiempo: revisa tu internet, o prueba la URI del *Session pooler*."
    if "connection refused" in e:
        return "El servidor rechazó la conexión: revisa host y puerto en la URI."
    if "ssl" in e:
        return "Problema con el cifrado SSL: la URI de Supabase debe llevar ?sslmode=require (se agrega sola si falta)."
    return "Revisa que copiaste completa la URI y que la contraseña no tenga símbolos sin codificar (@ = %40, # = %23, / = %2F)."


def main():
    print(f"\nCarpeta del proyecto: {AQUI}\n")
    print("1) Archivo .env")
    if (AQUI / ".env").exists():
        ok("Existe el archivo .env")
    elif (AQUI / ".env.txt").exists():
        mal("Tienes un archivo llamado '.env.txt'. Debe llamarse exactamente '.env' (sin .txt). "
            "En la terminal: ren .env.txt .env")
    else:
        mal("No existe el archivo .env en esta carpeta. Créalo copiando el ejemplo:  copy .env.example .env")

    print("\n2) DATABASE_URL")
    url = config.DATABASE_URL
    if not url:
        mal("DATABASE_URL está vacía: la app usa SQLite local (un archivo solo en este computador).")
        print("       Abre .env, escribe la URI de Supabase después de 'DATABASE_URL=' (sin corchetes, sin '#' al inicio)")
        print("       y vuelve a correr este verificador.\n")
        sys.exit(1)
    partes = urlsplit(url)
    ok(f"Leída: usuario={partes.username}  servidor={partes.hostname}  puerto={partes.port}  base={partes.path.lstrip('/')}")
    if "[" in url or "]" in url or "YOUR-PASSWORD" in url.upper():
        mal("La URI aún tiene corchetes o '[YOUR-PASSWORD]': reemplaza eso por tu contraseña real (sin corchetes).")

    print("\n3) Conexión")
    try:
        import database
        conn = database.conectar()
    except Exception as exc:                       # noqa: BLE001 - queremos mostrar cualquier causa
        mal(f"No se pudo conectar: {type(exc).__name__}")
        print("       " + ocultar(str(exc).strip().splitlines()[0] if str(exc).strip() else "", url))
        print("       Pista: " + pista(str(exc)) + "\n")
        sys.exit(1)
    try:
        version = conn.execute("SELECT version()").fetchone()[0]
        ok("Conectado a PostgreSQL: " + version.split(",")[0])
        tablas = [f[0] for f in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY 1")]
        faltan = [t for t in database.TABLAS if t not in tablas]
        if not faltan:
            ok(f"Están las {len(database.TABLAS)} tablas de LABDENT SMART.")
        else:
            print(f"  [..] Aún no existen estas tablas: {', '.join(faltan)}")
            print("       Es normal la primera vez: se crean solas al correr  python app.py")
    finally:
        conn.close()
    print("\nTodo bien: la app está conectada a tu base de datos compartida.\n")


if __name__ == "__main__":
    main()
