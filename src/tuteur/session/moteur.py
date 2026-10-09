"""Moteur de session : machine à états explicite et politique pédagogique par RÈGLES.

    RÉVISION (rappels espacés dus) → DIAGNOSTIC → REMÉDIATION (parcours) → TRANSFERT → TERMINÉ

Aucune de ces décisions n'a besoin d'un LLM : ce sont des règles explicites, versionnées
(`VERSION_POLITIQUE`) et journalisées. Chaque décision enregistre ses options, l'option choisie
et la PROBABILITÉ de l'avoir choisie (aléa contrôlé entre options pédagogiquement équivalentes) :
c'est ce qui rendra possible, plus tard, l'évaluation hors ligne d'autres politiques (bandits /
RL hors ligne) à partir des trajectoires réelles.

Règles de la remédiation (KC courante k) :
  * première rencontre et P(k) < 0,6 → cours puis exemple corrigé (effet de l'exemple travaillé) ;
  * difficulté : +1 après 2 réussites de suite, −1 après 2 échecs de suite ;
  * 2 échecs de suite → exemple corrigé de l'exercice raté ;
  * erreur typique dont la KC est un prérequis non maîtrisé de k → on y descend immédiatement ;
  * k résiste (≥ 8 tentatives, P < 0,4) → on descend sur ses prérequis forts non sûrs ;
    s'il n'y en a pas → escalade vers un humain (enseignant), on n'insiste pas indéfiniment ;
  * k maîtrisée (critères stricts) → KC suivante du parcours, rappel planifié à J+1.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable

from ..contenu import Contenu
from ..diagnostic import Diagnostic, ParamsDiagnostic, ResultatDiagnostic
from ..exercises import Item
from ..knowledge import CRITERES_DEFAUT, CriteresMaitrise, ProfilEleve, Tentative, prior_selon_niveau
from ..mathengine import Statut, Verdict
from ..storage import Evenement, JournalEvenements
from ..teacher import Enseignant, EnseignantDeterministe

VERSION_POLITIQUE = "regles-v1"


class Mode(StrEnum):
    REVISION = "revision"
    DIAGNOSTIC = "diagnostic"
    REMEDIATION = "remediation"
    TRANSFERT = "transfert"
    TERMINE = "termine"


class TypeAction(StrEnum):
    QUESTION = "question"
    COURS = "cours"
    EXEMPLE = "exemple"
    MESSAGE = "message"
    FIN = "fin"


@dataclass(frozen=True)
class Action:
    type: TypeAction
    texte: str
    mode: Mode
    item: Item | None = None
    raison: str = ""


@dataclass(frozen=True)
class Retour:
    verdict: Verdict
    texte: str
    etapes: tuple[dict, ...] = ()  # résolution rédigée : verdict ligne par ligne


@dataclass(frozen=True)
class Decision:
    mode: str
    kc: str | None
    options: tuple[str, ...]
    choix: str
    proba: float
    raison: str


@dataclass
class _SuiviKC:
    intro_faite: bool = False
    difficulte: int = 1
    succes_suite: int = 0
    echecs_suite: int = 0
    tentatives: int = 0
    descente_faite: bool = False


@dataclass
class Session:
    contenu: Contenu
    profil: ProfilEleve
    chapitre: str
    journal: JournalEvenements | None = None
    enseignant: Enseignant | None = None
    graine: int = 0
    epsilon: float = 0.15
    criteres: CriteresMaitrise = CRITERES_DEFAUT
    params_diagnostic: ParamsDiagnostic = field(default_factory=ParamsDiagnostic)
    horloge: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    tentatives_max_kc: int = 15
    seuil_a_revoir: float = 0.7  # au-delà, une KC qui « résiste » est reportée en révision, pas escaladée

    def __post_init__(self) -> None:
        self.g = self.contenu.graphe
        self.cibles = list(self.g.chapitres[self.chapitre].cibles)
        self.enseignant = self.enseignant or EnseignantDeterministe(self.contenu)
        self.rng = random.Random(self.graine)
        self.mode = Mode.REVISION
        self.file: list[str] = []
        self.suivi: dict[str, _SuiviKC] = {}
        self.a_faire: list[Action] = []  # actions non-question en attente (cours, exemples, messages)
        self.item_courant: Item | None = None
        self.mode_item: Mode | None = None
        self.aide = False
        self.decisions: list[Decision] = []
        self.escalades: list[str] = []
        self.a_revoir: list[str] = []
        self.resultat_diagnostic: ResultatDiagnostic | None = None
        self.revisions = self._revisions_dues()
        self.transferts: list[str] = []
        self._transfert_reessaye: set[str] = set()
        self._compteur = 0
        self.diagnostic = Diagnostic(
            self.contenu, self.cibles, self.profil.niveau_scolaire,
            priors={k: e.p for k, e in self.profil.etats.items() if e.tentatives},
            params=self.params_diagnostic, graine=self.graine,
        )
        self._log("session_debut", {"chapitre": self.chapitre, "niveau": self.profil.niveau_scolaire, "revisions": self.revisions})

    # ------------------------------------------------------------------ outils
    def _prior(self, kc: str) -> float:
        return prior_selon_niveau(self.g.kcs[kc].niveau, self.profil.niveau_scolaire)

    def _p(self, kc: str) -> float:
        return self.profil.etat(kc, self._prior(kc)).p

    def _maitrisee(self, kc: str) -> bool:
        return self.profil.etat(kc, self._prior(kc)).est_maitrisee(self.criteres)

    def _log(self, type_: str, donnees: dict) -> None:
        if self.journal is not None:
            self.journal.ajouter(Evenement(self.profil.eleve, self.horloge(), type_, donnees, self.contenu.version, VERSION_POLITIQUE))

    def _decider(self, kc: str | None, options: list[str], preferee: str | None, raison: str) -> str:
        """Choix avec aléa contrôlé : `preferee` avec proba 1 − ε (+ sa part de ε), sinon uniforme."""
        if preferee is None or len(options) == 1:
            choix = self.rng.choice(options) if preferee is None else preferee
            proba = 1.0 / len(options) if preferee is None else 1.0
        else:
            choix = preferee if self.rng.random() >= self.epsilon else self.rng.choice(options)
            proba = (1 - self.epsilon) + self.epsilon / len(options) if choix == preferee else self.epsilon / len(options)
        d = Decision(self.mode.value, kc, tuple(options), choix, round(proba, 4), raison)
        self.decisions.append(d)
        self._log("decision", asdict(d))
        return choix

    def _nouvel_item(self, kc: str, difficulte: int, diagnostic_seulement: bool = False) -> Item:
        modeles = self.contenu.modeles_diagnostic(kc) if diagnostic_seulement else self.contenu.modeles_pratique(kc)
        usages = {m.id: sum(1 for t in self.profil.etat(kc, self._prior(kc)).tentatives if t.modele == m.id) for m in modeles}
        moins = min(usages.values())
        options = sorted(m for m, u in usages.items() if u == moins)
        choix = self._decider(kc, options, None, "variante la moins pratiquée (aléa entre ex aequo)")
        self._compteur += 1
        return self.contenu.modeles[choix].instancier(self.graine * 100_000 + self._compteur, difficulte)

    def _revisions_dues(self) -> list[str]:
        maintenant = self.horloge()
        dues = [k for k, e in self.profil.etats.items()
                if e.maitrisee_le is not None and not e.consolidee and maintenant - e.maitrisee_le >= self.criteres.delai_consolidation]
        return sorted(dues)[:3]

    # ------------------------------------------------------------------ boucle
    def prochaine_action(self) -> Action:
        if self.item_courant is not None:
            return Action(TypeAction.QUESTION, self.item_courant.enonce, self.mode, self.item_courant)
        if self.a_faire:
            return self.a_faire.pop(0)
        if self.mode is Mode.REVISION:
            if self.revisions:
                kc = self.revisions.pop(0)
                return self._poser(self._nouvel_item(kc, 2), Mode.REVISION, f"rappel espacé de « {self.g.kcs[kc].titre} »")
            self.mode = Mode.DIAGNOSTIC
        if self.mode is Mode.DIAGNOSTIC:
            item = self.diagnostic.prochaine_question()
            if item is not None:
                return self._poser(item, Mode.DIAGNOSTIC, self._raison_diagnostic(item))
            self._terminer_diagnostic()
            return self.prochaine_action()
        if self.mode is Mode.REMEDIATION:
            return self._action_remediation()
        if self.mode is Mode.TRANSFERT:
            if self.transferts:
                kc = self.transferts.pop(0)
                return self._poser(self._nouvel_item(kc, 2), Mode.TRANSFERT, f"vérification au niveau du chapitre : {self.g.kcs[kc].titre}")
            self.mode = Mode.TERMINE
        return self._fin()

    def _raison_diagnostic(self, item: Item) -> str:
        if not self.diagnostic.observations:
            return ("on commence par un exercice complet du chapitre : s'il est réussi, il valide d'un coup "
                    "toutes les notions qu'il contient")
        if item.kcs[0] in self.cibles:
            return "exercice du chapitre, pour vérifier ce que tu sais déjà faire"
        return "un exercice précédent n'a pas marché : on vérifie une des notions qu'il utilisait"

    def _poser(self, item: Item, mode: Mode, raison: str) -> Action:
        self.item_courant, self.mode_item, self.aide = item, mode, False
        self._log("question", {"item": item.cle, "modele": item.modele, "kcs": list(item.kcs), "mode": mode.value})
        return Action(TypeAction.QUESTION, item.enonce, mode, item, raison)

    def demander_aide(self) -> str:
        if self.item_courant is None:
            return "Aucune question en cours."
        self.aide = True
        self._log("aide", {"item": self.item_courant.cle})
        return self.enseignant.indice(self.item_courant)  # type: ignore[union-attr]

    def repondre(self, saisie: str, lignes: list[str] | None = None) -> Retour:
        """`lignes` : résolution rédigée ligne par ligne (« la copie »), la dernière donnant la réponse.
        La première ligne fausse est localisée et son erreur typique devient une preuve directe."""
        if self.item_courant is None or self.mode_item is None:
            raise RuntimeError("aucune question en attente")
        item, mode = self.item_courant, self.mode_item
        etapes: tuple[dict, ...] = ()
        if lignes and item.etapes_possibles:
            verdict, rapport = item.corriger_etapes(lignes)
            saisie = " | ".join(l for l in lignes if l.strip())
            if rapport is not None:
                # comme un professeur : on signale la PREMIÈRE erreur, sans juger ce qui en découle
                premiere = rapport.premiere_erreur
                etapes = tuple(
                    {"texte": l.texte,
                     "statut": "suite" if premiere is not None and l.index > premiere else l.statut.value,
                     "erreur": self.contenu.erreurs[l.erreur_type].titre if l.erreur_type and l.index == premiere else None}
                    for l in rapport.lignes[1:]
                )
        else:
            verdict = item.corriger(lignes[-1] if lignes else saisie)
        self.item_courant = None
        if verdict.statut is Statut.ILLISIBLE:
            self.item_courant = item  # on repose la même question
            return Retour(verdict, self.enseignant.retour(item, verdict), etapes)  # type: ignore[union-attr]
        maintenant = self.horloge()
        apprentissage = mode is not Mode.DIAGNOSTIC
        self._log("reponse", {
            "item": item.cle, "modele": item.modele, "difficulte": item.difficulte, "kcs": list(item.kcs),
            "saisie": saisie[:200], "statut": verdict.statut.value, "erreur": verdict.erreur_type, "aide": self.aide,
            "p_guess": item.proba_hasard, "mode": mode.value, "apprentissage": apprentissage,
        })
        appliquer_reponse(self.profil, self.contenu, item, verdict, self.aide, maintenant, apprentissage, self.criteres)
        texte = self.enseignant.retour(item, verdict)  # type: ignore[union-attr]
        if mode is Mode.DIAGNOSTIC:
            self.diagnostic.enregistrer(item, verdict)
            texte = "Réponse enregistrée." if verdict.juste else "Réponse enregistrée (on fait le point à la fin du test)."
            etapes = ()  # pendant le test, on ne corrige pas ligne par ligne devant l'élève
        elif mode is Mode.REMEDIATION:
            self._apres_remediation(item, verdict)
        elif mode is Mode.TRANSFERT and not verdict.juste:
            kc = item.kcs[0]
            if kc not in self._transfert_reessaye:
                self._transfert_reessaye.add(kc)
                self.file.append(kc)
                self.mode = Mode.REMEDIATION
                self.a_faire.append(Action(TypeAction.MESSAGE, f"On retravaille « {self.g.kcs[kc].titre} » encore un peu.", self.mode))
        if etapes and verdict.erreur_type and verdict.statut is Statut.INCORRECT and mode is not Mode.DIAGNOSTIC:
            texte = verdict.message + " " + texte
        return Retour(verdict, texte, etapes)

    # ------------------------------------------------------------------ diagnostic → parcours
    def _terminer_diagnostic(self) -> None:
        r = self.diagnostic.resultat()
        self.resultat_diagnostic = r
        for k, p in r.marginales.items():
            self.profil.etat(k, p).p = p
        self.file = [k for k in r.parcours if not self._maitrisee(k)]
        self._log("diagnostic_fin", {"marginales": r.marginales, "frontiere": r.frontiere, "parcours": self.file,
                                     "raison": r.raison_arret, "explication": r.explication(self.contenu)})
        racines = [k for k in r.frontiere if k not in self.cibles]
        hypotheses = [k for k in r.hypotheses if k not in self.cibles]
        if racines:
            tete = ("Bilan du test : on a trouvé d'où viennent tes difficultés. On les retravaille avant le chapitre, "
                    "c'est ce qui débloquera la suite.")
        elif hypotheses:
            tete = "Bilan du test : rien n'est confirmé, mais quelques notions sont à vérifier ; on le fera en t'entraînant."
        else:
            tete = "Bilan du test : tes bases sont solides, on attaque le chapitre."
        texte = "\n".join([tete, *r.explication_eleve(self.contenu, tuple(self.cibles))])
        self.a_faire.append(Action(TypeAction.MESSAGE, texte, Mode.REMEDIATION, raison="résultat du diagnostic"))
        self.mode = Mode.REMEDIATION

    # ------------------------------------------------------------------ remédiation
    def _kc_courante(self) -> str | None:
        while self.file and (self._maitrisee(self.file[0]) or self.file[0] in self.escalades or self.file[0] in self.a_revoir):
            self.file.pop(0)
        return self.file[0] if self.file else None

    def _action_remediation(self) -> Action:
        kc = self._kc_courante()
        if kc is None:
            self.mode = Mode.TRANSFERT
            self.transferts = [c for c in self.cibles if c not in self.escalades and c not in self.a_revoir]
            return self.prochaine_action()
        s = self.suivi.setdefault(kc, _SuiviKC())
        if not s.intro_faite:
            s.intro_faite = True
            p = self._p(kc)
            choix = self._decider(kc, ["cours_puis_exemple", "pratique_directe"],
                                  "cours_puis_exemple" if p < 0.6 else "pratique_directe",
                                  f"première rencontre, P(maîtrise) = {p:.2f}")
            if choix == "cours_puis_exemple":
                exemple = self._nouvel_item(kc, 1)
                self.a_faire.append(Action(TypeAction.EXEMPLE, self.enseignant.exemple_corrige(exemple), self.mode, exemple))  # type: ignore[union-attr]
                return Action(TypeAction.COURS, self.enseignant.cours(kc), self.mode, raison="nouvelle compétence")  # type: ignore[union-attr]
        return self._poser(self._nouvel_item(kc, s.difficulte), Mode.REMEDIATION, f"entraînement : {self.g.kcs[kc].titre}")

    def _apres_remediation(self, item: Item, verdict: Verdict) -> None:
        kc = item.kcs[0]
        s = self.suivi.setdefault(kc, _SuiviKC())
        s.tentatives += 1
        diffs = sorted({d for m in self.contenu.modeles_pratique(kc) for d in m.difficultes})
        if verdict.juste:
            s.succes_suite, s.echecs_suite = s.succes_suite + 1, 0
            if s.succes_suite >= 2 and s.difficulte < diffs[-1]:
                s.difficulte, s.succes_suite = s.difficulte + 1, 0
        else:
            s.echecs_suite, s.succes_suite = s.echecs_suite + 1, 0
            if s.echecs_suite >= 2:
                s.difficulte = max(diffs[0], s.difficulte - 1)
                self.a_faire.append(Action(TypeAction.EXEMPLE, self.enseignant.exemple_corrige(item), self.mode, item,  # type: ignore[union-attr]
                                           "deux échecs de suite : exemple corrigé"))
                s.echecs_suite = 0
        # descente dynamique sur la KC d'une erreur typique
        if verdict.erreur_type:
            kc_err = self.contenu.erreurs[verdict.erreur_type].kc
            if kc_err != kc and kc_err not in self.file and kc_err in self.g.ancetres(kc, inclure=False) and not self._maitrisee(kc_err):
                self._decider(kc, [f"descendre:{kc_err}"], f"descendre:{kc_err}", f"erreur typique « {verdict.erreur_type} »")
                self.file.insert(0, kc_err)
                self.a_faire.append(Action(TypeAction.MESSAGE, f"Cette erreur vient de « {self.g.kcs[kc_err].titre} » ({self.g.kcs[kc_err].niveau}) : on la retravaille d'abord.", self.mode))
                return
        if self._maitrisee(kc):
            self._log("kc_maitrisee", {"kc": kc, "tentatives": s.tentatives})
            self.a_faire.append(Action(TypeAction.MESSAGE, f"Compétence maîtrisée : {self.g.kcs[kc].titre}. Un rappel est prévu demain.", self.mode))
            return
        if s.tentatives >= 8 and self._p(kc) < 0.4 and not s.descente_faite:
            s.descente_faite = True
            prereqs = [p for p in self.g.prereqs(kc, True) if self._p(p) < 0.9 and not self._maitrisee(p) and p not in self.file]
            if prereqs:
                self._decider(kc, [f"descendre:{p}" for p in prereqs], f"descendre:{prereqs[0]}", "la compétence résiste")
                self.file[0:0] = prereqs
                self.a_faire.append(Action(TypeAction.MESSAGE, "On consolide d'abord une notion plus ancienne.", self.mode))
                return
        if s.tentatives >= self.tentatives_max_kc or (s.descente_faite and s.tentatives >= 12 and self._p(kc) < 0.4):
            if self._p(kc) >= self.seuil_a_revoir:
                # globalement réussie mais erreurs récurrentes : pas d'escalade, on y revient plus tard
                self.a_revoir.append(kc)
                self._log("a_revoir", {"kc": kc, "p": self._p(kc), "tentatives": s.tentatives})
                self.a_faire.append(Action(TypeAction.MESSAGE, f"« {self.g.kcs[kc].titre} » est presque acquise : on avance, et on y reviendra lors d'une prochaine révision.", self.mode))
                return
            self.escalades.append(kc)
            self._log("escalade", {"kc": kc, "p": self._p(kc), "tentatives": s.tentatives})
            self.a_faire.append(Action(TypeAction.MESSAGE, f"« {self.g.kcs[kc].titre} » résiste : je te conseille d'en parler à ton professeur. On continue avec la suite.", self.mode))

    def _fin(self) -> Action:
        maitrisees = [k for k in self.cibles if self._maitrisee(k)]
        a_reprendre = [k for k in dict.fromkeys(self.a_revoir + [c for c in self.cibles if c not in maitrisees])
                       if k not in self.escalades]
        texte = (f"Séance terminée. Compétences du chapitre maîtrisées : {len(maitrisees)}/{len(self.cibles)}."
                 + (f" On reprendra la prochaine fois : {', '.join(self.g.kcs[k].titre for k in a_reprendre)}." if a_reprendre else "")
                 + (f" À voir avec ton professeur : {', '.join(self.g.kcs[k].titre for k in self.escalades)}." if self.escalades else ""))
        self._log("session_fin", {"maitrisees": maitrisees, "escalades": self.escalades, "a_revoir": self.a_revoir})
        return Action(TypeAction.FIN, texte, Mode.TERMINE)


def appliquer_reponse(profil: ProfilEleve, contenu: Contenu, item: Item, verdict: Verdict, aide: bool, quand: datetime,
                      apprentissage: bool, criteres: CriteresMaitrise = CRITERES_DEFAUT) -> None:
    """Mise à jour du profil — partagée par la session en direct et par la reprojection du journal."""
    g = contenu.graphe
    for i, kc in enumerate(item.kcs):
        prior = prior_selon_niveau(g.kcs[kc].niveau, profil.niveau_scolaire)
        t = Tentative(item.cle, item.modele, item.difficulte, verdict.statut, verdict.erreur_type if i == 0 else None, aide, quand, principale=(i == 0))
        profil.enregistrer(kc, prior, t, item.proba_hasard, criteres=criteres, apprentissage=apprentissage)
    if verdict.erreur_type:
        kc_err = contenu.erreurs[verdict.erreur_type].kc
        if kc_err not in item.kcs:
            # l'erreur typique est une preuve (négative) sur SA KC
            prior = prior_selon_niveau(g.kcs[kc_err].niveau, profil.niveau_scolaire)
            t = Tentative(item.cle, item.modele, item.difficulte, Statut.INCORRECT, verdict.erreur_type, aide, quand, principale=True)
            profil.enregistrer(kc_err, prior, t, 0.02, criteres=criteres, apprentissage=False)


def reconstruire_profil(journal: JournalEvenements, contenu: Contenu, eleve: str, niveau: str,
                        criteres: CriteresMaitrise = CRITERES_DEFAUT) -> ProfilEleve:
    """Projection : rejoue le journal pour reconstruire l'état (après changement de modèle, etc.)."""
    profil = ProfilEleve(eleve, niveau)
    for e in journal.lire(eleve, ("reponse", "diagnostic_fin")):
        if e.type == "diagnostic_fin":
            for k, p in e.donnees["marginales"].items():
                profil.etat(k, p).p = p
            continue
        d = e.donnees
        modele = contenu.modeles[d["modele"]]
        cle = d["item"]
        graine = int(cle.split("#")[1].split("/")[0])
        item = modele.instancier(graine, d["difficulte"])
        verdict = Verdict(Statut(d["statut"]), "", d["erreur"])
        appliquer_reponse(profil, contenu, item, verdict, d["aide"], e.quand, d["apprentissage"], criteres)
    return profil


def horloge_fixe(depart: datetime) -> Callable[[], datetime]:
    """Horloge contrôlable pour les tests et la simulation."""
    etat = {"t": depart}

    def h() -> datetime:
        return etat["t"]

    h.avancer = lambda **kw: etat.__setitem__("t", etat["t"] + timedelta(**kw))  # type: ignore[attr-defined]
    return h
