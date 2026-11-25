"""El lector y su trinquete: sombra silenciosa, ordinal por ambito, ordinal compartido."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ordinal_ratchet import cli, scanner  # noqa: E402

# Caso real (medido al fusionar dos ramas de un corpus de 319 bancos): dos clases
# distintas del mismo fichero declaran `test_36`. Legal: las dos corren.
LEY_CON_ORDINAL_COMPARTIDO = """
import unittest


class ElPredicado(unittest.TestCase):
    def test_36_una_deuda_larga_da_rojo(self):
        pass


class LaVentana(unittest.TestCase):
    def test_36_la_ventana_no_cobra_la_simulacion(self):
        pass
"""

LEY_CON_ORDINAL_EN_UN_AMBITO = """
class Codigos:
    def test_1_el_bloqueo_gana(self):
        pass

    def test_1_bloqueo_sin_una_sola_cita(self):
        pass
"""

LEY_CON_SOMBRA = """
class LaVentana:
    def test_36_a(self):
        pass

    def test_36_a(self):
        pass
"""


def _escribir(raiz: Path, rel: str, texto: str) -> Path:
    destino = raiz / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino


def _correr(argv):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
        rc = cli.main(argv)
    return rc, salida.getvalue()


class ElLectorVeLaSombraYElOrdinal(unittest.TestCase):
    def test_un_nombre_repetido_en_el_mismo_ambito_es_sombra(self) -> None:
        cols = scanner.colisiones(scanner.definiciones(LEY_CON_SOMBRA, "ley.py"))
        self.assertEqual([c.clase for c in cols], [scanner.SOMBRA])
        self.assertEqual(cols[0].primera, 3)

    def test_el_mismo_nombre_en_clases_distintas_no_es_sombra(self) -> None:
        fuente = """
class A:
    def test_algo(self):
        pass


class B:
    def test_algo(self):
        pass
"""
        self.assertEqual(scanner.colisiones(scanner.definiciones(fuente, "ley.py")), [])

    def test_dos_nombres_distintos_con_el_mismo_ordinal_en_un_ambito_es_ordinal(self) -> None:
        cols = scanner.colisiones(scanner.definiciones(LEY_CON_ORDINAL_EN_UN_AMBITO, "ley.py"))
        self.assertEqual([c.clase for c in cols], [scanner.ORDINAL])
        self.assertEqual(cols[0].ambito, "Codigos")
        self.assertEqual((cols[0].linea, cols[0].primera), (6, 3))

    def test_el_mismo_ordinal_en_dos_clases_se_cuenta_pero_no_es_ordinal(self) -> None:
        cols = scanner.colisiones(scanner.definiciones(LEY_CON_ORDINAL_COMPARTIDO, "ley.py"))
        self.assertEqual([c.clase for c in cols], [scanner.COMPARTIDO])

    def test_un_nombre_dentro_de_un_docstring_no_define_nada(self) -> None:
        fuente = '''
"""def test_36_de_mentira(): pass
def test_36_tambien_de_mentira(): pass
"""


def test_1_real():
    pass
'''
        self.assertEqual(scanner.colisiones(scanner.definiciones(fuente, "ley.py")), [])

    def test_sombra_y_ordinal_no_se_cuentan_dos_veces_sobre_el_mismo_par(self) -> None:
        cuenta = scanner.recuento(
            scanner.colisiones(scanner.definiciones(LEY_CON_SOMBRA, "ley.py"))
        )
        self.assertEqual(cuenta, {"sombra": 1, "ordinal": 0, "compartido": 0})

    def test_un_fichero_que_no_parsea_es_ilegible_y_no_cero(self) -> None:
        _cols, ilegibles = scanner.escanear({"ley.py": "def test_1(:\n"})
        self.assertEqual(list(ilegibles), ["ley.py"])


class ElTrinqueteMuerde(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.base = self.raiz / ".ordinal-ratchet.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _argv(self):
        return [str(self.raiz), "--ratchet", str(self.base)]

    def test_un_arbol_limpio_da_rc_0(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", "def test_1_a():\n    pass\n")
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 0, salida)
        self.assertIn("sombra 0", salida)

    def test_un_ordinal_en_un_ambito_sobre_linea_base_vacia_da_rc_1(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", LEY_CON_ORDINAL_EN_UN_AMBITO)
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 1, salida)
        self.assertIn("SUBE", salida)

    def test_un_ordinal_compartido_no_falla_salvo_en_estricto(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", LEY_CON_ORDINAL_COMPARTIDO)
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 0, salida)
        self.assertIn("compartido 1", salida)
        rc, salida = _correr(self._argv() + ["--estricto"])
        self.assertEqual(rc, 1, salida)

    def test_la_base_congelada_absuelve_la_deuda_heredada(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", LEY_CON_ORDINAL_EN_UN_AMBITO)
        rc, _ = _correr(self._argv() + ["--write-baseline"])
        self.assertEqual(rc, 0)
        deuda = json.loads(self.base.read_text(encoding="utf-8"))["deuda"]
        self.assertEqual(deuda["tests/test_a.py"]["ordinal"], 1)
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 0, salida)

    def test_una_colision_nueva_sobre_la_base_da_rc_1(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", LEY_CON_ORDINAL_EN_UN_AMBITO)
        _correr(self._argv() + ["--write-baseline"])
        _escribir(self.raiz, "tests/test_b.py", LEY_CON_SOMBRA)
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 1, salida)
        self.assertIn("tests/test_b.py", salida)

    def test_una_deuda_resuelta_que_sigue_declarada_da_rc_1(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", LEY_CON_ORDINAL_EN_UN_AMBITO)
        _correr(self._argv() + ["--write-baseline"])
        _escribir(self.raiz, "tests/test_a.py", "def test_36_unico():\n    pass\n")
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 1, salida)
        self.assertIn("ZOMBI", salida)

    def test_sin_ficheros_de_prueba_da_rc_2(self) -> None:
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 2, salida)

    def test_un_fichero_que_no_parsea_da_rc_2(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", "def test_1(:\n")
        rc, salida = _correr(self._argv())
        self.assertEqual(rc, 2, salida)

    def test_json_trae_el_recuento_y_el_rc(self) -> None:
        _escribir(self.raiz, "tests/test_a.py", LEY_CON_ORDINAL_COMPARTIDO)
        rc, salida = _correr(self._argv() + ["--json"])
        self.assertEqual(rc, 0, salida)
        datos = json.loads(salida)
        self.assertEqual(datos["total"], {"sombra": 0, "ordinal": 0, "compartido": 1})
        self.assertEqual(datos["rc"], 0)
        self.assertEqual(datos["colisiones"][0]["nombre"], "ordinal 36 en 2 ambitos")


if __name__ == "__main__":
    unittest.main()
