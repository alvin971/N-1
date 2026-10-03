"""Vérification d'une résolution d'équation ligne par ligne (« model tracing »).

Chaque ligne doit avoir le MÊME ensemble de solutions que la précédente. La première ligne
qui change l'ensemble localise l'erreur ; on cherche alors quelle transformation fautive
(erreur typique exécutable) transforme la ligne précédente en la ligne écrite.
Tout est déterministe : le LLM ne sert, au plus, qu'à formuler le retour.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

import sympy

from .ast import Difference, Equation, ErreurMath, Noeud, Produit, Somme, Variable, en_texte, symbole, vers_sympy
from .equivalence import egalite_ensembles, equivalentes
from .parser import ErreurLecture, lire_equation


class StatutLigne(StrEnum):
    OK = "ok"
    ERREUR = "erreur"
    ILLISIBLE = "illisible"


@dataclass(frozen=True)
class VerdictLigne:
    index: int
    texte: str
    statut: StatutLigne
    erreur_type: str | None = None
    message: str = ""


@dataclass
class RapportEtapes:
    lignes: list[VerdictLigne] = field(default_factory=list)
    premiere_erreur: int | None = None
    terminee: bool = False  # dernière ligne de la forme « x = valeur »
    solution_finale_juste: bool = False

    @property
    def juste(self) -> bool:
        return self.premiere_erreur is None and self.terminee and self.solution_finale_juste


TOUS_REELS = "R"

# Erreurs typiques que le vérificateur d'étapes sait reconnaître (cf. content/erreurs_typiques.yaml).
ERREURS_ETAPES = (
    "eq.transposition_sans_changement_signe",
    "eq.soustrait_au_lieu_de_diviser",
    "eq.division_inversee",
    "eq.multiplie_au_lieu_de_diviser",
    "eq.signe_du_coefficient",
    "lit.distributivite_premier_terme_seulement",
    "lit.signe_moins_devant_parenthese",
)


def ensemble_solutions(eq: Equation, var: str = "x"):
    x = symbole(var)
    expr = sympy.expand(vers_sympy(eq.gauche) - vers_sympy(eq.droite))
    if expr == 0:
        return TOUS_REELS
    if not expr.has(x):
        return frozenset()
    sols = sympy.solve(sympy.Eq(expr, 0), x)
    return frozenset(s for s in sols if s.is_real is not False)


def _memes_solutions(a, b) -> bool:
    if a == TOUS_REELS or b == TOUS_REELS:
        return a == b
    return egalite_ensembles(a, b)


# ---------------------------------------------------------------------- erreurs de transformation


def _membres(eq: Equation) -> tuple[sympy.Expr, sympy.Expr]:
    return vers_sympy(eq.gauche), vers_sympy(eq.droite)


def _meme_equation(g1, d1, g2, d2) -> bool:
    return equivalentes(g1, g2) and equivalentes(d1, d2)


def _candidats_fautifs(prec: Equation, var: str) -> list[tuple[str, sympy.Expr, sympy.Expr]]:
    """Lignes que produirait une erreur typique appliquée à `prec`."""
    x = symbole(var)
    g, d = _membres(prec)
    out: list[tuple[str, sympy.Expr, sympy.Expr]] = []
    # 1. transposer un terme sans changer son signe
    for t in sympy.Add.make_args(sympy.expand(g)):
        if len(sympy.Add.make_args(sympy.expand(g))) > 1:
            out.append(("eq.transposition_sans_changement_signe", sympy.expand(g - t), sympy.expand(d + t)))
    for t in sympy.Add.make_args(sympy.expand(d)):
        if len(sympy.Add.make_args(sympy.expand(d))) > 1 or t.has(x):
            out.append(("eq.transposition_sans_changement_signe", sympy.expand(g + t), sympy.expand(d - t)))
    # 2. ax = b → x = b − a, x = a/b, x = b·a
    ge = sympy.expand(g)
    if ge.has(x) and sympy.Poly(ge, x).degree() == 1 and sympy.expand(ge - ge.coeff(x, 1) * x) == 0:
        a = ge.coeff(x, 1)
        if a not in (0, 1):
            out.append(("eq.soustrait_au_lieu_de_diviser", x, sympy.expand(d - a)))
            if d != 0:
                out.append(("eq.division_inversee", x, a / d))
            out.append(("eq.multiplie_au_lieu_de_diviser", x, d * a))
            out.append(("eq.signe_du_coefficient", x, -d / a))
    # 3. distributivité incomplète k(a + b) → ka + b  (sur l'AST : SymPy développe tout seul)
    for cote, membre, autre in (("g", prec.gauche, d), ("d", prec.droite, g)):
        for fautif in _distributivites_fautives(membre):
            f = vers_sympy(fautif)
            out.append(("lit.distributivite_premier_terme_seulement", *((f, autre) if cote == "g" else (autre, f))))
        for fautif in _moins_parenthese_fautifs(membre):
            f = vers_sympy(fautif)
            out.append(("lit.signe_moins_devant_parenthese", *((f, autre) if cote == "g" else (autre, f))))
    return out


def _distributivites_fautives(n: Noeud):
    """Toutes les variantes de n où UN produit k(a + b) est remplacé par ka + b."""
    match n:
        case Produit(gauche=k, droite=somme) if isinstance(somme, (Somme, Difference)):
            op = Somme if isinstance(somme, Somme) else Difference
            yield op(Produit(k, somme.gauche), somme.droite)
        case Produit(gauche=somme, droite=k) if isinstance(somme, (Somme, Difference)):
            op = Somme if isinstance(somme, Somme) else Difference
            yield op(Produit(somme.gauche, k), somme.droite)
    for champ in ("gauche", "droite", "arg"):
        enfant = getattr(n, champ, None)
        if isinstance(enfant, Noeud):
            for v in _distributivites_fautives(enfant):
                yield replace(n, **{champ: v})


def _moins_parenthese_fautifs(n: Noeud):
    """Variantes où « a − (b ± c) » est réécrit « a − b ± c » (signe de c non changé)."""
    if isinstance(n, Difference) and isinstance(n.droite, (Somme, Difference)):
        op = Somme if isinstance(n.droite, Somme) else Difference
        yield op(Difference(n.gauche, n.droite.gauche), n.droite.droite)
    for champ in ("gauche", "droite", "arg"):
        enfant = getattr(n, champ, None)
        if isinstance(enfant, Noeud):
            for v in _moins_parenthese_fautifs(enfant):
                yield replace(n, **{champ: v})


def _diagnostiquer(prec: Equation, cour: Equation, var: str) -> str | None:
    g2, d2 = _membres(cour)
    for id_err, g1, d1 in _candidats_fautifs(prec, var):
        if _meme_equation(g1, d1, g2, d2) or _meme_equation(g1, d1, d2, g2):
            return id_err
    return None


# ---------------------------------------------------------------------- vérification


def verifier_resolution(lignes: list[str], var: str = "x", solution_attendue=None) -> RapportEtapes:
    """`lignes[0]` est l'équation de départ (énoncé). Les suivantes sont celles de l'élève."""
    rapport = RapportEtapes()
    eqs: list[Equation | None] = []
    for i, texte in enumerate(lignes):
        try:
            eq = lire_equation(texte)
            ensemble_solutions(eq, var)
        except (ErreurLecture, ErreurMath, NotImplementedError) as e:
            rapport.lignes.append(VerdictLigne(i, texte, StatutLigne.ILLISIBLE, message=f"ligne illisible : {e}"))
            eqs.append(None)
            if rapport.premiere_erreur is None:
                rapport.premiere_erreur = i
            continue
        eqs.append(eq)
        if i == 0:
            rapport.lignes.append(VerdictLigne(i, texte, StatutLigne.OK, message="énoncé"))
            continue
        prec = next((e for e in reversed(eqs[:-1]) if e is not None), None)
        if prec is None or _memes_solutions(ensemble_solutions(prec, var), ensemble_solutions(eq, var)):
            rapport.lignes.append(VerdictLigne(i, texte, StatutLigne.OK))
            continue
        err = _diagnostiquer(prec, eq, var)
        msg = "Cette ligne n'a plus les mêmes solutions que la précédente."
        rapport.lignes.append(VerdictLigne(i, texte, StatutLigne.ERREUR, err, msg))
        if rapport.premiere_erreur is None:
            rapport.premiere_erreur = i

    derniere = eqs[-1] if eqs else None
    if derniere is not None and len(lignes) > 1:
        g, d = derniere.gauche, derniere.droite
        isolee = (g == Variable(var) and var not in en_texte(d)) or (d == Variable(var) and var not in en_texte(g))
        rapport.terminee = isolee
        if solution_attendue is not None:
            rapport.solution_finale_juste = _memes_solutions(ensemble_solutions(derniere, var), solution_attendue)
        else:
            rapport.solution_finale_juste = _memes_solutions(
                ensemble_solutions(derniere, var), ensemble_solutions(eqs[0], var)  # type: ignore[arg-type]
            ) if eqs[0] is not None else False
    return rapport
