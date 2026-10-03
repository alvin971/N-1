"""Lecture des saisies d'élèves en notation scolaire française.

Gère : virgule décimale (3,5), ×, ·, *, ÷, « : » comme division, −, –, ², ³, ^, √, racine(…),
multiplication implicite (2x, 3(x+1), (x+1)(x-2), xy), séparateur de milliers (1 000), [ ].

Analyseur descendant écrit à la main : aucune exécution de code, messages d'erreur en français.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .ast import (
    Difference,
    Equation,
    Nombre,
    Noeud,
    Oppose,
    Produit,
    Puissance,
    Quotient,
    Racine,
    Somme,
    Variable,
)

LONGUEUR_MAX = 200


class ErreurLecture(ValueError):
    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.position = position


@dataclass(frozen=True)
class Jeton:
    type: str  # NB, ID, FONC, OP, POW, LPAR, RPAR, EGAL, RAC
    valeur: str
    pos: int


_NORMALISATION = {
    "−": "-", "–": "-", "—": "-", "×": "*", "·": "*", "∙": "*", "÷": "/", ":": "/",
    "[": "(", "]": ")", "{": "(", "}": ")", " ": " ", " ": " ",
}
_FONCTIONS = {"racine", "sqrt", "rac"}
_RE_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")
_RE_MILLIERS = re.compile(r" (\d{3})(?![\d.,])")


def _jetons(texte: str) -> list[Jeton]:
    if len(texte) > LONGUEUR_MAX:
        raise ErreurLecture("saisie trop longue")
    s = "".join(_NORMALISATION.get(c, c) for c in texte)
    out: list[Jeton] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        m = _RE_NOMBRE.match(s, i)
        if m:
            nb = m.group()
            j = m.end()
            # séparateur de milliers « 1 000 » : seulement si l'entier n'a pas de partie décimale
            while "," not in nb and "." not in nb:
                mm = _RE_MILLIERS.match(s, j)
                if not mm:
                    break
                nb += mm.group(1)
                j = mm.end()
            out.append(Jeton("NB", nb, i))
            i = j
            continue
        if c.isalpha():
            j = i
            while j < len(s) and s[j].isalpha():
                j += 1
            mot = s[i:j]
            if mot.lower() in _FONCTIONS:
                out.append(Jeton("FONC", mot.lower(), i))
            else:
                # « xy » = x × y : chaque lettre est une variable
                out.extend(Jeton("ID", lettre, i + k) for k, lettre in enumerate(mot))
            i = j
            continue
        if c in "+-*/":
            out.append(Jeton("OP", c, i))
        elif c == "^":
            out.append(Jeton("OP", "^", i))
        elif c in "²³":
            out.append(Jeton("POW", "2" if c == "²" else "3", i))
        elif c == "(":
            out.append(Jeton("LPAR", c, i))
        elif c == ")":
            out.append(Jeton("RPAR", c, i))
        elif c == "=":
            out.append(Jeton("EGAL", c, i))
        elif c == "√":
            out.append(Jeton("RAC", c, i))
        else:
            raise ErreurLecture(f"caractère non reconnu « {c} »", i)
        i += 1
    return out


def _nombre(texte: str) -> Nombre:
    return Nombre(Fraction(texte.replace(",", ".")), texte)


class _Analyseur:
    def __init__(self, texte: str):
        self.j = _jetons(texte)
        self.i = 0
        if not self.j:
            raise ErreurLecture("saisie vide")

    # -------------------------------------------------------------- utilitaires
    def voir(self) -> Jeton | None:
        return self.j[self.i] if self.i < len(self.j) else None

    def prendre(self) -> Jeton:
        t = self.voir()
        if t is None:
            raise ErreurLecture("expression incomplète")
        self.i += 1
        return t

    def attendre(self, type_: str, valeur: str | None = None) -> Jeton:
        t = self.voir()
        if t is None or t.type != type_ or (valeur is not None and t.valeur != valeur):
            attendu = {"RPAR": "« ) »", "LPAR": "« ( »"}.get(type_, valeur or type_)
            raise ErreurLecture(f"{attendu} attendu", t.pos if t else None)
        return self.prendre()

    def est_op(self, *ops: str) -> bool:
        t = self.voir()
        return t is not None and t.type == "OP" and t.valeur in ops

    # -------------------------------------------------------------- grammaire
    def equation_ou_expression(self) -> Noeud | Equation:
        g = self.expr()
        t = self.voir()
        if t is not None and t.type == "EGAL":
            self.prendre()
            d = self.expr()
            if self.voir() is not None:
                raise ErreurLecture("un seul signe « = » par ligne", self.voir().pos)
            return Equation(g, d)
        if t is not None:
            raise ErreurLecture(f"« {t.valeur} » inattendu", t.pos)
        return g

    def expr(self) -> Noeud:
        n = self.terme()
        while self.est_op("+", "-"):
            op = self.prendre().valeur
            d = self.terme()
            n = Somme(n, d) if op == "+" else Difference(n, d)
        return n

    def terme(self) -> Noeud:
        n = self.unaire()
        while True:
            if self.est_op("*", "/"):
                op = self.prendre().valeur
                d = self.unaire()
                n = Produit(n, d) if op == "*" else Quotient(n, d)
                continue
            t = self.voir()
            if t is not None and t.type in ("ID", "LPAR", "RAC", "FONC"):
                n = Produit(n, self.puissance(), implicite=True)
                continue
            if t is not None and t.type == "NB":
                raise ErreurLecture("deux nombres côte à côte : il manque une opération", t.pos)
            return n

    def unaire(self) -> Noeud:
        if self.est_op("-"):
            self.prendre()
            return Oppose(self.unaire())
        if self.est_op("+"):
            self.prendre()
            return self.unaire()
        return self.puissance()

    def puissance(self) -> Noeud:
        base = self.postfixe()
        if self.est_op("^"):
            self.prendre()
            return Puissance(base, self.unaire())
        return base

    def postfixe(self) -> Noeud:
        n = self.atome()
        while (t := self.voir()) is not None and t.type == "POW":
            self.prendre()
            n = Puissance(n, Nombre(Fraction(int(t.valeur)), t.valeur))
        return n

    def atome(self) -> Noeud:
        t = self.prendre()
        if t.type == "NB":
            return _nombre(t.valeur)
        if t.type == "ID":
            return Variable(t.valeur)
        if t.type == "LPAR":
            n = self.expr()
            self.attendre("RPAR")
            return n
        if t.type == "RAC":
            if (s := self.voir()) is not None and s.type == "LPAR":
                return Racine(self.atome())
            return Racine(self.postfixe())
        if t.type == "FONC":
            self.attendre("LPAR")
            n = self.expr()
            self.attendre("RPAR")
            return Racine(n)
        raise ErreurLecture(f"« {t.valeur} » inattendu", t.pos)


def lire(texte: str) -> Noeud | Equation:
    """Lit une expression ou une équation. Lève ErreurLecture si illisible."""
    return _Analyseur(texte).equation_ou_expression()


def lire_expression(texte: str) -> Noeud:
    r = lire(texte)
    if isinstance(r, Equation):
        raise ErreurLecture("une expression est attendue, pas une équation")
    return r


def lire_equation(texte: str) -> Equation:
    r = lire(texte)
    if not isinstance(r, Equation):
        raise ErreurLecture("une équation (avec « = ») est attendue")
    return r
