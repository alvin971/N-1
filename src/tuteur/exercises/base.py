"""Modèles d'exercices paramétriques.

Principes :
  * la solution est construite AVANT l'énoncé (on tire x puis on calcule c = a·x + b) ;
  * un exercice est identifié par (modèle, version, graine, difficulté) : reproductible,
    rien n'est stocké individuellement ;
  * contrainte de POUVOIR DIAGNOSTIQUE : on rejette tout exercice pour lequel une erreur
    typique produit la bonne réponse (il ne permettrait pas de la détecter), ou pour lequel
    deux erreurs typiques donnent la même réponse (on ne saurait pas laquelle) ;
  * les enseignants relisent les MODÈLES, jamais chaque exercice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

import sympy

from ..mathengine import SpecReponse, corriger, egalite_ensembles, equivalentes


@dataclass(frozen=True)
class Item:
    modele: str
    version: int
    graine: int
    difficulte: int
    kcs: tuple[str, ...]
    enonce: str
    spec: SpecReponse
    solution_redigee: tuple[str, ...] = ()
    choix: tuple[str, ...] = ()  # non vide → QCM

    @property
    def cle(self) -> str:
        return f"{self.modele}@v{self.version}#{self.graine}/d{self.difficulte}"

    @property
    def est_qcm(self) -> bool:
        return bool(self.choix)

    @property
    def proba_hasard(self) -> float:
        """Probabilité de réussir sans savoir (paramètre « guess »)."""
        if self.est_qcm:
            return 1.0 / len(self.choix)
        return 0.5 if self.spec.type == "booleen" else 0.02

    def corriger(self, saisie: str):
        return corriger(self.spec, saisie)


@dataclass(frozen=True)
class Brouillon:
    """Ce que renvoie la fonction de génération d'un modèle (avant contrôles)."""

    enonce: str
    spec: SpecReponse
    solution_redigee: tuple[str, ...] = ()


@dataclass(frozen=True)
class Modele:
    id: str
    version: int
    kcs: tuple[str, ...]  # Q-matrix : compétences sollicitées
    diagnostic: bool  # isole kcs[0] (les autres KC à un niveau trivial)
    generer: Callable[[random.Random, int], Brouillon]
    difficultes: tuple[int, ...] = (1, 2, 3)
    qcm_possible: bool = True
    temps_estime_s: int = 40
    erreurs: tuple[str, ...] = ()  # erreurs typiques que ce modèle sait produire
    # Compétences MOBILISÉES selon la difficulté : un exercice de haut niveau contient toutes ses
    # parties techniques (ex. résoudre 2(x − 3) = ½x + 4 mobilise distributivité, relatifs,
    # fractions, réduction…). Une réussite valide donc toutes ces acquisitions à la fois.
    mobilise: dict[int, tuple[str, ...]] = field(default_factory=dict)

    @property
    def kc_principale(self) -> str:
        return self.kcs[0]

    def kcs_mobilisees(self, difficulte: int) -> tuple[str, ...]:
        """Q-matrix effective à cette difficulté : KC principale d'abord, puis toutes les parties."""
        extra = tuple(k for k in self.mobilise.get(difficulte, ()) if k not in self.kcs)
        return self.kcs + extra

    def instancier(self, graine: int, difficulte: int = 1, qcm: bool = False, essais_max: int = 200) -> Item:
        if difficulte not in self.difficultes:
            difficulte = min(self.difficultes, key=lambda d: abs(d - difficulte))
        for essai in range(essais_max):
            rng = random.Random(f"{self.id}|{self.version}|{graine}|{difficulte}|{essai}")
            b = self.generer(rng, difficulte)
            if not diagnostique(b.spec):
                continue
            choix: tuple[str, ...] = ()
            if qcm and self.qcm_possible and b.spec.type != "booleen":
                choix = construire_qcm(b.spec, rng)
            return Item(self.id, self.version, graine, difficulte, self.kcs_mobilisees(difficulte), b.enonce, b.spec,
                        b.solution_redigee, choix)
        raise RuntimeError(f"{self.id} : aucun exercice diagnostique trouvé en {essais_max} essais")


def _egal(spec: SpecReponse, a, b) -> bool:
    if spec.type == "solutions":
        return egalite_ensembles(a, b)
    if spec.type == "booleen":
        return a == b
    return equivalentes(a, b)


def diagnostique(spec: SpecReponse) -> bool:
    reps = list(spec.erreurs.values())
    for r in reps:
        if _egal(spec, r, spec.valeur):
            return False
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            if _egal(spec, reps[i], reps[j]):
                return False
    return True


# ---------------------------------------------------------------------- QCM


def texte_valeur(v) -> str:
    """Affichage d'une valeur SymPy en notation scolaire relisible par le parseur."""
    import re

    if isinstance(v, (frozenset, set)):
        vals = sorted(v, key=lambda e: float(e))
        return " ; ".join(texte_valeur(e) for e in vals) if vals else "aucune solution"
    s = str(sympy.sympify(v)).replace("**", "^")
    s = re.sub(r"(\d)\*([a-z(])", r"\1\2", s)
    s = re.sub(r"\)\*\(", ")(", s)
    return s.replace("*", " × ")


def construire_qcm(spec: SpecReponse, rng: random.Random, n: int = 4) -> tuple[str, ...]:
    """Bonne réponse + réponses produites par les erreurs typiques + distracteurs proches."""
    options = [spec.valeur, *spec.erreurs.values()]
    distincts: list = []
    for o in options:
        if not any(_egal(spec, o, d) for d in distincts):
            distincts.append(o)
    k = 1
    while len(distincts) < n and k < 50:
        cand = _voisin(spec, k, rng)
        if cand is not None and not any(_egal(spec, cand, d) for d in distincts):
            distincts.append(cand)
        k += 1
    distincts = distincts[: max(n, 1 + len(spec.erreurs))]
    textes = [spec.texte_attendu if (i == 0 and spec.texte_attendu) else texte_valeur(o) for i, o in enumerate(distincts)]
    rng.shuffle(textes)
    return tuple(textes)


def _voisin(spec: SpecReponse, k: int, rng: random.Random):
    if spec.type == "solutions":
        vals = sorted(spec.valeur, key=float)  # type: ignore[arg-type]
        if not vals:
            return frozenset({sympy.Integer(rng.randint(-9, 9))})
        return frozenset(v + rng.choice([-k, k]) for v in vals)
    v = sympy.sympify(spec.valeur)
    if v.free_symbols:
        x = sorted(v.free_symbols, key=str)[0]
        return sympy.expand(v + rng.choice([-k, k]) * (x if k % 2 else 1))
    return v + rng.choice([-k, k])


# ---------------------------------------------------------------------- registre

REGISTRE: dict[str, Modele] = {}


def modele(id: str, kcs: list[str], *, version: int = 1, diagnostic: bool = True, erreurs: tuple[str, ...] = (),
           difficultes: tuple[int, ...] = (1, 2, 3), qcm_possible: bool = True, temps_estime_s: int = 40,
           mobilise: dict[int, tuple[str, ...]] | None = None):
    def deco(f: Callable[[random.Random, int], Brouillon]) -> Callable[[random.Random, int], Brouillon]:
        if id in REGISTRE:
            raise ValueError(f"modèle en double : {id}")
        REGISTRE[id] = Modele(id, version, tuple(kcs), diagnostic, f, difficultes, qcm_possible, temps_estime_s, erreurs,
                              dict(mobilise or {}))
        return f

    return deco


def modeles_pour(kc: str, diagnostic_seulement: bool = False) -> list[Modele]:
    return [m for m in REGISTRE.values() if kc in m.kcs and (m.kc_principale == kc) and (m.diagnostic or not diagnostic_seulement)]
