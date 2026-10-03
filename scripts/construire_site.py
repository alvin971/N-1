"""Construit la version « tout dans le navigateur » du tuteur, publiable sur GitHub Pages.

    python scripts/construire_site.py --pyodide build/pyodide --sortie site

- reprend l'interface élève (src/tuteur/api/static) ;
- y ajoute Pyodide (servi localement) et `local.js`, qui exécute `tuteur.service.Service`
  directement dans la page : pas de serveur, les réponses de l'élève restent sur son appareil
  (base SQLite conservée dans le stockage du navigateur) ;
- empaquette le code Python et le contenu pédagogique dans `tuteur.zip`.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
STATIQUE = RACINE / "src" / "tuteur" / "api" / "static"
SCRIPTS_LOCAUX = '  <script defer src="pyodide/pyodide.js"></script>\n  <script defer src="local.js"></script>\n'


def empaqueter(sortie: Path) -> None:
    with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as z:
        for base in ("src/tuteur", "content"):
            for f in sorted((RACINE / base).rglob("*")):
                rel = f.relative_to(RACINE)
                if f.is_dir() or "__pycache__" in f.parts or rel.parts[:4] == ("src", "tuteur", "api", "static"):
                    continue
                z.write(f, rel.as_posix())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pyodide", required=True, help="dossier produit par telecharger_pyodide.py")
    ap.add_argument("--sortie", required=True)
    a = ap.parse_args()
    sortie = Path(a.sortie)
    if sortie.exists():
        shutil.rmtree(sortie)
    shutil.copytree(STATIQUE, sortie)
    shutil.copytree(a.pyodide, sortie / "pyodide")
    index = sortie / "index.html"
    html = index.read_text(encoding="utf-8")
    ancre = '  <script defer src="app.js"></script>\n'
    if ancre not in html:
        raise SystemExit("index.html : balise app.js introuvable")
    index.write_text(html.replace(ancre, SCRIPTS_LOCAUX + ancre), encoding="utf-8")
    empaqueter(sortie / "tuteur.zip")
    (sortie / ".nojekyll").write_text("")  # GitHub Pages : servir les fichiers tels quels
    taille = sum(f.stat().st_size for f in sortie.rglob("*") if f.is_file())
    print(f"Site construit dans {sortie} ({taille / 1e6:.1f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
