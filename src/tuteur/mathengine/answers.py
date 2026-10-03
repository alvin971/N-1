"""Spécification de réponse et correction.

Le verdict a QUATRE issues (et non deux) :
  CORRECT · FORME (valeur juste, forme non conforme) · INCORRECT · ILLISIBLE.
Une réponse incorrecte est confrontée aux réponses produites par les erreurs typiques
de l'exercice : une réponse fausse précise est un signal diagnostique fort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

import sympy

from .ast import Equation, ErreurMath, Noeud, Variable, en_texte, variables, vers_sympy
from .equivalence import egalite_ensembles, equivalentes
from .forms import message_forme, predicat_forme
from .parser import ErreurLecture, lire, lire_expression


class Statut(StrEnum):
    CORRECT = "correct"
    FORME = "forme_non_conforme"
    INCORRECT = "incorrect"
    ILLISIBLE = "illisible"


@dataclass(frozen=True)
class Verdict:
    statut: Statut
    message: str
    erreur_type: str | None = None
    lu: str | None = None

    @property
    def juste(self) -> bool:
        return self.statut is Statut.CORRECT


TypeReponse = Literal["expression", "solutions", "booleen"]


@dataclass(frozen=True)
class SpecReponse:
    type: TypeReponse
    valeur: object  # sympy.Expr | frozenset[sympy.Expr] | bool
    formes: tuple[str, ...] = ()
    erreurs: dict[str, object] = field(default_factory=dict)  # id erreur typique -> réponse produite
    variable: str = "x"
    texte_attendu: str | None = None  # bonne réponse écrite dans la forme exigée (sinon déduite de `valeur`)

    def affichage(self) -> str:
        if self.texte_attendu:
            return self.texte_attendu
        if self.type == "booleen":
            return "oui" if self.valeur else "non"
        if self.type == "solutions":
            vals = sorted(self.valeur, key=lambda v: float(v))  # type: ignore[arg-type]
            if not vals:
                return "aucune solution"
            return " ou ".join(f"{self.variable} = {_texte_sympy(v)}" for v in vals)
        return _texte_sympy(self.valeur)  # type: ignore[arg-type]


def _texte_sympy(v: sympy.Expr) -> str:
    s = str(v).replace("**", "^").replace("*", "×")
    return s


# ---------------------------------------------------------------------- lecture des ensembles

_VIDE = re.compile(r"^(s\s*=\s*)?(∅|\{\s*\}|aucune solution|pas de solution|il n'y a pas de solution)$", re.I)
_SEP = re.compile(r";|\bou\b|\bet\b", re.I)


def lire_solutions(texte: str, var: str = "x") -> list[Noeud]:
    t = texte.strip()
    if _VIDE.match(t):
        return []
    t = re.sub(r"^\s*s\s*=\s*", "", t, flags=re.I)
    t = t.replace("{", " ").replace("}", " ")
    morceaux = [m.strip() for m in _SEP.split(t) if m.strip()]
    if not morceaux:
        raise ErreurLecture("aucune valeur lue")
    valeurs: list[Noeud] = []
    for m in morceaux:
        r = lire(m)
        if isinstance(r, Equation):
            if r.gauche == Variable(var):
                r = r.droite
            elif r.droite == Variable(var):
                r = r.gauche
            else:
                raise ErreurLecture(f"écris la solution sous la forme « {var} = … »")
        if variables(r):
            raise ErreurLecture(f"la solution ne doit pas contenir de lettre (écris {var} = valeur)")
        valeurs.append(r)
    return valeurs


# ---------------------------------------------------------------------- correction


def corriger(spec: SpecReponse, saisie: str) -> Verdict:
    try:
        if spec.type == "booleen":
            return _corriger_booleen(spec, saisie)
        if spec.type == "solutions":
            return _corriger_solutions(spec, saisie)
        return _corriger_expression(spec, saisie)
    except ErreurLecture as e:
        return Verdict(Statut.ILLISIBLE, f"Je n'arrive pas à lire ta réponse : {e}.")
    except ErreurMath as e:
        return Verdict(Statut.INCORRECT, f"Calcul impossible : {e}.")


def _erreur_reconnue(spec: SpecReponse, valeur: object, egal) -> str | None:
    for id_erreur, rep in spec.erreurs.items():
        try:
            if egal(valeur, rep):
                return id_erreur
        except (TypeError, ValueError):
            continue
    return None


def _corriger_booleen(spec: SpecReponse, saisie: str) -> Verdict:
    s = saisie.strip().lower()
    if s in {"oui", "vrai", "o", "v", "yes"}:
        rep = True
    elif s in {"non", "faux", "n", "f", "no"}:
        rep = False
    else:
        raise ErreurLecture("réponds par oui ou par non")
    if rep == spec.valeur:
        return Verdict(Statut.CORRECT, "Exact.", lu=s)
    return Verdict(Statut.INCORRECT, "Ce n'est pas la bonne réponse.", _erreur_reconnue(spec, rep, lambda a, b: a == b), s)


def _corriger_expression(spec: SpecReponse, saisie: str) -> Verdict:
    noeud = lire_expression(saisie)
    lu = en_texte(noeud)
    val = vers_sympy(noeud)
    if not equivalentes(val, spec.valeur):  # type: ignore[arg-type]
        err = _erreur_reconnue(spec, val, equivalentes)
        return Verdict(Statut.INCORRECT, "Ce n'est pas la bonne réponse.", err, lu)
    for f in spec.formes:
        if not predicat_forme(f)(noeud):
            return Verdict(Statut.FORME, message_forme(f), None, lu)
    return Verdict(Statut.CORRECT, "Exact.", lu=lu)


def _corriger_solutions(spec: SpecReponse, saisie: str) -> Verdict:
    noeuds = lire_solutions(saisie, spec.variable)
    vals = frozenset(vers_sympy(n) for n in noeuds)
    attendu: frozenset = spec.valeur  # type: ignore[assignment]
    lu = " ; ".join(en_texte(n) for n in noeuds) or "∅"
    if not egalite_ensembles(vals, attendu):
        err = _erreur_reconnue(spec, vals, egalite_ensembles)
        if err is None and vals and len(vals) < len(attendu) and all(any(equivalentes(v, a) for a in attendu) for v in vals):
            return Verdict(Statut.INCORRECT, "C'est juste, mais il manque au moins une solution.", None, lu)
        return Verdict(Statut.INCORRECT, "Ce n'est pas la bonne solution.", err, lu)
    for n in noeuds:
        for f in spec.formes:
            if not predicat_forme(f)(n):
                return Verdict(Statut.FORME, message_forme(f), None, lu)
    return Verdict(Statut.CORRECT, "Exact.", lu=lu)


def valeur_de(texte: str) -> sympy.Expr:
    """Raccourci pour les tests et le contenu : lit et évalue une expression."""
    return vers_sympy(lire_expression(texte))
