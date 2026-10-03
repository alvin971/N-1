"""Télécharge Pyodide (Python compilé en WebAssembly) et les paquets dont le tuteur a besoin,
pour les servir DEPUIS NOTRE PROPRE SITE (aucun CDN tiers contacté par le navigateur de l'élève).

    python scripts/telecharger_pyodide.py --dest build/pyodide

- noyau : paquet npm officiel `pyodide` ;
- paquets (numpy, sympy, pyyaml, sqlite3 + dépendances) : distribution officielle Pyodide ;
- chaque fichier est vérifié contre l'empreinte SHA-256 du fichier `pyodide-lock.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "0.29.5"
PAQUETS = ["numpy", "sympy", "pyyaml", "sqlite3"]
NOYAU = ["pyodide.js", "pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
SOURCES = [
    "https://cdn.jsdelivr.net/pyodide/v{version}/full/{fichier}",
    "https://cdn.jsdelivr.net/pyodide/v{version}/pyc/{fichier}",
]


def telecharger(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "tuteur-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def dependances(lock: dict, noms: list[str]) -> dict[str, dict]:
    acc: dict[str, dict] = {}
    pile = list(noms)
    while pile:
        n = pile.pop()
        if n in acc:
            continue
        acc[n] = lock["packages"][n]
        pile.extend(acc[n].get("depends", []))
    return acc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--version", default=VERSION)
    a = ap.parse_args()
    dest = Path(a.dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    print(f"Noyau Pyodide {a.version} (npm)…")
    tgz = telecharger(f"https://registry.npmjs.org/pyodide/-/pyodide-{a.version}.tgz")
    with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as t:
        for f in NOYAU:
            membre = t.extractfile(f"package/{f}")
            if membre is None:
                raise SystemExit(f"fichier absent du paquet npm : {f}")
            (dest / f).write_bytes(membre.read())

    lock = json.loads((dest / "pyodide-lock.json").read_text())
    for nom, p in sorted(dependances(lock, PAQUETS).items()):
        fichier, attendu = p["file_name"], p["sha256"]
        for modele in SOURCES:
            url = modele.format(version=a.version, fichier=fichier)
            try:
                donnees = telecharger(url)
            except Exception as e:  # noqa: BLE001
                print(f"  {nom} : {url} → {e}")
                continue
            if hashlib.sha256(donnees).hexdigest() != attendu:
                print(f"  {nom} : empreinte invalide depuis {url}")
                continue
            (dest / fichier).write_bytes(donnees)
            print(f"  {nom} : {fichier} ({len(donnees) // 1024} Ko) ✓")
            break
        else:
            print(f"ÉCHEC : impossible d'obtenir {fichier}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
