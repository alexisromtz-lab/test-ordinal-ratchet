"""CLI de `test-ordinal-ratchet`.

Contrato de salida:

  RC 0  nada sube sobre la linea base declarada (que puede ser cero)
  RC 1  una colision NUEVA, un contador por encima de la base, o una deuda
        declarada que ya no existe (deuda zombi: se resuelve, se quita)
  RC 2  uso invalido, sin ficheros de prueba (ausencia de sujeto no es cero),
        o un fichero que no parsea (no se adivina lo que no se pudo leer)

La linea base es un JSON con la deuda HEREDADA. El trinquete es de una sola
direccion: el recuento declarado puede bajar, nunca subir.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Optional, Sequence, Tuple

from . import scanner

RUTA_BASE = ".ordinal-ratchet.json"
VERSION_BASE = 1


def _recolectar(
    rutas: Sequence[str], patron: str
) -> Tuple[List[Tuple[str, pathlib.Path]], List[str]]:
    """Devuelve pares (clave, fichero). La clave es relativa al argumento que lo trajo.

    Una clave absoluta ataria la linea base a la maquina donde se congelo, y la
    deuda heredada dejaria de leerse al clonar.
    """
    ficheros: List[Tuple[str, pathlib.Path]] = []
    faltantes: List[str] = []
    for ruta in rutas:
        p = pathlib.Path(ruta)
        if p.is_dir():
            for hallado in sorted(p.rglob(patron)):
                ficheros.append((hallado.relative_to(p).as_posix(), hallado))
        elif p.is_file():
            ficheros.append((p.name, p))
        else:
            faltantes.append(ruta)
    vistos: Dict[str, pathlib.Path] = {}
    for clave, fichero in ficheros:
        vistos.setdefault(clave, fichero)
    return sorted(vistos.items()), faltantes


def _leer(ficheros: Sequence[Tuple[str, pathlib.Path]]) -> Dict[str, str]:
    fuentes: Dict[str, str] = {}
    for clave, fichero in ficheros:
        try:
            fuentes[clave] = fichero.read_text(encoding="utf-8", errors="replace")
        except OSError:
            fuentes[clave] = ""
    return fuentes


def _cargar_base(ruta: pathlib.Path) -> Tuple[Dict[str, Dict[str, int]], Optional[str]]:
    if not ruta.is_file():
        return {}, None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, "linea base ilegible: %s" % error
    deuda = datos.get("deuda")
    if not isinstance(deuda, dict):
        return {}, "linea base sin bloque `deuda`"
    limpio: Dict[str, Dict[str, int]] = {}
    for ruta_f, cuenta in deuda.items():
        if not isinstance(cuenta, dict):
            return {}, "linea base con entrada que no es objeto: %s" % ruta_f
        limpio[str(ruta_f)] = {
            clase: int(cuenta.get(clase, 0) or 0) for clase in scanner.CLASES
        }
    return limpio, None


def _medido_por_fichero(cols: Sequence[scanner.Colision]) -> Dict[str, Dict[str, int]]:
    salida: Dict[str, Dict[str, int]] = {}
    for c in cols:
        cuenta = salida.setdefault(c.ruta, {clase: 0 for clase in scanner.CLASES})
        cuenta[c.clase] += 1
    return salida


def _comparar(
    medido: Dict[str, Dict[str, int]], base: Dict[str, Dict[str, int]]
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, int]]]:
    subidas: Dict[str, Dict[str, int]] = {}
    zombis: Dict[str, Dict[str, int]] = {}
    for ruta in sorted(set(medido) | set(base)):
        ahora = medido.get(ruta, {clase: 0 for clase in scanner.CLASES})
        declarado = base.get(ruta, {clase: 0 for clase in scanner.CLASES})
        for clase in scanner.CLASES_TRINQUETE:
            if ahora[clase] > declarado[clase]:
                subidas.setdefault(ruta, {})[clase] = ahora[clase] - declarado[clase]
            elif declarado[clase] > ahora[clase]:
                zombis.setdefault(ruta, {})[clase] = declarado[clase] - ahora[clase]
    return subidas, zombis


def _deuda_de(medido: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, int]]:
    return {
        f: {c: v for c, v in cuenta.items() if c in scanner.CLASES_TRINQUETE}
        for f, cuenta in medido.items()
        if any(cuenta.get(c) for c in scanner.CLASES_TRINQUETE)
    }


def _escribir_base(ruta: pathlib.Path, patron: str, medido: Dict[str, Dict[str, int]]) -> None:
    ruta.write_text(
        json.dumps(
            {"version": VERSION_BASE, "patron": patron, "deuda": _deuda_de(medido)},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _resumen(medido: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    return {
        clase: sum(c.get(clase, 0) for c in medido.values()) for clase in scanner.CLASES
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="test-ordinal-ratchet",
        description="Detecta nombres de prueba pisados o con ordinal repetido, "
        "con trinquete de deuda heredada.",
    )
    parser.add_argument("rutas", nargs="*", default=["."], help="directorios o ficheros")
    parser.add_argument("--patron", default="test_*.py", help="glob de ficheros en directorios")
    parser.add_argument(
        "--ratchet",
        default=None,
        help="linea base de deuda (por defecto %s junto al cwd)" % RUTA_BASE,
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="congela el recuento actual como deuda heredada",
    )
    parser.add_argument("--json", action="store_true", help="salida legible por maquina")
    parser.add_argument(
        "--estricto",
        action="store_true",
        help="tambien falla si dos ambitos del mismo fichero reusan un ordinal",
    )
    args = parser.parse_args(argv)

    ruta_base = pathlib.Path(args.ratchet) if args.ratchet else pathlib.Path(RUTA_BASE)

    ficheros, faltantes = _recolectar(args.rutas or ["."], args.patron)
    if faltantes:
        print("RC 2: ruta inexistente: %s" % ", ".join(faltantes), file=sys.stderr)
        return 2
    if not ficheros:
        print(
            "RC 2: ningun fichero casa con `%s` bajo %s (sin sujeto no hay cero)"
            % (args.patron, ", ".join(args.rutas or ["."])),
            file=sys.stderr,
        )
        return 2

    cols, ilegibles = scanner.escanear(_leer(ficheros))
    if ilegibles:
        for ruta, motivo in sorted(ilegibles.items()):
            print("RC 2: no parsea %s (%s)" % (ruta, motivo), file=sys.stderr)
        return 2

    medido = _medido_por_fichero(cols)
    total = _resumen(medido)

    if args.write_baseline:
        _escribir_base(ruta_base, args.patron, medido)
        if args.json:
            print(
                json.dumps(
                    {"base": ruta_base.as_posix(), "deuda": _deuda_de(medido), "total": total, "rc": 0},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                "linea base escrita en %s: %d ficheros · sombra %d · ordinal %d"
                % (
                    ruta_base.as_posix(),
                    len(_deuda_de(medido)),
                    total["sombra"],
                    total["ordinal"],
                )
            )
        return 0

    base, error_base = _cargar_base(ruta_base)
    if error_base:
        print("RC 2: %s" % error_base, file=sys.stderr)
        return 2

    subidas, zombis = _comparar(medido, base)
    rc = 1 if (subidas or zombis) else 0
    if args.estricto and total[scanner.COMPARTIDO]:
        rc = 1

    if args.json:
        print(
            json.dumps(
                {
                    "archivos": len(ficheros),
                    "total": total,
                    "colisiones": [
                        {
                            "clase": c.clase,
                            "ruta": c.ruta,
                            "ambito": c.ambito,
                            "nombre": c.nombre,
                            "linea": c.linea,
                            "primera": c.primera,
                        }
                        for c in cols
                    ],
                    "subidas": subidas,
                    "zombis": zombis,
                    "base": ruta_base.as_posix(),
                    "rc": rc,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return rc

    print(
        "test-ordinal-ratchet: %d ficheros · sombra %d · ordinal %d · compartido %d"
        % (
            len(ficheros),
            total["sombra"],
            total["ordinal"],
            total["compartido"],
        )
    )
    for c in cols:
        print("  " + c.linea_de_reporte())
    for ruta, cuenta in sorted(subidas.items()):
        print(
            "  SUBE %s: %s"
            % (ruta, ", ".join("%s +%d" % (k, v) for k, v in sorted(cuenta.items())))
        )
    for ruta, cuenta in sorted(zombis.items()):
        print(
            "  ZOMBI %s: %s (la deuda ya no existe: quitala de la linea base)"
            % (ruta, ", ".join("%s -%d" % (k, v) for k, v in sorted(cuenta.items())))
        )
    if rc:
        print(
            "RC 1: %d ficheros suben y %d declaran deuda resuelta%s"
            % (
                len(subidas),
                len(zombis),
                " · --estricto cobra %d ordinales compartidos" % total[scanner.COMPARTIDO]
                if args.estricto and total[scanner.COMPARTIDO]
                else "",
            )
        )
    else:
        print("RC 0: sin colisiones nuevas sobre %s" % ruta_base.as_posix())
    return rc


if __name__ == "__main__":
    sys.exit(main())
