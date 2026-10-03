"""Arbre syntaxique propre au tuteur.

On ne passe PAS par `sympy.parse_expr` / `sympify` : ils utilisent `eval` (dangereux sur une
saisie utilisateur) et évaluent automatiquement (2/4 devient 1/2), ce qui détruit la FORME
écrite par l'élève. L'AST conserve la forme ; `vers_sympy` donne la valeur.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import sympy


class ErreurMath(ValueError):
    """Erreur de calcul (division par zéro…) distincte d'une erreur de lecture."""


@dataclass(frozen=True)
class Noeud:
    pass


@dataclass(frozen=True)
class Nombre(Noeud):
    valeur: Fraction
    texte: str

    @property
    def est_entier(self) -> bool:
        return self.valeur.denominator == 1 and "," not in self.texte and "." not in self.texte


@dataclass(frozen=True)
class Variable(Noeud):
    nom: str


@dataclass(frozen=True)
class Oppose(Noeud):
    arg: Noeud


@dataclass(frozen=True)
class Somme(Noeud):
    gauche: Noeud
    droite: Noeud


@dataclass(frozen=True)
class Difference(Noeud):
    gauche: Noeud
    droite: Noeud


@dataclass(frozen=True)
class Produit(Noeud):
    gauche: Noeud
    droite: Noeud
    implicite: bool = False


@dataclass(frozen=True)
class Quotient(Noeud):
    gauche: Noeud
    droite: Noeud


@dataclass(frozen=True)
class Puissance(Noeud):
    base: Noeud
    exposant: Noeud


@dataclass(frozen=True)
class Racine(Noeud):
    arg: Noeud


@dataclass(frozen=True)
class Equation:
    gauche: Noeud
    droite: Noeud


SYMBOLES: dict[str, sympy.Symbol] = {}


def symbole(nom: str) -> sympy.Symbol:
    if nom not in SYMBOLES:
        SYMBOLES[nom] = sympy.Symbol(nom)
    return SYMBOLES[nom]


def vers_sympy(n: Noeud) -> sympy.Expr:
    match n:
        case Nombre(valeur=v):
            return sympy.Rational(v.numerator, v.denominator)
        case Variable(nom=nom):
            return symbole(nom)
        case Oppose(arg=a):
            return -vers_sympy(a)
        case Somme(gauche=g, droite=d):
            return vers_sympy(g) + vers_sympy(d)
        case Difference(gauche=g, droite=d):
            return vers_sympy(g) - vers_sympy(d)
        case Produit(gauche=g, droite=d):
            return vers_sympy(g) * vers_sympy(d)
        case Quotient(gauche=g, droite=d):
            den = vers_sympy(d)
            if den == 0:
                raise ErreurMath("division par zéro")
            return vers_sympy(g) / den
        case Puissance(base=b, exposant=e):
            base, exp = vers_sympy(b), vers_sympy(e)
            if base == 0 and exp.is_number and exp <= 0:
                raise ErreurMath("0 élevé à une puissance négative ou nulle")
            return base**exp
        case Racine(arg=a):
            return sympy.sqrt(vers_sympy(a))
    raise TypeError(f"nœud inconnu : {n!r}")


# ---------------------------------------------------------------------- outils de forme


def termes(n: Noeud) -> list[tuple[int, Noeud]]:
    """Aplati les sommes/différences de premier niveau : [(signe, terme), …]."""
    match n:
        case Somme(gauche=g, droite=d):
            return termes(g) + termes(d)
        case Difference(gauche=g, droite=d):
            return termes(g) + [(-s, t) for s, t in termes(d)]
        case Oppose(arg=a) if isinstance(a, (Somme, Difference)):
            return [(-s, t) for s, t in termes(a)]
    return [(1, n)]


def facteurs(n: Noeud) -> list[Noeud]:
    match n:
        case Produit(gauche=g, droite=d):
            return facteurs(g) + facteurs(d)
    return [n]


def est_somme(n: Noeud) -> bool:
    while isinstance(n, Oppose):
        n = n.arg
    return isinstance(n, (Somme, Difference))


def contient_somme(n: Noeud) -> bool:
    match n:
        case Somme() | Difference():
            return True
        case Oppose(arg=a) | Racine(arg=a):
            return contient_somme(a)
        case Produit(gauche=g, droite=d) | Quotient(gauche=g, droite=d):
            return contient_somme(g) or contient_somme(d)
        case Puissance(base=b, exposant=e):
            return contient_somme(b) or contient_somme(e)
    return False


def variables(n: Noeud) -> set[str]:
    match n:
        case Variable(nom=nom):
            return {nom}
        case Nombre():
            return set()
        case Oppose(arg=a) | Racine(arg=a):
            return variables(a)
        case Puissance(base=b, exposant=e):
            return variables(b) | variables(e)
        case Somme(gauche=g, droite=d) | Difference(gauche=g, droite=d) | Produit(gauche=g, droite=d) | Quotient(gauche=g, droite=d):
            return variables(g) | variables(d)
    return set()


def en_texte(n: Noeud) -> str:
    """Rendu lisible (notation scolaire) — utilisé pour les messages et la journalisation."""

    def par(x: Noeud, cond: bool) -> str:
        s = en_texte(x)
        return f"({s})" if cond else s

    match n:
        case Nombre(texte=t):
            return t
        case Variable(nom=nom):
            return nom
        case Oppose(arg=a):
            return "-" + par(a, isinstance(a, (Somme, Difference, Oppose)))
        case Somme(gauche=g, droite=d):
            return f"{en_texte(g)} + {par(d, isinstance(d, Oppose))}"
        case Difference(gauche=g, droite=d):
            return f"{en_texte(g)} - {par(d, isinstance(d, (Somme, Difference, Oppose)))}"
        case Produit(gauche=g, droite=d, implicite=imp):
            gs = par(g, isinstance(g, (Somme, Difference)))
            ds = par(d, isinstance(d, (Somme, Difference, Oppose)))
            return f"{gs}{ds}" if imp else f"{gs} × {ds}"
        case Quotient(gauche=g, droite=d):
            return f"{par(g, isinstance(g, (Somme, Difference)))}/{par(d, not isinstance(d, (Nombre, Variable)))}"
        case Puissance(base=b, exposant=e):
            return f"{par(b, not isinstance(b, (Nombre, Variable)))}^{par(e, not isinstance(e, (Nombre, Variable)))}"
        case Racine(arg=a):
            return f"√({en_texte(a)})"
    raise TypeError(n)
