"""Prédicats de FORME sur l'AST.

L'équivalence mathématique ne suffit pas : si la consigne est « développer (x+2)² »,
la réponse « (x+2)² » est équivalente… et fausse. Chaque spécification de réponse déclare
les formes exigées ; elles sont vérifiées ici, sur l'arbre écrit par l'élève.
"""

from __future__ import annotations

from math import gcd
from typing import Callable

import sympy

from .ast import (
    Nombre,
    Noeud,
    Oppose,
    Produit,
    Puissance,
    Quotient,
    Variable,
    contient_somme,
    est_somme,
    facteurs,
    termes,
    vers_sympy,
)


def _sans_oppose(n: Noeud) -> Noeud:
    while isinstance(n, Oppose):
        n = n.arg
    return n


def _entier_litteral(n: Noeud) -> int | None:
    n = _sans_oppose(n)
    if isinstance(n, Nombre) and n.est_entier:
        return n.valeur.numerator
    return None


def est_entier(n: Noeud) -> bool:
    return _entier_litteral(n) is not None


def fraction_ecrite(n: Noeud) -> tuple[int, int] | None:
    """(numérateur, dénominateur) si n s'écrit a/b, -a/b, (-a)/b ou a/(-b) avec a, b entiers."""
    signe = 1
    while isinstance(n, Oppose):
        signe, n = -signe, n.arg
    if isinstance(n, Quotient):
        a, b = _entier_litteral(n.gauche), _entier_litteral(n.droite)
        if a is None or b is None:
            return None
        sa = -1 if isinstance(n.gauche, Oppose) else 1
        sb = -1 if isinstance(n.droite, Oppose) else 1
        return signe * sa * a, sb * b
    return None


def est_fraction_irreductible(n: Noeud) -> bool:
    """Entier, ou a/b avec PGCD(a, b) = 1 et b > 1."""
    if est_entier(n):
        return True
    f = fraction_ecrite(n)
    if f is None:
        return False
    a, b = f
    return b > 1 and gcd(a, b) == 1


def a_denominateur(d: int) -> Callable[[Noeud], bool]:
    def pred(n: Noeud) -> bool:
        f = fraction_ecrite(n)
        return f is not None and f[1] == d

    pred.__name__ = f"denominateur_{d}"
    return pred


def _est_monome(t: Noeud) -> bool:
    """Produit d'au plus un coefficient numérique et de puissances de variables distinctes."""
    if contient_somme(t):
        return False
    nb_coeffs = 0
    vus: set[str] = set()
    for f in facteurs(_sans_oppose(t)):
        f = _sans_oppose(f)
        if isinstance(f, Nombre) or (fraction_ecrite(f) is not None):
            nb_coeffs += 1
        elif isinstance(f, Variable):
            if f.nom in vus:
                return False
            vus.add(f.nom)
        elif isinstance(f, Puissance) and isinstance(f.base, Variable) and est_entier(f.exposant):
            if f.base.nom in vus:
                return False
            vus.add(f.base.nom)
        elif isinstance(f, Quotient) and isinstance(_sans_oppose(f.droite), Nombre):
            # x/2, 3x/4 : coefficient rationnel écrit comme une division
            if not _est_monome(f.gauche):
                return False
            nb_coeffs += 1
        else:
            return False
    return nb_coeffs <= 1


def est_developpee_reduite(n: Noeud) -> bool:
    """Somme de monômes sans parenthèse, chaque degré n'apparaissant qu'une fois, sans terme nul."""
    ts = termes(n)
    monomes = set()
    for _, t in ts:
        if not _est_monome(t):
            return False
        v = vers_sympy(t)
        if v == 0 and len(ts) > 1:
            return False
        cle = sympy.Mul.make_args(v)
        partie_litterale = tuple(sorted(str(f) for f in cle if not f.is_number))
        if partie_litterale in monomes:
            return False
        monomes.add(partie_litterale)
    return True


def est_factorisee(n: Noeud) -> bool:
    """Produit (au premier niveau) dont au moins un facteur est une somme, ou carré d'une somme."""
    n = _sans_oppose(n)
    if est_somme(n):
        return False
    if isinstance(n, Puissance):
        return est_somme(n.base)
    if not isinstance(n, Produit):
        return False
    fs = facteurs(n)
    return len(fs) >= 2 and any(est_somme(f) or (isinstance(f, Puissance) and est_somme(f.base)) for f in fs)


FORMES: dict[str, Callable[[Noeud], bool]] = {
    "entier": est_entier,
    "fraction_irreductible": est_fraction_irreductible,
    "developpee_reduite": est_developpee_reduite,
    "factorisee": est_factorisee,
}

MESSAGES_FORME = {
    "entier": "La réponse doit être écrite sous la forme d'un nombre entier.",
    "fraction_irreductible": "C'est la bonne valeur, mais la fraction doit être simplifiée au maximum (irréductible).",
    "developpee_reduite": "C'est équivalent, mais l'expression doit être développée et réduite.",
    "factorisee": "C'est équivalent, mais l'expression doit être factorisée.",
}


def predicat_forme(nom: str) -> Callable[[Noeud], bool]:
    if nom.startswith("denominateur:"):
        return a_denominateur(int(nom.split(":", 1)[1]))
    return FORMES[nom]


def message_forme(nom: str) -> str:
    if nom.startswith("denominateur:"):
        return f"C'est la bonne valeur, mais la fraction doit avoir {nom.split(':', 1)[1]} pour dénominateur."
    return MESSAGES_FORME[nom]
