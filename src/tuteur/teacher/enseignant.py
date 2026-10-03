"""Le « professeur » : formule les explications et retours.

Il ne DÉCIDE rien (ni la correction, ni la compétence à travailler, ni la difficulté) : il reçoit
un verdict structuré et le met en mots.

  * `EnseignantDeterministe` (défaut) : sert le contenu pré-rédigé et relu (cours par KC,
    remédiation par erreur typique, exemple corrigé du modèle). Couvre l'essentiel des cas,
    coût nul, fiabilité maximale.
  * `PasserelleLLM` : optionnelle, pour le dialogue ouvert. Garde-fous :
      - refuse tout point d'accès non déclaré hébergé dans l'UE ;
      - filtre les données personnelles avant envoi ;
      - ne transmet que l'état structuré nécessaire (pas d'identité, pas d'historique brut) ;
      - revérifie avec SymPy chaque égalité numérique de la réponse ;
      - interdit de divulguer la réponse attendue en mode indice ;
      - en cas d'échec d'un garde-fou : repli sur le contenu déterministe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import sympy

from ..contenu import Contenu
from ..exercises import Item
from ..mathengine import Statut, Verdict, lire_expression, vers_sympy
from ..mathengine.parser import ErreurLecture
from ..privacy.pii import filtrer


class Enseignant(Protocol):
    def cours(self, kc: str) -> str: ...
    def retour(self, item: Item, verdict: Verdict) -> str: ...
    def exemple_corrige(self, item: Item) -> str: ...
    def indice(self, item: Item) -> str: ...


@dataclass
class EnseignantDeterministe:
    contenu: Contenu

    def cours(self, kc: str) -> str:
        k = self.contenu.graphe.kcs[kc]
        return f"{k.titre} ({k.niveau}). {self.contenu.cours[kc]}"

    def retour(self, item: Item, verdict: Verdict) -> str:
        if verdict.statut is Statut.CORRECT:
            return "Exact !"
        if verdict.statut is Statut.FORME:
            return verdict.message
        if verdict.statut is Statut.ILLISIBLE:
            return verdict.message + " Vérifie l'écriture (parenthèses, opérations)."
        if verdict.erreur_type:
            e = self.contenu.erreurs[verdict.erreur_type]
            return f"Je crois reconnaître une erreur fréquente : {e.titre.lower()}. {e.remediation}"
        return verdict.message + f" La bonne réponse était : {item.spec.affichage()}."

    def exemple_corrige(self, item: Item) -> str:
        etapes = "\n".join(f"  {l}" for l in item.solution_redigee)
        return f"Exemple corrigé — {item.enonce}\n{etapes}\n  Réponse : {item.spec.affichage()}"

    def indice(self, item: Item) -> str:
        if item.solution_redigee:
            return f"Indice : {item.solution_redigee[0].split(':')[0]}…" if ":" in item.solution_redigee[0] else \
                "Indice : " + self.contenu.cours[item.kcs[0]].split(".")[0] + "."
        return "Indice : relis la méthode dans le cours."


# ---------------------------------------------------------------------- passerelle LLM


class ClientLLM(Protocol):
    """Client d'un modèle auto-hébergé ou d'un fournisseur UE (API compatible chat)."""

    region: str  # "UE" exigé
    nom: str

    def completer(self, systeme: str, utilisateur: str) -> str: ...


class RegionNonAutorisee(RuntimeError):
    pass


_EGALITE = re.compile(r"(-?[\d,./×x*+\-() ]+?)\s*=\s*(-?\d+(?:[.,]\d+)?(?:/\d+)?)(?![\d/])")


def egalites_fausses(texte: str) -> list[str]:
    """Égalités purement numériques du texte qui sont FAUSSES (« 3 × 4 = 13 »)."""
    fausses = []
    for g, d in _EGALITE.findall(texte):
        g = g.strip().strip("(").strip()
        if not re.search(r"\d", g) or re.search(r"[a-wyzA-Z]", g) or not re.search(r"[×*+\-/]", g.lstrip("-")):
            continue
        try:
            vg, vd = vers_sympy(lire_expression(g)), vers_sympy(lire_expression(d))
        except (ErreurLecture, ValueError, ZeroDivisionError):
            continue
        if vg.free_symbols or sympy.simplify(vg - vd) != 0:
            fausses.append(f"{g} = {d}")
    return fausses


SYSTEME = (
    "Tu es un professeur de mathématiques bienveillant pour des collégiens français. "
    "Tu reformules l'explication fournie, en phrases courtes, avec le vocabulaire du programme "
    "(développer, réduire, factoriser, membre, solution). Tu ne donnes jamais la réponse finale de "
    "l'exercice en cours. Tu ne demandes ni ne mentionnes aucune information personnelle. "
    "Tu restes strictement sur les mathématiques."
)


@dataclass
class PasserelleLLM:
    client: ClientLLM
    repli: EnseignantDeterministe
    journal_refus: list[str] | None = None

    def __post_init__(self) -> None:
        if getattr(self.client, "region", None) != "UE":
            raise RegionNonAutorisee(
                f"{getattr(self.client, 'nom', '?')} : seuls les modèles hébergés dans l'UE (auto-hébergés ou "
                "fournisseur UE sous contrat art. 28) peuvent recevoir du texte d'élève."
            )
        if self.journal_refus is None:
            self.journal_refus = []

    def reformuler(self, item: Item, verdict: Verdict, question_eleve: str = "", prenom: str = "") -> str:
        base = self.repli.retour(item, verdict)
        q = filtrer(question_eleve, (prenom,)).texte if question_eleve else ""
        demande = (
            f"Exercice : {item.enonce}\nVerdict du moteur : {verdict.statut.value}"
            + (f" ; erreur reconnue : {verdict.erreur_type}" if verdict.erreur_type else "")
            + f"\nExplication validée à reformuler : {base}"
            + (f"\nQuestion de l'élève : {q}" if q else "")
        )
        try:
            texte = self.client.completer(SYSTEME, demande)
        except Exception as e:  # réseau, quota… : on ne bloque jamais l'élève
            self.journal_refus.append(f"erreur client : {e}")  # type: ignore[union-attr]
            return base
        return self._controler(texte, item, verdict, base)

    def _controler(self, texte: str, item: Item, verdict: Verdict, base: str) -> str:
        fausses = egalites_fausses(texte)
        if fausses:
            self.journal_refus.append(f"calcul faux : {fausses}")  # type: ignore[union-attr]
            return base
        if verdict.statut is not Statut.CORRECT and item.spec.type != "booleen":
            attendu = item.spec.affichage().replace(" ", "")
            if attendu and len(attendu) > 1 and attendu in texte.replace(" ", ""):
                self.journal_refus.append("réponse divulguée")  # type: ignore[union-attr]
                return base
        if filtrer(texte).modifie:
            self.journal_refus.append("donnée personnelle dans la réponse")  # type: ignore[union-attr]
            return base
        return texte
