"""SECCIÓN 12 - Simulación de eventos discretos del flujo de producción (SimPy).

Modelo
------
Las órdenes llegan al laboratorio con un proceso de Poisson (tiempos entre llegadas
exponenciales, media = jornada / órdenes por día) y recorren 4 estaciones en serie:

    Diseño CAD  ->  Fresado  ->  Horno  ->  Acabado / QC

Cada estación es un recurso con `capacidad` servidores (técnicos o máquinas) y una sola
fila de espera (FIFO). El tiempo de servicio es exponencial con la media de la estación.
Es decir, cada estación es una cola M/M/c, y el sistema completo una red de colas en serie.

Validación
----------
Para cada estación se calcula también el resultado TEÓRICO (Erlang C) y se muestra junto al
simulado. Por el teorema de Burke, con llegadas Poisson y servicio exponencial, las salidas
de una M/M/c vuelven a ser Poisson, así que cada estación de la serie se comporta como una
M/M/c independiente. Si la simulación y la teoría coinciden, el modelo está bien construido.

Todas las corridas usan generadores aleatorios propios (`random.Random(semilla)`), por lo que
son reproducibles y no interfieren con otras peticiones de la app.
"""
import math
import random
import statistics

import simpy

ETAPAS = [
    ("diseno", "Diseño CAD", 20),
    ("fresado", "Fresado", 22),
    ("horno", "Horno", 18),
    ("acabado", "Acabado / QC", 15),
]
CLAVES = [e[0] for e in ETAPAS]
NOMBRES = {e[0]: e[1] for e in ETAPAS}

MINUTOS_JORNADA = 480            # 8 horas de trabajo por día
DIAS_CALENTAMIENTO = 3           # días iniciales que se descartan (el sistema arranca vacío)

# Límites de lo que se acepta del formulario (protegen al servidor de corridas gigantes)
LIM = {"llegadas": (1, 60), "servicio": (5, 120), "capacidad": (1, 5),
       "dias": (5, 60), "replicas": (3, 30), "semilla": (0, 999999)}


# ---------------------------------------------------------------------------
# Teoría de colas (M/M/c)
# ---------------------------------------------------------------------------
def teoria_mmc(lam, media_servicio, c):
    """Resultados teóricos de una cola M/M/c. Tiempos en minutos, `lam` en órdenes/minuto.
    Devuelve rho (utilización), wq (espera en cola), w (espera + servicio) y si es estable."""
    mu = 1.0 / media_servicio
    a = lam / mu                      # carga ofrecida (en "servidores ocupados")
    rho = a / c
    if rho >= 1:
        return {"rho": rho, "wq": math.inf, "w": math.inf, "estable": False}
    suma = sum(a ** k / math.factorial(k) for k in range(c))
    cola = a ** c / (math.factorial(c) * (1 - rho))
    p_espera = cola / (suma + cola)   # Erlang C: probabilidad de tener que esperar
    wq = p_espera / (c * mu - lam)
    return {"rho": rho, "wq": wq, "w": wq + media_servicio, "estable": True}


# ---------------------------------------------------------------------------
# Simulación (SimPy)
# ---------------------------------------------------------------------------
def _una_corrida(params, capacidades, semilla):
    """Una réplica completa. Devuelve esperas por etapa, tiempos totales y tiempo ocupado."""
    rng = random.Random(semilla)
    env = simpy.Environment()
    estaciones = {k: simpy.Resource(env, capacity=capacidades[k]) for k in CLAVES}
    media = params["servicio"]
    interarribo = MINUTOS_JORNADA / params["llegadas"]
    calentamiento = DIAS_CALENTAMIENTO * MINUTOS_JORNADA
    horizonte = (params["dias"] + DIAS_CALENTAMIENTO) * MINUTOS_JORNADA

    esperas = {k: [] for k in CLAVES}
    totales = []
    ocupado = {k: 0.0 for k in CLAVES}

    def orden(llegada):
        medir = llegada >= calentamiento
        for k in CLAVES:
            with estaciones[k].request() as req:
                t0 = env.now
                yield req
                espera = env.now - t0
                servicio = rng.expovariate(1.0 / media[k])
                yield env.timeout(servicio)
            if medir:
                esperas[k].append(espera)
                ocupado[k] += servicio
        if medir:
            totales.append(env.now - llegada)

    def llegadas():
        while env.now < horizonte:
            yield env.timeout(rng.expovariate(1.0 / interarribo))
            if env.now < horizonte:
                env.process(orden(env.now))

    env.process(llegadas())
    env.run()          # sin "until": corre hasta que TODAS las órdenes terminan (sin sesgo por corte)
    return esperas, totales, ocupado


def _p90(valores):
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, math.ceil(0.9 * len(ordenados)) - 1)]


def simular_escenario(params, capacidades):
    """Corre `replicas` réplicas (semillas consecutivas) y promedia los resultados."""
    n = params["replicas"]
    dias_medidos = params["dias"]
    espera_rep = {k: [] for k in CLAVES}
    util_rep = {k: [] for k in CLAVES}
    total_rep, p90_rep, completadas_rep = [], [], []

    for i in range(n):
        esperas, totales, ocupado = _una_corrida(params, capacidades, params["semilla"] + i)
        if not totales:
            continue
        for k in CLAVES:
            espera_rep[k].append(statistics.mean(esperas[k]))
            util_rep[k].append(ocupado[k] / (capacidades[k] * dias_medidos * MINUTOS_JORNADA))
        total_rep.append(statistics.mean(totales))
        p90_rep.append(_p90(totales))
        completadas_rep.append(len(totales))

    def media_std(v):
        return statistics.mean(v), (statistics.stdev(v) if len(v) > 1 else 0.0)

    lam = params["llegadas"] / MINUTOS_JORNADA
    etapas, teorico_total, estable = [], 0.0, True
    for k in CLAVES:
        t = teoria_mmc(lam, params["servicio"][k], capacidades[k])
        espera, espera_std = media_std(espera_rep[k])
        estable = estable and t["estable"]
        teorico_total += t["w"]
        etapas.append({
            "clave": k, "nombre": NOMBRES[k], "capacidad": capacidades[k],
            "servicio": params["servicio"][k],
            "rho_teorica": t["rho"], "util_sim": media_std(util_rep[k])[0],
            "espera_sim": espera, "espera_std": espera_std,
            "espera_teor": t["wq"] if t["estable"] else None,
            "cola_prom": lam * espera,                  # Ley de Little: Lq = λ · Wq
        })
    total, total_std = media_std(total_rep)
    cuello = max(etapas, key=lambda e: (e["espera_sim"], e["rho_teorica"]))
    return {
        "capacidades": dict(capacidades), "etapas": etapas, "estable": estable,
        "total_min": total, "total_h": total / 60, "total_std_h": total_std / 60,
        "ic95_h": 1.96 * (total_std / 60) / math.sqrt(len(total_rep)),
        "p90_h": statistics.mean(p90_rep) / 60,
        "teorico_h": (teorico_total / 60) if estable else None,
        "completadas_dia": statistics.mean(completadas_rep) / dias_medidos,
        "cuello": cuello,
    }


def sugerir_inversion(params, base):
    """Prueba agregar UN servidor a cada estación (con las mismas semillas) y mide la mejora.
    Responde: ¿dónde conviene invertir primero?"""
    filas = []
    for k in CLAVES:
        if base[k] >= LIM["capacidad"][1]:
            continue
        caps = dict(base)
        caps[k] += 1
        r = simular_escenario(params, caps)
        filas.append({"clave": k, "nombre": NOMBRES[k], "nueva_cap": caps[k],
                      "total_h": r["total_h"]})
    return filas


# ---------------------------------------------------------------------------
# Lectura segura de parámetros (formulario / URL)
# ---------------------------------------------------------------------------
def _entero(valor, defecto, limites):
    try:
        n = int(float(valor))
    except (TypeError, ValueError):
        n = defecto
    return max(limites[0], min(limites[1], n))


def leer_parametros(args):
    """Convierte los datos del formulario en parámetros válidos (si algo viene mal, usa el valor por defecto)."""
    params = {
        "llegadas": _entero(args.get("llegadas"), 20, LIM["llegadas"]),
        "dias": _entero(args.get("dias"), 30, LIM["dias"]),
        "replicas": _entero(args.get("replicas"), 15, LIM["replicas"]),
        "semilla": _entero(args.get("semilla"), 42, LIM["semilla"]),
        "servicio": {k: _entero(args.get(f"t_{k}"), m, LIM["servicio"]) for k, _, m in ETAPAS},
    }
    cap_a = {k: _entero(args.get(f"a_{k}"), 1, LIM["capacidad"]) for k in CLAVES}
    # Por defecto el escenario B es "el actual + una segunda fresadora" (la pregunta del proyecto)
    cap_b = {k: _entero(args.get(f"b_{k}"), 2 if k == "fresado" else 1, LIM["capacidad"]) for k in CLAVES}
    return params, cap_a, cap_b


def analizar(params, cap_a, cap_b):
    """Todo lo que muestra la pantalla: escenario A, escenario B, comparación e inversión sugerida."""
    a = simular_escenario(params, cap_a)
    b = simular_escenario(params, cap_b) if cap_b != cap_a else a
    reduccion = (1 - b["total_min"] / a["total_min"]) * 100 if a["total_min"] else 0.0
    return {"a": a, "b": b, "reduccion": reduccion, "iguales": cap_a == cap_b,
            "inversion": sugerir_inversion(params, cap_a)}
