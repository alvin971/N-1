"""Élèves simulés PARAMÉTRIQUES (et non simulés par un LLM).

Usage légitime de la simulation : tester des algorithmes contre une vérité terrain connue.
Les élèves sont générés par un processus DIFFÉRENT de l'a priori du diagnostic (lacunes racines
qui se propagent aux descendants), pour ne pas commettre le « crime inverse » (évaluer un modèle
sur des données tirées de ce même modèle).

Les réponses produites sont des TEXTES passés dans le vrai correcteur : le pipeline testé est
celui de la production (parseur → SymPy → erreurs typiques → diagnostic).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..contenu import Contenu
from ..exercises import Item, texte_valeur
from ..exercises.base import _voisin
from ..graph import rang_niveau


@dataclass
class EleveSimule:
    maitrisees: set[str]
    p_slip: float = 0.08
    p_erreur_typique: float = 0.6
    p_apprentissage: float = 0.25  # P(acquérir la KC après une explication + pratique ciblée)
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    lacunes_racines: tuple[str, ...] = ()

    def sait(self, kc: str) -> bool:
        return kc in self.maitrisees

    def repondre(self, item: Item, contenu: Contenu) -> str:
        spec = item.spec
        kc = item.kcs[0]
        if self.sait(kc) and all(self.sait(k) for k in item.kcs[1:]):
            if self.rng.random() > self.p_slip:
                return self._juste(item)
            return self._faux(item)
        # erreurs typiques produites par une KC non maîtrisée (celle de l'exercice ou un prérequis)
        candidates = [e for e in spec.erreurs if not self.sait(contenu.erreurs[e].kc)]
        if candidates and self.rng.random() < self.p_erreur_typique:
            return texte_valeur(spec.erreurs[self.rng.choice(candidates)])
        if self.rng.random() < item.proba_hasard:
            return self._juste(item)
        return self._faux(item)

    def _juste(self, item: Item) -> str:
        if item.est_qcm:
            for c in item.choix:
                if item.corriger(c).juste:
                    return c
        if item.spec.type == "booleen":
            return "oui" if item.spec.valeur else "non"
        return item.spec.affichage()

    def _faux(self, item: Item) -> str:
        if item.spec.type == "booleen":
            return "non" if item.spec.valeur else "oui"
        if item.est_qcm:
            faux = [c for c in item.choix if not item.corriger(c).juste]
            return self.rng.choice(faux)
        return texte_valeur(_voisin(item.spec, self.rng.randint(1, 4), self.rng))

    def apprendre(self, kc: str, contenu: Contenu) -> None:
        """Après explication/pratique : peut acquérir la KC si ses prérequis forts sont acquis."""
        if kc in self.maitrisees:
            return
        if all(p in self.maitrisees for p in contenu.graphe.prereqs(kc, True)) and self.rng.random() < self.p_apprentissage:
            self.maitrisees.add(kc)


def generer_eleve(contenu: Contenu, cibles: list[str], niveau_eleve: str, rng: random.Random,
                  n_lacunes: tuple[int, int] = (0, 2)) -> EleveSimule:
    """Vérité terrain : 0 à 2 lacunes racines tirées dans le sous-graphe ; tous leurs descendants
    sont non maîtrisés ; les KC du niveau de l'élève sont non maîtrisées avec probabilité 0,6
    (chapitre pas encore travaillé) ; bruit : 3 % de KC « oubliées » isolées."""
    g = contenu.graphe
    kcs = g.sous_graphe(cibles)
    sous = set(kcs)
    lacunes = rng.sample(kcs, rng.randint(*n_lacunes))
    non_m: set[str] = set()
    for l in lacunes:
        non_m.add(l)
        non_m |= g.descendants(l, sous)
    for k in kcs:
        if rang_niveau(g.kcs[k].niveau) >= rang_niveau(niveau_eleve) and rng.random() < 0.6:
            non_m.add(k)
            non_m |= g.descendants(k, sous)
        elif rng.random() < 0.03:
            non_m.add(k)
    maitrisees = {k for k in kcs if k not in non_m}
    return EleveSimule(maitrisees, rng=random.Random(rng.random()), lacunes_racines=tuple(lacunes))


def frontiere_vraie(contenu: Contenu, eleve: EleveSimule, kcs: list[str]) -> set[str]:
    g = contenu.graphe
    return {k for k in kcs if not eleve.sait(k) and all(eleve.sait(p) for p in g.prereqs(k, True) if p in kcs)}
