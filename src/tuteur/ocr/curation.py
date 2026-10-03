"""Active learning OCR SUPERVISÉ : des corrections d'élèves au dataset versionné.

    corrections → filtres automatiques → revue humaine (échantillon / cas douteux)
                → dataset versionné (manifeste + empreintes) → fine-tuning périodique
                → évaluation sur jeu de référence FIGÉ → déploiement seulement si amélioration

Ce module ne réentraîne rien : il décide quelles paires sont admissibles et si un nouveau
modèle a le droit d'être déployé.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from ..mathengine import ErreurLecture, lire_equation
from .flux import CopieEleve, Etape


class Decision(StrEnum):
    ACCEPTEE = "acceptee"
    REVUE_HUMAINE = "revue_humaine"
    REJETEE = "rejetee"


@dataclass(frozen=True)
class Candidate:
    empreinte_image: str
    transcription: str
    hypothese_ocr: str
    confiance_ocr: float
    modifiee_par_eleve: bool
    version_ocr: str
    eleve: str  # pseudonyme ; retiré du manifeste publié au dataset


@dataclass
class ParamsCuration:
    distance_max_relative: float = 0.35  # au-delà : réécriture trop importante → humain
    confiance_haute: float = 0.95  # OCR très sûr ET non modifié → acceptée (avec contrôle par échantillon)
    taux_controle: float = 0.05  # part des acceptations auto envoyées quand même en revue
    fiabilite_min: float = 0.7  # fiabilité minimale de l'élève (mesurée par des pièges connus)


def distance_edition(a: str, b: str) -> int:
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cour = [i]
        for j, cb in enumerate(b, 1):
            cour.append(min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (ca != cb)))
        prec = cour
    return prec[-1]


def evaluer_candidate(copie: CopieEleve, references: set[str], fiabilite_eleve: float,
                      params: ParamsCuration = ParamsCuration(), rng: random.Random | None = None) -> tuple[Decision, str, Candidate | None]:
    rng = rng or random.Random(copie.empreinte)
    if not copie.consentement_entrainement:
        return Decision.REJETEE, "pas de consentement à l'entraînement", None
    if copie.etape is not Etape.CORRIGEE or copie.transcription_finale is None:
        return Decision.REJETEE, "transcription non confirmée avant verdict", None
    if copie.empreinte in references:
        return Decision.REJETEE, "image du jeu de référence (jamais en entraînement)", None
    try:
        for ligne in copie.transcription_finale.splitlines():
            if ligne.strip():
                lire_equation(ligne)
    except ErreurLecture as e:
        return Decision.REJETEE, f"transcription illisible par le moteur : {e}", None
    h = copie.hypotheses[0]
    cand = Candidate(copie.empreinte, copie.transcription_finale, h.texte, h.confiance, copie.modifiee_par_eleve,
                     copie.version_ocr, copie.eleve)
    if fiabilite_eleve < params.fiabilite_min:
        return Decision.REVUE_HUMAINE, "fiabilité de l'élève insuffisante", cand
    if copie.modifiee_par_eleve:
        meilleure = min(distance_edition(copie.transcription_finale, x.texte) for x in copie.hypotheses)
        if meilleure / max(len(copie.transcription_finale), 1) > params.distance_max_relative:
            return Decision.REVUE_HUMAINE, "correction trop éloignée de toutes les hypothèses de l'OCR", cand
        if any(x.texte.strip() == copie.transcription_finale for x in copie.hypotheses[1:]):
            return Decision.ACCEPTEE, "la correction correspond à une hypothèse alternative de l'OCR", cand
        return Decision.REVUE_HUMAINE, "correction plausible mais hors des hypothèses : vérification", cand
    if h.confiance >= params.confiance_haute:
        # risque principal : l'élève valide sans relire ; contrôle par échantillon
        if rng.random() < params.taux_controle:
            return Decision.REVUE_HUMAINE, "contrôle aléatoire d'une validation", cand
        return Decision.ACCEPTEE, "OCR sûr et validé", cand
    return Decision.REVUE_HUMAINE, "OCR peu sûr validé sans modification : vérification", cand


@dataclass
class VersionDataset:
    paires: list[Candidate] = field(default_factory=list)
    parent: str | None = None

    def manifeste(self) -> dict:
        lignes = sorted(({"image": c.empreinte_image, "transcription": c.transcription} for c in self.paires),
                        key=lambda d: d["image"])
        corps = json.dumps(lignes, ensure_ascii=False, sort_keys=True).encode()
        return {"version": hashlib.sha256(corps).hexdigest()[:16], "parent": self.parent, "n": len(lignes), "paires": lignes}


@dataclass(frozen=True)
class Metriques:
    """Mesurées sur le jeu de référence figé, par catégorie (fractions, exposants, ratures, éclairage…)."""

    taux_inversion_verdict: dict[str, float]  # part des copies dont l'erreur OCR change le verdict JUSTE/FAUX
    taux_exact: dict[str, float]


def porte_deploiement(actuel: Metriques, candidat: Metriques, tolerance: float = 0.005) -> tuple[bool, list[str]]:
    """Déploie seulement si le taux global d'inversion de verdict baisse ET qu'aucune catégorie
    ne régresse au-delà de la tolérance."""
    raisons = []
    glob_a = sum(actuel.taux_inversion_verdict.values()) / len(actuel.taux_inversion_verdict)
    glob_c = sum(candidat.taux_inversion_verdict.values()) / len(candidat.taux_inversion_verdict)
    if glob_c >= glob_a:
        raisons.append(f"pas d'amélioration globale ({glob_c:.3f} ≥ {glob_a:.3f})")
    for cat, v in actuel.taux_inversion_verdict.items():
        if candidat.taux_inversion_verdict.get(cat, 1.0) > v + tolerance:
            raisons.append(f"régression sur « {cat} »")
    return (not raisons), raisons


def exporter(c: Candidate) -> dict:
    d = asdict(c)
    d.pop("eleve")  # le dataset d'entraînement ne contient pas l'identifiant élève
    return d
