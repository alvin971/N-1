"""Tuteur mathématique adaptatif — noyau déterministe."""

import os
from pathlib import Path

RACINE_CONTENU = Path(os.environ.get("TUTEUR_CONTENU", Path(__file__).resolve().parents[2] / "content"))

__version__ = "0.1.0"
