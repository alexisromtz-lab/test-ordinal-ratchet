"""Colisiones entre nombres de prueba: sombra silenciosa y ordinal repetido.

Dos defectos distintos comparten causa: el nombre de la prueba es un
identificador, y los identificadores se repiten al fusionar ramas.

  sombra   dos definiciones del MISMO nombre en el MISMO ambito. Python deja
           viva la ultima y la primera nunca corre: la prueba desaparece sin que
           git reporte conflicto, porque el texto no se pisa.
  ordinal  dos nombres DISTINTOS que comparten el prefijo numerico
           (`test_36_a`, `test_36_b`). Las dos corren, pero cualquier referencia
           a «test_36» deja de ser inyectiva: `-k test_36` y los informes no
           pueden distinguirlas.

Se lee con `ast`, no con expresiones regulares: un nombre dentro de un docstring
o de un comentario no es una definicion.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

RE_ORDINAL = re.compile(r"^test_(\d+)")

SOMBRA = "sombra"
ORDINAL = "ordinal"
COMPARTIDO = "compartido"

#: Lo unico que el trinquete cobra. `compartido` se cuenta y se publica, pero no
#: falla: dos clases del mismo fichero pueden reusar el ordinal sin que ninguna
#: prueba deje de correr.
CLASES_TRINQUETE = (SOMBRA, ORDINAL)
CLASES = (SOMBRA, ORDINAL, COMPARTIDO)


@dataclasses.dataclass(frozen=True)
class Definicion:
    ruta: str
    ambito: str
    nombre: str
    linea: int


@dataclasses.dataclass(frozen=True)
class Colision:
    clase: str
    ruta: str
    ambito: str
    nombre: str
    linea: int
    primera: int

    def linea_de_reporte(self) -> str:
        if self.clase == SOMBRA:
            return (
                "%s:%d %s.%s pisa la definicion de :%d (esa prueba nunca corre)"
                % (self.ruta, self.linea, self.ambito, self.nombre, self.primera)
            )
        if self.clase == COMPARTIDO:
            return "%s:%d %s desde :%d (legal: ninguna prueba deja de correr)" % (
                self.ruta,
                self.linea,
                self.nombre,
                self.primera,
            )
        return (
            "%s:%d %s.%s comparte ordinal con la definicion de :%d"
            % (self.ruta, self.linea, self.ambito, self.nombre, self.primera)
        )


def _definiciones(cuerpo: List[ast.stmt], ambito: str, ruta: str) -> Iterator[Definicion]:
    for nodo in cuerpo:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if nodo.name.startswith("test"):
                yield Definicion(ruta, ambito, nodo.name, nodo.lineno)
        elif isinstance(nodo, ast.ClassDef):
            anidado = nodo.name if ambito == "modulo" else ambito + "." + nodo.name
            yield from _definiciones(nodo.body, anidado, ruta)


def definiciones(fuente: str, ruta: str) -> List[Definicion]:
    """Definiciones `test*` de un fuente, con su ambito. `ast` o nada."""
    arbol = ast.parse(fuente)
    return list(_definiciones(arbol.body, "modulo", ruta))


def colisiones(deffs: Sequence[Definicion]) -> List[Colision]:
    """Sombra siempre; ordinal dentro del mismo ambito; `compartido` solo se cuenta."""
    salida: List[Colision] = []

    primera_vista: Dict[Tuple[str, str, str], int] = {}
    for d in deffs:
        clave = (d.ruta, d.ambito, d.nombre)
        if clave in primera_vista:
            salida.append(
                Colision(SOMBRA, d.ruta, d.ambito, d.nombre, d.linea, primera_vista[clave])
            )
        else:
            primera_vista[clave] = d.linea

    grupos: Dict[Tuple[str, int], List[Definicion]] = {}
    for d in deffs:
        coincide = RE_ORDINAL.match(d.nombre)
        if coincide:
            grupos.setdefault((d.ruta, int(coincide.group(1))), []).append(d)

    for (ruta, numero), grupo in sorted(grupos.items()):
        por_ambito: Dict[str, List[Definicion]] = {}
        for d in grupo:
            por_ambito.setdefault(d.ambito, []).append(d)
        if len(por_ambito) > 1:
            primera = min(d.linea for d in grupo)
            salida.append(
                Colision(
                    COMPARTIDO,
                    ruta,
                    "*",
                    "ordinal %d en %d ambitos" % (numero, len(por_ambito)),
                    primera,
                    primera,
                )
            )
        for ambito, ds in por_ambito.items():
            if len({d.nombre for d in ds}) < 2:
                continue
            ordenadas = sorted(ds, key=lambda d: d.linea)
            for d in ordenadas[1:]:
                salida.append(
                    Colision(ORDINAL, ruta, ambito, d.nombre, d.linea, ordenadas[0].linea)
                )
    return salida


def recuento(cols: Iterable[Colision]) -> Dict[str, int]:
    cuenta = {clase: 0 for clase in CLASES}
    for c in cols:
        cuenta[c.clase] += 1
    return cuenta


def escanear(fuentes: Dict[str, str]) -> Tuple[List[Colision], Dict[str, str]]:
    """Devuelve (colisiones, ilegibles). Un fuente que no parsea no se adivina."""
    todas: List[Colision] = []
    ilegibles: Dict[str, str] = {}
    for ruta in sorted(fuentes):
        try:
            todas.extend(colisiones(definiciones(fuentes[ruta], ruta)))
        except SyntaxError as error:
            ilegibles[ruta] = "linea %s: %s" % (error.lineno, error.msg)
    return todas, ilegibles
