"""Pruebas de la simulación del flujo de producción (colas con SimPy).

    python -m unittest discover -s tests -v
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import simulacion_colas as sc  # noqa: E402
from test_login import BaseLogin              # noqa: E402

PARAMS = {"llegadas": 20, "dias": 30, "replicas": 6, "semilla": 7,
          "servicio": {"diseno": 20, "fresado": 22, "horno": 18, "acabado": 15}}


class Teoria(unittest.TestCase):
    def test_mm1_coincide_con_formula_conocida(self):
        # M/M/1: Wq = rho * s / (1 - rho). lam=1/24, s=22 -> rho=0.9167, Wq=242 min
        t = sc.teoria_mmc(1 / 24, 22, 1)
        self.assertAlmostEqual(t["rho"], 22 / 24)
        self.assertAlmostEqual(t["wq"], (22 / 24) * 22 / (1 - 22 / 24), places=6)
        self.assertTrue(t["estable"])

    def test_mmc_dos_servidores(self):
        # M/M/2 con a=1 (rho=0.5): Pw = 1/3, Wq = Pw/(c*mu-lam)
        t = sc.teoria_mmc(1 / 20, 20, 2)
        self.assertAlmostEqual(t["wq"], (1 / 3) / (2 / 20 - 1 / 20), places=6)

    def test_inestable(self):
        t = sc.teoria_mmc(1 / 10, 20, 1)
        self.assertFalse(t["estable"])
        self.assertTrue(math.isinf(t["wq"]))


class Simulacion(unittest.TestCase):
    CAP1 = {k: 1 for k in sc.CLAVES}

    def test_reproducible_con_la_misma_semilla(self):
        a = sc.simular_escenario(PARAMS, self.CAP1)
        b = sc.simular_escenario(PARAMS, self.CAP1)
        self.assertEqual(a["total_min"], b["total_min"])

    def test_cuello_de_botella_es_el_fresado(self):
        r = sc.simular_escenario(PARAMS, self.CAP1)
        self.assertEqual(r["cuello"]["clave"], "fresado")

    def test_segunda_fresadora_reduce_el_tiempo(self):
        a = sc.simular_escenario(PARAMS, self.CAP1)
        b = sc.simular_escenario(PARAMS, {**self.CAP1, "fresado": 2})
        self.assertLess(b["total_min"], a["total_min"] * 0.8)

    def test_simulacion_cercana_a_la_teoria_en_estaciones_poco_cargadas(self):
        p = {**PARAMS, "replicas": 12, "dias": 40}
        r = sc.simular_escenario(p, {"diseno": 2, "fresado": 2, "horno": 2, "acabado": 2})
        for e in r["etapas"]:
            self.assertAlmostEqual(e["util_sim"], e["rho_teorica"], delta=0.06)
        self.assertAlmostEqual(r["total_h"], r["teorico_h"], delta=0.35)

    def test_sistema_inestable_se_detecta(self):
        p = {**PARAMS, "llegadas": 40, "dias": 5, "replicas": 3}
        r = sc.simular_escenario(p, self.CAP1)
        self.assertFalse(r["estable"])
        self.assertIsNone(r["teorico_h"])

    def test_inversion_sugiere_probar_cada_estacion(self):
        filas = sc.sugerir_inversion({**PARAMS, "replicas": 3, "dias": 10}, self.CAP1)
        self.assertEqual([f["clave"] for f in filas], sc.CLAVES)


class Parametros(unittest.TestCase):
    def test_valores_fuera_de_rango_se_ajustan(self):
        p, a, b = sc.leer_parametros({"llegadas": "99999", "dias": "-4", "replicas": "x",
                                      "a_fresado": "50", "t_horno": "0"})
        self.assertEqual(p["llegadas"], sc.LIM["llegadas"][1])
        self.assertEqual(p["dias"], sc.LIM["dias"][0])
        self.assertEqual(p["replicas"], 15)
        self.assertEqual(a["fresado"], sc.LIM["capacidad"][1])
        self.assertEqual(p["servicio"]["horno"], sc.LIM["servicio"][0])

    def test_por_defecto_B_agrega_una_fresadora(self):
        _, a, b = sc.leer_parametros({})
        self.assertEqual(a["fresado"], 1)
        self.assertEqual(b["fresado"], 2)


class Pantalla(BaseLogin):
    def test_exige_login(self):
        self.assertEqual(self.cliente_http().get("/simulacion").status_code, 302)

    def test_se_muestra_y_acepta_parametros_raros(self):
        c = self.crear_admin()
        r = c.get("/simulacion?replicas=3&dias=5")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Cuello de botella", html)
        self.assertIn("chEsperas", html)
        self.assertEqual(c.get("/simulacion?llegadas=abc&dias=%27%3Cscript%3E").status_code, 200)

    def test_simulacion_de_materiales_sigue_funcionando(self):
        c = self.crear_admin()
        self.assertEqual(c.get("/simulacion/materiales").status_code, 200)
        self.assertEqual(c.post("/simulacion/materiales", data={"factor": "120", "horizonte": "30"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
