"""Chargement et validation de TOUT le contenu pédagogique (graphe, erreurs typiques, cours,
modèles d'exercices). La validation tourne en CI : un contenu incohérent ne part pas en production.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from . import RACINE_CONTENU
from .exercises import REGISTRE, Modele, modeles_pour
from .graph import Graphe
from .mathengine.steps import ERREURS_ETAPES


@dataclass(frozen=True)
class ErreurTypique:
    id: str
    kc: str
    titre: str
    remediation: str


@dataclass(frozen=True)
class Contenu:
    graphe: Graphe
    erreurs: dict[str, ErreurTypique]
    cours: dict[str, str]
    modeles: dict[str, Modele]

    @property
    def version(self) -> str:
        return self.graphe.version

    def modeles_diagnostic(self, kc: str) -> list[Modele]:
        return modeles_pour(kc, diagnostic_seulement=True)

    def modeles_pratique(self, kc: str) -> list[Modele]:
        return modeles_pour(kc)

    def valider(self, echantillons: int = 15) -> list[str]:
        g = self.graphe
        pbs: list[str] = []
        for m in self.modeles.values():
            for kc in m.kcs:
                if kc not in g.kcs:
                    pbs.append(f"modèle {m.id} : KC inconnue {kc}")
            for e in m.erreurs:
                if e not in self.erreurs:
                    pbs.append(f"modèle {m.id} : erreur typique inconnue {e}")
            for d in m.difficultes:
                for graine in range(echantillons):
                    item = m.instancier(graine, d)
                    hors = set(item.spec.erreurs) - set(m.erreurs)
                    if hors:
                        pbs.append(f"modèle {m.id} : erreurs produites non déclarées {sorted(hors)}")
                        break
        for ch in g.chapitres.values():
            sous = set(g.sous_graphe(list(ch.cibles)))
            for m in self.modeles.values():
                if m.kc_principale not in sous:
                    continue
                for d in m.difficultes:
                    hors = [k for k in m.kcs_mobilisees(d) if k not in sous]
                    if hors:
                        pbs.append(f"modèle {m.id} (difficulté {d}) mobilise {hors}, hors du chapitre {ch.id} : "
                                   "ajouter le prérequis manquant au graphe")
        for m in self.modeles.values():
            for d, ks in m.mobilise.items():
                for k in ks:
                    if k not in g.kcs:
                        pbs.append(f"modèle {m.id} : KC mobilisée inconnue {k}")
                    elif g.kcs[k].rang > g.kcs[m.kc_principale].rang:
                        pbs.append(f"modèle {m.id} : mobilise {k} de niveau supérieur à sa KC principale")
        for kc in g.kcs:
            if not self.modeles_diagnostic(kc):
                pbs.append(f"KC {kc} : aucun modèle diagnostique")
            if kc not in self.cours:
                pbs.append(f"KC {kc} : pas d'explication de cours")
        for e in self.erreurs.values():
            if e.kc not in g.kcs:
                pbs.append(f"erreur {e.id} : KC inconnue {e.kc}")
        utilisees = {e for m in self.modeles.values() for e in m.erreurs} | set(ERREURS_ETAPES)
        for e in sorted(set(self.erreurs) - utilisees):
            pbs.append(f"erreur {e} : définie mais jamais produite (ni modèle ni vérificateur d'étapes)")
        for e in sorted(set(ERREURS_ETAPES) - set(self.erreurs)):
            pbs.append(f"vérificateur d'étapes : erreur {e} absente du catalogue")
        for k in self.cours:
            if k not in g.kcs:
                pbs.append(f"cours : KC inconnue {k}")
        return pbs


def charger(racine: str | Path = RACINE_CONTENU) -> Contenu:
    racine = Path(racine)
    graphe = Graphe.depuis_yaml(racine / "graphe.yaml")
    brut = yaml.safe_load((racine / "erreurs_typiques.yaml").read_text(encoding="utf-8"))["erreurs"]
    erreurs = {i: ErreurTypique(i, e["kc"], e["titre"], " ".join(e["remediation"].split())) for i, e in brut.items()}
    cours = {k: " ".join(v.split()) for k, v in yaml.safe_load((racine / "cours.yaml").read_text(encoding="utf-8"))["cours"].items()}
    return Contenu(graphe, erreurs, cours, dict(REGISTRE))


@lru_cache(maxsize=1)
def contenu_par_defaut() -> Contenu:
    return charger()
