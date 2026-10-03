"""Journal d'événements en ajout seul (event sourcing).

L'état de maîtrise n'est qu'une PROJECTION recalculable des événements : quand on change de
modèle (paramètres BKT, critères de maîtrise, graphe), on rejoue l'historique.
Chaque événement porte la version du contenu et de la politique qui l'ont produit.

Les événements ne contiennent QUE l'identifiant pseudonyme de l'élève — jamais nom, e-mail,
établissement (ils vivent dans le coffre d'identité, base séparée).

MVP : SQLite. Production : PostgreSQL partitionné par élève (voir docs/architecture.md).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS evenements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eleve TEXT NOT NULL,
    quand TEXT NOT NULL,
    type TEXT NOT NULL,
    donnees TEXT NOT NULL,
    version_contenu TEXT NOT NULL,
    version_politique TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evenements_eleve ON evenements(eleve, id);
CREATE TRIGGER IF NOT EXISTS evenements_sans_modification
BEFORE UPDATE ON evenements BEGIN SELECT RAISE(ABORT, 'journal en ajout seul'); END;
"""


@dataclass(frozen=True)
class Evenement:
    eleve: str
    quand: datetime
    type: str
    donnees: dict[str, Any]
    version_contenu: str
    version_politique: str
    id: int | None = None


class JournalEvenements:
    def __init__(self, chemin: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(chemin))
        self.db.executescript(SCHEMA)

    def ajouter(self, e: Evenement) -> int:
        cur = self.db.execute(
            "INSERT INTO evenements (eleve, quand, type, donnees, version_contenu, version_politique) VALUES (?, ?, ?, ?, ?, ?)",
            (e.eleve, e.quand.astimezone(timezone.utc).isoformat(), e.type, json.dumps(e.donnees, ensure_ascii=False),
             e.version_contenu, e.version_politique),
        )
        self.db.commit()
        return int(cur.lastrowid)  # type: ignore[arg-type]

    def lire(self, eleve: str, types: tuple[str, ...] | None = None) -> Iterator[Evenement]:
        q = "SELECT id, eleve, quand, type, donnees, version_contenu, version_politique FROM evenements WHERE eleve = ?"
        args: list[Any] = [eleve]
        if types:
            q += f" AND type IN ({','.join('?' * len(types))})"
            args += list(types)
        for row in self.db.execute(q + " ORDER BY id", args):
            yield Evenement(row[1], datetime.fromisoformat(row[2]), row[3], json.loads(row[4]), row[5], row[6], row[0])

    def effacer_eleve(self, eleve: str) -> int:
        """Droit à l'effacement (RGPD art. 17). Seule suppression autorisée dans le journal."""
        cur = self.db.execute("DELETE FROM evenements WHERE eleve = ?", (eleve,))
        self.db.commit()
        return cur.rowcount

    def purger_avant(self, limite: datetime, types: tuple[str, ...]) -> int:
        """Durée de conservation : purge des types d'événements à courte rétention (ex. texte libre)."""
        cur = self.db.execute(
            f"DELETE FROM evenements WHERE quand < ? AND type IN ({','.join('?' * len(types))})",
            (limite.astimezone(timezone.utc).isoformat(), *types),
        )
        self.db.commit()
        return cur.rowcount
