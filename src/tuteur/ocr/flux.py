"""Flux « photo de MA résolution » → transcription → confirmation → correction.

Règles imposées par le code (et non par la bonne volonté) :
  1. Les métadonnées de l'image (EXIF : GPS, appareil, date…) sont supprimées à la réception.
  2. La transcription doit être CONFIRMÉE (ou corrigée) par l'élève AVANT de connaître le verdict.
     Sinon l'élève qui voit « faux » « corrige l'OCR » en y écrivant la bonne réponse : la paire
     image → transcription deviendrait fausse et contaminerait le dataset (et ce serait de la triche).
  3. Une fois le verdict rendu, la transcription est figée.
  4. Seule une paire dont l'élève (et un parent sous 15 ans) a consenti à l'usage pour
     l'entraînement peut devenir une candidate de dataset — sinon l'image est jetée après usage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ..mathengine import RapportEtapes, verifier_resolution


@dataclass(frozen=True)
class Hypothese:
    texte: str  # une ligne par équation, séparées par « \n »
    confiance: float


class ModeleOCR(Protocol):
    """Modèle auto-hébergé dans l'UE (ex. petit modèle vision-langage fine-tuné, voir docs)."""

    version: str

    def transcrire(self, image: bytes, n_meilleures: int = 3) -> list[Hypothese]: ...


class Etape(StrEnum):
    RECUE = "recue"
    TRANSCRITE = "transcrite"
    CONFIRMEE = "confirmee"
    CORRIGEE = "corrigee"


class OrdreInterdit(RuntimeError):
    pass


def supprimer_metadonnees_jpeg(donnees: bytes) -> bytes:
    """Retire les segments APPn (EXIF, XMP, ICC…) et COM d'un JPEG, sans dépendance externe."""
    if not donnees.startswith(b"\xff\xd8"):
        return donnees  # pas un JPEG : laissé au pré-traitement dédié (PNG : chunks texte, etc.)
    out = bytearray(b"\xff\xd8")
    i = 2
    while i + 4 <= len(donnees):
        if donnees[i] != 0xFF:
            break
        marqueur = donnees[i + 1]
        if marqueur == 0xDA:  # début des données d'image : on recopie la suite telle quelle
            out += donnees[i:]
            return bytes(out)
        longueur = int.from_bytes(donnees[i + 2:i + 4], "big")
        segment = donnees[i:i + 2 + longueur]
        if not (0xE1 <= marqueur <= 0xEF or marqueur == 0xFE):  # on garde APP0 (JFIF), on retire APP1..15 et COM
            out += segment
        i += 2 + longueur
    out += donnees[i:]
    return bytes(out)


@dataclass
class CopieEleve:
    eleve: str
    enonce: str  # équation de départ (connue : exercice proposé par le tuteur)
    image: bytes
    consentement_entrainement: bool
    etape: Etape = Etape.RECUE
    hypotheses: list[Hypothese] = field(default_factory=list)
    version_ocr: str = ""
    transcription_finale: str | None = None
    modifiee_par_eleve: bool = False
    rapport: RapportEtapes | None = None

    def __post_init__(self) -> None:
        self.image = supprimer_metadonnees_jpeg(self.image)

    @property
    def empreinte(self) -> str:
        return hashlib.sha256(self.image).hexdigest()

    def transcrire(self, modele: ModeleOCR) -> Hypothese:
        if self.etape is not Etape.RECUE:
            raise OrdreInterdit("déjà transcrite")
        self.hypotheses = modele.transcrire(self.image)
        self.version_ocr = modele.version
        self.etape = Etape.TRANSCRITE
        return self.hypotheses[0]

    def confirmer(self, transcription: str) -> None:
        if self.etape is Etape.CORRIGEE:
            raise OrdreInterdit("le verdict est rendu : la transcription ne peut plus être modifiée")
        if self.etape is not Etape.TRANSCRITE:
            raise OrdreInterdit("rien à confirmer")
        self.transcription_finale = transcription.strip()
        self.modifiee_par_eleve = self.transcription_finale != self.hypotheses[0].texte.strip()
        self.etape = Etape.CONFIRMEE

    def corriger(self) -> RapportEtapes:
        if self.etape is not Etape.CONFIRMEE:
            raise OrdreInterdit("la transcription doit être confirmée par l'élève avant la correction")
        lignes = [self.enonce] + [l for l in (self.transcription_finale or "").splitlines() if l.strip()]
        self.rapport = verifier_resolution(lignes)
        self.etape = Etape.CORRIGEE
        return self.rapport
