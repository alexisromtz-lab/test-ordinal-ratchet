# test-ordinal-ratchet

Un lector estático para suites de prueba cuyo **nombre es un identificador** —`test_36_algo`— y
que, al fusionar ramas, puede dejar de ser inyectivo sin que git diga nada.

Git compara texto. Dos ramas que añaden `def test_36_a` y `def test_36_b` en puntos distintos del
mismo fichero fusionan **sin conflicto**, y el resultado no es el mismo tipo de defecto según dónde
caigan:

| clase | qué pasó | ¿alguna prueba deja de correr? |
|---|---|---|
| `sombra` | mismo nombre, **mismo ámbito** | **sí**: Python deja viva la última, la primera desaparece |
| `ordinal` | nombres distintos, **mismo ordinal, mismo ámbito** | no, pero `-k test_36` y los informes ya no distinguen |
| `compartido` | mismo ordinal, **clases distintas del mismo fichero** | no: ámbitos separados, ambas corren |

El caso que originó la herramienta fue un `compartido`: dos clases del mismo fichero declarando
`test_36`, git con cero conflictos textuales, las dos pruebas corriendo. La conclusión honesta es
que la ambigüedad de ordinal **no** era una prueba perdida — y por eso la herramienta separa las
tres clases en vez de contarlas juntas.

## Instalación

Sin dependencias en tiempo de ejecución, Python ≥ 3.9:

```console
$ pip install -e .
$ test-ordinal-ratchet tests
test-ordinal-ratchet: 319 ficheros · sombra 0 · ordinal 39 · compartido 57
```

Sin instalar nada:

```console
$ python -m ordinal_ratchet tests
```

(Todavía no está publicado en PyPI, así que `uvx test-ordinal-ratchet` aún no resuelve. `pip
install -e .` y `python -m ordinal_ratchet` funcionan hoy.)

## Contrato de salida

| RC | significado |
|---|---|
| `0` | nada sube sobre la línea base declarada (que puede ser cero) |
| `1` | una colisión **nueva**, un contador por encima de la base, o deuda declarada que ya no existe |
| `2` | uso inválido · **ningún** fichero de prueba · un fichero que no parsea |

`RC 2` existe para que la ausencia de sujeto no se lea como cero: si el glob no encuentra ficheros,
o un fichero no parsea, no hay medición y la herramienta se niega a decir «limpio».

Un `compartido` **no** hace fallar: es legal y se publica como recuento. Con `--estricto` sí falla,
para equipos que quieran ordinales únicos por fichero.

## El trinquete

La deuda heredada se congela una vez y sólo puede bajar:

```console
$ test-ordinal-ratchet tests --write-baseline     # escribe .ordinal-ratchet.json
```

```json
{
  "version": 1,
  "patron": "test_*.py",
  "deuda": {
    "test_orden_de_arranque.py": { "ordinal": 2 }
  }
}
```

De ahí en adelante:

- más colisiones que la base ⇒ `RC 1` (`SUBE`);
- **menos** colisiones que la base ⇒ `RC 1` (`ZOMBI`): una deuda que ya no existe y sigue declarada
  es deuda zombi, y una lista de deuda que no se poda deja de ser evidencia.

Las claves son rutas **relativas** al argumento, no absolutas, para que la base congelada en una
máquina siga leyéndose al clonar.

## En GitHub Actions

```yaml
name: ordinal-ratchet
on: [push, pull_request]
jobs:
  ratchet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install .
      - run: test-ordinal-ratchet tests
```

## Medición real

Sobre un corpus de 319 ficheros `tests/test_*.py` (2 098 pruebas), `ast` sobre el árbol fusionado:

- `sombra 0`
- `ordinal 39` en 16 ficheros — 27 son la convención deliberada `test_NNb` (una variante del mismo
  ordinal dentro de la misma clase: la herramienta la reporta porque `-k test_03` casa las dos), 12
  son números reusados con nombres distintos
- `compartido 57`

Esa distinción es la que hace útil el recuento: 57 usos legales de un ordinal entre clases se
verían idénticos a 57 pruebas perdidas si el lector contara sólo números.

## Límites declarados

- **No ejecuta nada.** Lee `def`/`async def test*` en ámbito de módulo y de clase. No sabe nada de
  pruebas generadas en tiempo de ejecución (bucles, `setattr`, factorías, `parametrize`).
- **Un fichero es un universo.** Dos ficheros distintos pueden tener cada uno su `test_36`: son
  ámbitos separados y no se reportan.
- **Parsea, no adivina.** Un fichero con sintaxis que el intérprete en curso no entiende da `RC 2`,
  nunca «cero colisiones».
- El ordinal es el prefijo `test_<dígitos>`; `test_caso_36` no tiene ordinal.

## Licencia

MIT.
