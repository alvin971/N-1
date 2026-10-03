"""Bayesian Knowledge Tracing par KC.

P(L) = probabilité que la KC soit maîtrisée. Mise à jour bayésienne à chaque réponse
(slip = erreur d'inattention, guess = réussite au hasard, qui dépend du format : QCM, oui/non,
saisie libre), puis transition d'apprentissage (en pratique uniquement).

Paramètres fixés à la main au départ (avec des enseignants), puis ajustés sur les données réelles :
voir docs/architecture.md, « Calibration ».
"""

from __future__ import annotations

from dataclasses import dataclass

from ..graph import rang_niveau


@dataclass(frozen=True)
class ParamsBKT:
    p_transit: float = 0.12
    p_slip: float = 0.10
    p_oubli: float = 0.0  # BKT standard : pas d'oubli ; la consolidation est mesurée à part


PARAMS_DEFAUT = ParamsBKT()


def prior_selon_niveau(niveau_kc: str, niveau_eleve: str) -> float:
    """A priori de maîtrise d'une KC selon l'écart entre son niveau et la classe de l'élève.

    Valeurs de départ raisonnables ; à remplacer par des a priori appris sur la population.
    """
    ecart = rang_niveau(niveau_eleve) - rang_niveau(niveau_kc)
    if ecart < 0:
        return 0.05  # notion pas encore enseignée
    return {0: 0.30, 1: 0.60, 2: 0.72}.get(ecart, 0.82)


def posterieur(p: float, juste: bool, p_slip: float, p_guess: float) -> float:
    if juste:
        num = p * (1 - p_slip)
        den = num + (1 - p) * p_guess
    else:
        num = p * p_slip
        den = num + (1 - p) * (1 - p_guess)
    return num / den if den > 0 else p


def mise_a_jour(p: float, juste: bool, p_guess: float, params: ParamsBKT = PARAMS_DEFAUT, apprentissage: bool = True) -> float:
    q = posterieur(p, juste, params.p_slip, p_guess)
    if apprentissage:
        q = q + (1 - q) * params.p_transit
    return min(max(q, 1e-4), 1 - 1e-4)


def proba_reussite(p: float, p_guess: float, params: ParamsBKT = PARAMS_DEFAUT) -> float:
    """Probabilité prédite de réussir le prochain exercice."""
    return p * (1 - params.p_slip) + (1 - p) * p_guess
