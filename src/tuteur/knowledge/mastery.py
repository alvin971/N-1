"""État de maîtrise d'un élève et critères de maîtrise.

Une seule bonne réponse ne suffit JAMAIS. Une KC est « maîtrisée » si TOUTES les conditions :
  1. P(L) ≥ seuil (0,95) ;
  2. au moins 3 réussites sans aide ;
  3. au moins 2 variantes différentes réussies (modèle × difficulté) — pas un seul format ;
  4. au moins une réussite au niveau de difficulté cible ;
  5. aucune erreur typique dans les 3 dernières tentatives.
Puis deux niveaux supplémentaires :
  - CONSOLIDÉE : nouvelle réussite au moins 1 jour après la maîtrise (rétention) ;
  - TRANSFÉRÉE : réussite dans un exercice d'une KC parente qui la mobilise.
Une KC seulement inférée par le diagnostic est « PRÉSUMÉE » (pas maîtrisée au sens strict).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from ..mathengine import Statut
from .bkt import PARAMS_DEFAUT, ParamsBKT, mise_a_jour


class Niveau(StrEnum):
    NON_EVALUEE = "non_evaluee"
    A_TRAVAILLER = "a_travailler"
    EN_COURS = "en_cours"
    PRESUMEE = "presumee"
    MAITRISEE = "maitrisee"
    CONSOLIDEE = "consolidee"
    TRANSFEREE = "transferee"


@dataclass(frozen=True)
class CriteresMaitrise:
    seuil: float = 0.95
    seuil_presume: float = 0.85
    seuil_lacune: float = 0.40
    reussites_min: int = 3
    variantes_min: int = 2
    difficulte_cible: int = 2
    fenetre_erreurs: int = 3
    delai_consolidation: timedelta = timedelta(days=1)


CRITERES_DEFAUT = CriteresMaitrise()


@dataclass(frozen=True)
class Tentative:
    item: str  # clé reproductible modèle@version#graine/difficulté
    modele: str
    difficulte: int
    statut: Statut
    erreur_type: str | None
    aide: bool
    quand: datetime
    principale: bool = True  # la KC est-elle la KC principale de l'exercice ?


@dataclass
class EtatKC:
    kc: str
    p: float
    tentatives: list[Tentative] = field(default_factory=list)
    maitrisee_le: datetime | None = None
    consolidee: bool = False
    transferee: bool = False

    def reussites(self) -> list[Tentative]:
        return [t for t in self.tentatives if t.principale and t.statut is Statut.CORRECT and not t.aide]

    def niveau(self, c: CriteresMaitrise = CRITERES_DEFAUT) -> Niveau:
        if self.maitrisee_le is not None:
            if self.transferee:
                return Niveau.TRANSFEREE
            if self.consolidee:
                return Niveau.CONSOLIDEE
            return Niveau.MAITRISEE
        if not self.tentatives:
            return Niveau.NON_EVALUEE if self.p < c.seuil_presume else Niveau.PRESUMEE
        if self.p >= c.seuil_presume:
            return Niveau.PRESUMEE
        if self.p < c.seuil_lacune:
            return Niveau.A_TRAVAILLER
        return Niveau.EN_COURS

    def criteres_remplis(self, c: CriteresMaitrise = CRITERES_DEFAUT) -> dict[str, bool]:
        ok = self.reussites()
        recentes = [t for t in self.tentatives if t.principale][-c.fenetre_erreurs:]
        return {
            "probabilite": self.p >= c.seuil,
            "reussites": len(ok) >= c.reussites_min,
            "variantes": len({(t.modele, t.difficulte) for t in ok}) >= c.variantes_min,
            "difficulte_cible": any(t.difficulte >= c.difficulte_cible for t in ok),
            "sans_erreur_typique_recente": not any(t.erreur_type for t in recentes),
        }

    def est_maitrisee(self, c: CriteresMaitrise = CRITERES_DEFAUT) -> bool:
        return self.maitrisee_le is not None or all(self.criteres_remplis(c).values())


@dataclass
class ProfilEleve:
    """État pédagogique d'un élève, indexé par identifiant PSEUDONYME (jamais le nom)."""

    eleve: str
    niveau_scolaire: str
    etats: dict[str, EtatKC] = field(default_factory=dict)

    def etat(self, kc: str, prior: float) -> EtatKC:
        if kc not in self.etats:
            self.etats[kc] = EtatKC(kc, prior)
        return self.etats[kc]

    def enregistrer(
        self,
        kc: str,
        prior: float,
        tentative: Tentative,
        p_guess: float,
        params: ParamsBKT = PARAMS_DEFAUT,
        criteres: CriteresMaitrise = CRITERES_DEFAUT,
        apprentissage: bool = True,
    ) -> EtatKC:
        e = self.etat(kc, prior)
        maitrisee_avant = e.maitrisee_le is not None
        e.tentatives.append(tentative)
        observation = _observation(tentative)
        if observation is not None and (tentative.principale or observation):
            # KC secondaire : seule une réussite est informative (un échec peut venir d'ailleurs)
            e.p = mise_a_jour(e.p, observation, p_guess, params, apprentissage)
        if maitrisee_avant and tentative.statut is Statut.CORRECT and not tentative.aide:
            if tentative.principale and tentative.quand - e.maitrisee_le >= criteres.delai_consolidation:  # type: ignore[operator]
                e.consolidee = True
            if not tentative.principale:
                e.transferee = True
        if not maitrisee_avant and e.est_maitrisee(criteres):
            e.maitrisee_le = tentative.quand
        if maitrisee_avant and tentative.principale and tentative.erreur_type:
            # erreur typique sur une KC maîtrisée : on la rouvre (rechute)
            e.maitrisee_le, e.consolidee, e.transferee = None, False, False
        return e


def _observation(t: Tentative) -> bool | None:
    """CORRECT → vrai ; INCORRECT → faux ; FORME / ILLISIBLE → neutre ; aide → neutre si juste."""
    if t.statut is Statut.CORRECT:
        return None if t.aide else True
    if t.statut is Statut.INCORRECT:
        return False
    return None
