"""Filtrage des données personnelles dans le texte libre AVANT tout envoi à un modèle de langage.

Limite assumée : un filtre par motifs ne garantit PAS l'absence de données personnelles dans du
texte libre d'enfant. Il RÉDUIT l'exposition ; il ne remplace ni l'hébergement UE du modèle,
ni le contrat de sous-traitance (art. 28), ni l'interdiction contractuelle d'entraîner sur les données.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MOTIFS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("TELEPHONE", re.compile(r"(?:(?:\+|00)33[\s.-]?|0)[1-9](?:[\s.-]?\d{2}){4}")),
    ("URL", re.compile(r"https?://\S+|www\.\S+")),
    ("CODE_POSTAL", re.compile(r"\b\d{5}\b(?=\s+[A-ZÉÈ][a-zéèêàç-]+)")),
    ("ETABLISSEMENT", re.compile(r"\b(?i:coll[eè]ge|lyc[ée]e|[ée]cole|institution)\s+(?:[A-ZÉÈ][\w'-]*\s?){1,4}")),
    ("PERSONNE", re.compile(r"\b(?:M\.|Mme|Mlle|Madame|Monsieur|Mr|prof(?:esseur|esseure)?)\s+[A-ZÉÈ][\w'-]+")),
    ("PRENOM_DECLARE", re.compile(r"\b(?:je m'appelle|mon nom est|moi c'est|mon prénom est)\s+[A-ZÉÈa-zéè][\w'-]+", re.I)),
    ("CLASSE", re.compile(r"\b(?:en|de la|la)\s+[3-6]e\s?[A-Z0-9]\b")),
]


@dataclass(frozen=True)
class TexteFiltre:
    texte: str
    remplacements: dict[str, int]

    @property
    def modifie(self) -> bool:
        return bool(self.remplacements)


def filtrer(texte: str, prenoms_connus: tuple[str, ...] = ()) -> TexteFiltre:
    compte: dict[str, int] = {}
    for etiquette, motif in _MOTIFS:
        texte, n = motif.subn(f"[{etiquette}]", texte)
        if n:
            compte[etiquette] = compte.get(etiquette, 0) + n
    for p in prenoms_connus:
        if p:
            texte, n = re.subn(rf"\b{re.escape(p)}\b", "[PRENOM]", texte, flags=re.I)
            if n:
                compte["PRENOM"] = compte.get("PRENOM", 0) + n
    return TexteFiltre(texte, compte)
