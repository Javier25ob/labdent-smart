"""SECCIÓN 5 - Panel principal (dashboard) e Inteligencia de Negocios."""
from flask import Blueprint, render_template, request

from database import get_ajuste, get_db
from services import acceso, analitica, inventario, seguimiento
from services import simulacion_colas as colas

bp = Blueprint("panel", __name__)


@bp.route("/")
def dashboard():
    db = get_db()
    n = lambda t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    pasos = [
        ("Pon tu WhatsApp", "Para que los odontólogos te escriban a tu número.", "/ajustes/", bool(get_ajuste("lab_whatsapp"))),
        ("Registra tus materiales", "Lo que usas: zirconio, acrílico, yeso… con su stock.", "/inventario/", n("materiales") > 0),
        ("Crea tus servicios", "Coronas, prótesis, carillas… con precio, días y materiales que gastan.", "/catalogos/?tab=servicios", n("servicios") > 0),
        ("Agrega un odontólogo", "El cliente que te envía los trabajos.", "/catalogos/?tab=odontologos", n("odontologos") > 0),
        ("Crea tu primera orden", "Y obtén su QR de seguimiento.", "/ordenes/nueva", n("ordenes") > 0),
    ]
    if not acceso.es_admin():      # "Ajustes" es solo de administradores: no les mostramos un paso que no pueden hacer
        pasos = [p for p in pasos if p[2] != "/ajustes/"]
    return render_template("dashboard.html", pasos=pasos, hay_ordenes=n("ordenes") > 0, hay_materiales=n("materiales") > 0,
                           kpi=analitica.indicadores(db),
                           recomendaciones=analitica.recomendaciones(db),
                           alertas=inventario.alertas_stock(db),
                           pulso=seguimiento.pulso(db),
                           riesgo=seguimiento.en_riesgo(db),
                           prediccion=analitica.prediccion_materiales(db))


@bp.route("/simulacion")
def simulacion():
    """Simulación del flujo de producción (colas, SimPy): compara dos configuraciones del laboratorio."""
    params, cap_a, cap_b = colas.leer_parametros(request.args)
    return render_template("simulacion.html", p=params, cap_a=cap_a, cap_b=cap_b,
                           r=colas.analizar(params, cap_a, cap_b), etapas=colas.ETAPAS,
                           lim=colas.LIM, jornada=colas.MINUTOS_JORNADA,
                           calentamiento=colas.DIAS_CALENTAMIENTO)


@bp.route("/simulacion/materiales", methods=["GET", "POST"])
def simulacion_materiales():
    db = get_db()
    factor, horizonte = 1.0, 30
    if request.method == "POST":
        factor = float(request.form.get("factor", 100)) / 100
        horizonte = int(request.form.get("horizonte", 30))
    filas = analitica.simular(db, factor, horizonte)
    return render_template("simulacion_materiales.html", filas=filas, factor=int(factor * 100),
                           horizonte=horizonte,
                           total=sum(f["costo"] for f in filas),
                           prediccion=analitica.prediccion_materiales(db))


@bp.route("/ayuda")
def ayuda():
    return render_template("ayuda.html")


@bp.route("/respaldo")
def respaldo():
    import database
    from flask import Response, send_file
    if database.usa_postgres():     # la base no es un archivo: se descarga una copia de todas las tablas en JSON
        return Response(database.volcar_json(), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=labdent_respaldo.json"})
    return send_file(database.DB_PATH, as_attachment=True, download_name="labdent_respaldo.db")
