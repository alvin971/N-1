"""Équivalence de valeurs.

Pour les polynômes et fractions rationnelles (l'essentiel du collège), `cancel` décide
exactement. Pour le reste (racines…), `simplify` puis contrôle numérique en points
rationnels pseudo-aléatoires (graine fixe → reproductible).
"""

from __future__ import annotations

import random

import sympy

_POINTS = [sympy.Rational(n, d) for n, d in [(7, 3), (-5, 2), (11, 7), (-13, 5), (3, 11), (17, 4)]]


def equivalentes(a: sympy.Expr, b: sympy.Expr) -> bool:
    d = sympy.sympify(a) - sympy.sympify(b)
    if d == 0:
        return True
    if not d.has(sympy.Pow) or all(p.exp.is_integer for p in d.atoms(sympy.Pow)):
        return sympy.cancel(sympy.together(d)) == 0
    if sympy.simplify(d) == 0:
        return True
    return _numeriquement_nul(d)


def _numeriquement_nul(d: sympy.Expr) -> bool:
    symboles = sorted(d.free_symbols, key=str)
    rng = random.Random(0)
    for _ in range(len(_POINTS)):
        sub = {s: rng.choice(_POINTS) for s in symboles}
        try:
            v = complex(d.subs(sub).evalf(30))
        except (TypeError, ZeroDivisionError):
            continue
        if abs(v) > 1e-12:
            return False
    return True


def egalite_ensembles(a: set | frozenset, b: set | frozenset) -> bool:
    if len(a) != len(b):
        return False
    restants = list(b)
    for x in a:
        for i, y in enumerate(restants):
            if equivalentes(x, y):
                restants.pop(i)
                break
        else:
            return False
    return True
