"""Benchmark du diagnostic sur élèves simulés : exactitude vs nombre de questions.

Compare :
  * le diagnostic par gain d'information (src/tuteur/diagnostic) ;
  * la « descente séquentielle » naïve (échec → on teste les prérequis, réussite → on s'arrête),
    c'est-à-dire l'hypothèse initiale du projet, comme référence.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from ..contenu import Contenu
from ..diagnostic import Diagnostic, ParamsDiagnostic
from .eleves import PROFILS, EleveSimule, frontiere_vraie, generer_eleve


@dataclass
class Mesures:
    exactitude_kc: float  # part des KC correctement classées (maîtrisée / non maîtrisée)
    rappel_frontiere: float  # part des vraies lacunes racines retrouvées
    precision_frontiere: float
    questions: float
    rappel_avec_hypotheses: float = 0.0  # lacunes confirmées OU signalées comme hypothèses à vérifier

    def ligne(self, nom: str) -> str:
        return (f"{nom:<32} exactitude {self.exactitude_kc:6.1%} | lacunes confirmées {self.rappel_frontiere:6.1%} "
                f"(+ hypothèses {self.rappel_avec_hypotheses:6.1%}) | précision {self.precision_frontiere:6.1%} "
                f"| questions {self.questions:5.1f}")


def _pr(vraie: set[str], trouvee: set[str]) -> tuple[float, float]:
    rappel = len(vraie & trouvee) / len(vraie) if vraie else 1.0
    precision = len(vraie & trouvee) / len(trouvee) if trouvee else (1.0 if not vraie else 0.0)
    return rappel, precision


def diagnostiquer(contenu: Contenu, eleve: EleveSimule, cibles: list[str], niveau: str, graine: int,
                  params: ParamsDiagnostic = ParamsDiagnostic()) -> tuple[dict[str, bool], set[str], int, set[str]]:
    d = Diagnostic(contenu, cibles, niveau, params=params, graine=graine)
    while (item := d.prochaine_question()) is not None:
        d.enregistrer(item, item.corriger(eleve.repondre(item, contenu)))
    r = d.resultat()
    return {k: v >= 0.5 for k, v in r.marginales.items()}, set(r.frontiere), len(r.observations), set(r.hypotheses)


def descente_sequentielle(contenu: Contenu, eleve: EleveSimule, cibles: list[str], graine: int) -> tuple[dict[str, bool], set[str], int]:
    g = contenu.graphe
    kcs = g.sous_graphe(cibles)
    resultat: dict[str, bool] = {}
    n = 0
    pile = list(reversed(cibles))
    while pile:
        k = pile.pop()
        if k in resultat:
            continue
        m = contenu.modeles_diagnostic(k)[0]
        item = m.instancier(graine * 1000 + n, 2)
        n += 1
        ok = item.corriger(eleve.repondre(item, contenu)).juste
        resultat[k] = ok
        if not ok:
            pile.extend(p for p in g.prereqs(k, True) if p not in resultat)
    classes = {k: resultat.get(k, True) for k in kcs}
    frontiere = {k for k, ok in resultat.items() if not ok and all(resultat.get(p, True) for p in g.prereqs(k, True))}
    return classes, frontiere, n, set()


def evaluer(contenu: Contenu, chapitre: str = "equations_3e", niveau: str = "3e", n_eleves: int = 100,
            graine: int = 1, params: ParamsDiagnostic = ParamsDiagnostic(), profil: str | None = None) -> dict[str, Mesures]:
    """`profil` : « fort », « moyen », « fragile » (voir simulation.eleves.PROFILS), ou None pour le
    tirage historique (lacunes 0-2, KC du niveau non acquises avec probabilité 0,6)."""
    cibles = list(contenu.graphe.chapitres[chapitre].cibles)
    kcs = contenu.graphe.sous_graphe(cibles)
    rng = random.Random(graine)
    from dataclasses import replace

    strategies = {
        "descendante (présent d'abord)": lambda e, i: diagnostiquer(contenu, e, cibles, niveau, i, replace(params, strategie="descendante")),
        "exhaustive (tout le graphe)": lambda e, i: diagnostiquer(contenu, e, cibles, niveau, i, replace(params, strategie="exhaustive")),
        "descente séquentielle naïve": lambda e, i: descente_sequentielle(contenu, e, cibles, i),
    }
    res: dict[str, list[tuple[float, float, float, int, float]]] = {nom: [] for nom in strategies}
    for i in range(n_eleves):
        if profil is None:
            eleve = generer_eleve(contenu, cibles, niveau, rng)
        else:
            lacunes, p_niveau = PROFILS[profil]
            eleve = generer_eleve(contenu, cibles, niveau, rng, n_lacunes=lacunes, p_niveau=p_niveau)
        vraie = frontiere_vraie(contenu, eleve, kcs)
        for nom, f in strategies.items():
            e = EleveSimule(set(eleve.maitrisees), eleve.p_slip, eleve.p_erreur_typique, rng=random.Random(i))
            classes, frontiere, n, hypotheses = f(e, i)
            exact = sum(classes[k] == eleve.sait(k) for k in kcs) / len(kcs)
            rappel, precision = _pr(vraie, frontiere)
            rappel_h, _ = _pr(vraie, frontiere | hypotheses)
            res[nom].append((exact, rappel, precision, n, rappel_h))
    return {
        nom: Mesures(*(statistics.mean(v[j] for v in vals) for j in range(5)))  # type: ignore[arg-type]
        for nom, vals in res.items()
    }
