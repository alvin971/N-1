"""Coffre d'identité, SÉPARÉ des données pédagogiques.

- L'identifiant pseudonyme est ALÉATOIRE (uuid4), jamais dérivé du nom ou de l'e-mail : sans
  le coffre, les données pédagogiques ne permettent pas de remonter à l'élève par calcul.
- Attention : c'est une PSEUDONYMISATION, pas une anonymisation. Les données pédagogiques
  restent des données personnelles au sens du RGPD (réidentification possible via le coffre).
- Minimisation : prénom (affichage), année de naissance (règles de consentement < 15 ans),
  contact parent. Pas de date de naissance complète, pas d'adresse, pas d'établissement par défaut.
- Consentements granulaires et révocables, notamment l'usage des copies pour l'entraînement OCR
  (traitement distinct, opt-in, consentement parental sous 15 ans — art. 45 loi Informatique et Libertés).

MVP : SQLite chiffré au repos par le stockage. Production : base dédiée, accès restreint, clés
gérées dans un HSM/KMS hébergé dans l'UE.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS identites (
    eleve TEXT PRIMARY KEY,
    prenom TEXT NOT NULL,
    annee_naissance INTEGER NOT NULL,
    niveau_scolaire TEXT NOT NULL,
    contact_parent TEXT,
    cree_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consentements (
    eleve TEXT NOT NULL REFERENCES identites(eleve) ON DELETE CASCADE,
    finalite TEXT NOT NULL,
    accorde INTEGER NOT NULL,
    par_parent INTEGER NOT NULL,
    quand TEXT NOT NULL
);
"""

FINALITES = {
    "service": "Fonctionnement du tutorat (exécution du service)",
    "entrainement_ocr": "Utilisation de recadrages de copies pour améliorer la lecture des copies",
    "recherche_pedagogique": "Analyses agrégées pour améliorer les parcours",
}

AGE_MAJORITE_NUMERIQUE = 15  # France, art. 45 loi Informatique et Libertés


@dataclass(frozen=True)
class Identite:
    eleve: str
    prenom: str
    annee_naissance: int
    niveau_scolaire: str
    contact_parent: str | None


class CoffreIdentite:
    def __init__(self, chemin: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(chemin))
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def creer(self, prenom: str, annee_naissance: int, niveau_scolaire: str, contact_parent: str | None = None) -> Identite:
        ident = Identite(str(uuid.uuid4()), prenom.strip(), annee_naissance, niveau_scolaire, contact_parent)
        if self.consentement_parental_requis(ident) and not contact_parent:
            raise ValueError("moins de 15 ans : un contact parent est requis pour recueillir le consentement")
        self.db.execute(
            "INSERT INTO identites VALUES (?, ?, ?, ?, ?, ?)",
            (ident.eleve, ident.prenom, ident.annee_naissance, ident.niveau_scolaire, ident.contact_parent,
             datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()
        return ident

    @staticmethod
    def consentement_parental_requis(ident: Identite, aujourd_hui: date | None = None) -> bool:
        aujourd_hui = aujourd_hui or date.today()
        # prudence : on considère l'âge minimal possible à partir de l'année de naissance
        return aujourd_hui.year - ident.annee_naissance - 1 < AGE_MAJORITE_NUMERIQUE

    def lire(self, eleve: str) -> Identite | None:
        row = self.db.execute(
            "SELECT eleve, prenom, annee_naissance, niveau_scolaire, contact_parent FROM identites WHERE eleve = ?", (eleve,)
        ).fetchone()
        return Identite(*row) if row else None

    def consentir(self, eleve: str, finalite: str, accorde: bool, par_parent: bool) -> None:
        if finalite not in FINALITES:
            raise ValueError(f"finalité inconnue : {finalite}")
        ident = self.lire(eleve)
        if ident is None:
            raise KeyError(eleve)
        if accorde and finalite != "service" and self.consentement_parental_requis(ident) and not par_parent:
            raise PermissionError("moins de 15 ans : le consentement doit aussi être donné par un titulaire de l'autorité parentale")
        self.db.execute("INSERT INTO consentements VALUES (?, ?, ?, ?, ?)",
                        (eleve, finalite, int(accorde), int(par_parent), datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def a_consenti(self, eleve: str, finalite: str) -> bool:
        """Dernier choix enregistré (un retrait de consentement l'emporte sur un accord antérieur)."""
        row = self.db.execute(
            "SELECT accorde FROM consentements WHERE eleve = ? AND finalite = ? ORDER BY rowid DESC LIMIT 1", (eleve, finalite)
        ).fetchone()
        return bool(row and row[0])

    def effacer(self, eleve: str) -> None:
        self.db.execute("DELETE FROM identites WHERE eleve = ?", (eleve,))
        self.db.commit()
