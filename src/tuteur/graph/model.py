"""Graphe de compétences : modèle en mémoire, compilé depuis le YAML versionné.

Le graphe est petit (quelques centaines à quelques milliers de nœuds) et change rarement :
pas de base de données graphe, une structure immuable chargée par chaque processus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import yaml

NIVEAUX = ["CP", "CE1", "CE2", "CM1", "CM2", "6e", "5e", "4e", "3e"]


def rang_niveau(niveau: str) -> int:
    return NIVEAUX.index(niveau)


@dataclass(frozen=True)
class Prerequis:
    kc: str
    force: str  # "forte" | "faible"
    pourquoi: str

    @property
    def fort(self) -> bool:
        return self.force == "forte"


@dataclass(frozen=True)
class KC:
    id: str
    titre: str
    niveau: str
    domaine: str
    maitrise: str
    prereqs: tuple[Prerequis, ...] = ()

    @property
    def rang(self) -> int:
        return rang_niveau(self.niveau)


@dataclass(frozen=True)
class Chapitre:
    id: str
    titre: str
    niveau: str
    cibles: tuple[str, ...]


class GraphError(ValueError):
    pass


@dataclass
class Graphe:
    version: str
    kcs: dict[str, KC]
    chapitres: dict[str, Chapitre] = field(default_factory=dict)

    # ------------------------------------------------------------------ chargement
    @classmethod
    def depuis_yaml(cls, chemin: str | Path) -> "Graphe":
        data = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
        kcs: dict[str, KC] = {}
        for raw in data["kcs"]:
            if raw["id"] in kcs:
                raise GraphError(f"KC en double : {raw['id']}")
            kcs[raw["id"]] = KC(
                id=raw["id"],
                titre=raw["titre"],
                niveau=raw["niveau"],
                domaine=raw["domaine"],
                maitrise=raw["maitrise"],
                prereqs=tuple(Prerequis(**p) for p in raw.get("prereqs") or []),
            )
        chapitres = {
            c["id"]: Chapitre(id=c["id"], titre=c["titre"], niveau=c["niveau"], cibles=tuple(c["cibles"]))
            for c in data.get("chapitres") or []
        }
        g = cls(version=str(data["version"]), kcs=kcs, chapitres=chapitres)
        g.valider()
        return g

    # ------------------------------------------------------------------ validation
    def valider(self) -> None:
        erreurs: list[str] = []
        for kc in self.kcs.values():
            if kc.niveau not in NIVEAUX:
                erreurs.append(f"{kc.id} : niveau inconnu {kc.niveau!r}")
            for p in kc.prereqs:
                if p.kc not in self.kcs:
                    erreurs.append(f"{kc.id} : prérequis inconnu {p.kc}")
                elif p.force not in ("forte", "faible"):
                    erreurs.append(f"{kc.id} → {p.kc} : force invalide {p.force!r}")
                elif not p.pourquoi.strip():
                    erreurs.append(f"{kc.id} → {p.kc} : justification manquante")
                elif self.kcs[p.kc].rang > kc.rang:
                    erreurs.append(f"{kc.id} ({kc.niveau}) a pour prérequis {p.kc} de niveau supérieur")
        for ch in self.chapitres.values():
            for c in ch.cibles:
                if c not in self.kcs:
                    erreurs.append(f"chapitre {ch.id} : cible inconnue {c}")
        if erreurs:
            raise GraphError("\n".join(erreurs))
        self.ordre_topologique  # lève GraphError en cas de cycle

    # ------------------------------------------------------------------ requêtes
    def prereqs(self, kc_id: str, seulement_forts: bool = False) -> list[str]:
        return [p.kc for p in self.kcs[kc_id].prereqs if p.fort or not seulement_forts]

    @cached_property
    def successeurs(self) -> dict[str, list[str]]:
        succ: dict[str, list[str]] = {k: [] for k in self.kcs}
        for kc in self.kcs.values():
            for p in kc.prereqs:
                succ[p.kc].append(kc.id)
        return succ

    @cached_property
    def ordre_topologique(self) -> list[str]:
        """Ordre de Kahn, départage stable par (niveau, id) pour être reproductible."""
        degre = {k: len(self.kcs[k].prereqs) for k in self.kcs}
        prets = sorted((k for k, d in degre.items() if d == 0), key=self._cle_tri)
        ordre: list[str] = []
        while prets:
            k = prets.pop(0)
            ordre.append(k)
            for s in self.successeurs[k]:
                degre[s] -= 1
                if degre[s] == 0:
                    prets.append(s)
            prets.sort(key=self._cle_tri)
        if len(ordre) != len(self.kcs):
            reste = sorted(set(self.kcs) - set(ordre))
            raise GraphError(f"cycle détecté parmi : {', '.join(reste)}")
        return ordre

    def _cle_tri(self, k: str) -> tuple[int, str]:
        return (self.kcs[k].rang, k)

    def ancetres(self, kc_ids: str | list[str], inclure: bool = True) -> set[str]:
        depart = [kc_ids] if isinstance(kc_ids, str) else list(kc_ids)
        vus: set[str] = set(depart) if inclure else set()
        pile = list(depart)
        while pile:
            k = pile.pop()
            for p in self.kcs[k].prereqs:
                if p.kc not in vus:
                    vus.add(p.kc)
                    pile.append(p.kc)
        return vus

    def descendants(self, kc_id: str, dans: set[str] | None = None) -> set[str]:
        vus: set[str] = set()
        pile = [kc_id]
        while pile:
            k = pile.pop()
            for s in self.successeurs[k]:
                if s not in vus and (dans is None or s in dans):
                    vus.add(s)
                    pile.append(s)
        return vus

    def sous_graphe(self, cibles: list[str]) -> list[str]:
        """Fermeture des ancêtres des cibles, en ordre topologique."""
        ens = self.ancetres(cibles)
        return [k for k in self.ordre_topologique if k in ens]
