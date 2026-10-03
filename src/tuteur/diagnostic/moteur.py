"""Diagnostic adaptatif sur le sous-graphe des prérequis d'un chapitre.

Modèle (proche de la Knowledge Space Theory / réseau bayésien « noisy-AND ») :
  * état de connaissance = vecteur booléen « KC maîtrisée ? » sur le sous-graphe ;
  * a priori : une KC est très improbable si l'un de ses prérequis FORTS n'est pas maîtrisé
    (les états sont presque « fermés vers le bas ») ;
  * vraisemblance d'une réponse : un exercice MOBILISE plusieurs compétences (toutes ses parties
    techniques) ; P(réussite) = 1 − slip si TOUTES sont maîtrisées, guess sinon. Une réussite sur
    un exercice large valide donc d'un coup tous les acquis qu'il contient. Une erreur typique
    reconnue pointe vers SA KC (souvent plus basse) : c'est un raccourci vers la racine ;
  * inférence : population d'états (particules) + rééchantillonnage + mouvements de
    Metropolis-Hastings (pas d'appauvrissement des particules) ;
  * stratégie « descendante » (défaut) : on teste d'abord le PRÉSENT, avec l'exercice le plus
    large du chapitre au niveau le plus difficile ; on ne descend que dans les parties d'un
    exercice raté (et dans la KC d'une erreur typique), avec des exercices de plus en plus ciblés ;
    une compétence validée par une réussite plus haut n'est jamais re-testée ;
  * parmi les questions autorisées : gain d'information attendu maximal (réduction d'entropie des
    marginales) par seconde de réponse estimée ;
  * arrêt : toutes les marginales tranchées, ou gain attendu négligeable, ou budget atteint.

Tout est déterministe à graine fixée, explicable (on garde les preuves), et ne fait appel à
aucun LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..contenu import Contenu
from ..exercises import Item
from ..graph import rang_niveau
from ..knowledge.bkt import prior_selon_niveau
from ..mathengine import Statut, Verdict


@dataclass(frozen=True)
class ParamsDiagnostic:
    n_particules: int = 2000
    p_slip: float = 0.10
    q_erreur_typique: float = 0.45  # P(produire l'erreur typique | sa KC non maîtrisée)
    fuite: float = 0.06  # P(KC maîtrisée | un prérequis fort non maîtrisé)
    penalite_faible: float = 0.75  # facteur si un prérequis faible n'est pas maîtrisé
    seuil_bas: float = 0.15
    seuil_haut: float = 0.90
    questions_max: int = 18
    questions_min: int = 3
    max_par_kc: int = 3
    gain_min: float = 0.015  # bits
    difficulte: int = 2
    qcm: bool = False
    balayages_mh: int = 4
    poids_temps: float = 0.5  # 1 = gain par seconde ; 0 = ignorer le temps (0,5 : compromis, évite les questions trop faciles)
    strategie: str = "descendante"  # « descendante » (part du présent) ou « exhaustive » (tout le sous-graphe)


@dataclass(frozen=True)
class Observation:
    kc: str
    item: str
    statut: Statut
    erreur_type: str | None
    p_guess: float
    kcs: tuple[str, ...] = ()  # compétences mobilisées par l'exercice (kcs[0] = principale)

    @property
    def mobilisees(self) -> tuple[str, ...]:
        return self.kcs or (self.kc,)


@dataclass
class ResultatDiagnostic:
    marginales: dict[str, float]
    frontiere: list[str]
    parcours: list[str]
    observations: list[Observation]
    raison_arret: str

    def maitrisee(self, kc: str, seuil: float = 0.5) -> bool:
        return self.marginales[kc] >= seuil

    def explication_eleve(self, contenu: Contenu) -> list[str]:
        """Version pour l'élève : concrète, sans probabilités ni identifiants."""
        lignes = []
        for kc in self.frontiere:
            k = contenu.graphe.kcs[kc]
            ratees = [o for o in self.observations if o.statut is not Statut.CORRECT
                      and (o.kc == kc or (o.erreur_type and contenu.erreurs[o.erreur_type].kc == kc))]
            erreurs = sorted({contenu.erreurs[o.erreur_type].titre.lower() for o in ratees if o.erreur_type})
            if ratees:
                detail = f"{len(ratees)} question{'s' if len(ratees) > 1 else ''} de ce type t'{'ont' if len(ratees) > 1 else 'a'} posé problème"
            else:
                detail = "c'est la base qui manque pour la suite"
            if erreurs:
                detail += f" (erreur repérée : {erreurs[0]})"
            lignes.append(f"{k.titre} ({k.niveau}) : {detail}.")
        return lignes

    def explication(self, contenu: Contenu) -> list[str]:
        """Justification détaillée (enseignant, parent, export) des conclusions."""
        lignes = []
        for kc in self.frontiere:
            preuves = [o for o in self.observations
                       if kc in o.mobilisees or (o.erreur_type and contenu.erreurs[o.erreur_type].kc == kc)]
            detail = ", ".join(
                f"{'réussi' if o.statut is Statut.CORRECT else 'échoué'} ({o.item.split('@')[0]}"
                + (f", erreur typique : {contenu.erreurs[o.erreur_type].titre}" if o.erreur_type else "")
                + ")"
                for o in preuves
            )
            prereqs_ok = [contenu.graphe.kcs[p].titre for p in contenu.graphe.prereqs(kc, True) if self.marginales.get(p, 1) >= 0.5]
            lignes.append(
                f"« {contenu.graphe.kcs[kc].titre} » ({contenu.graphe.kcs[kc].niveau}) est une lacune racine : "
                f"P(maîtrise) = {self.marginales[kc]:.2f}"
                + (f" ; preuves : {detail}" if detail else "")
                + (f" ; ses prérequis semblent acquis : {', '.join(prereqs_ok)}" if prereqs_ok else "")
                + "."
            )
        return lignes


def _entropie(p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-(p * np.log2(p) + (1 - p) * np.log2(1 - p)).sum())


class Diagnostic:
    def __init__(
        self,
        contenu: Contenu,
        cibles: list[str],
        niveau_eleve: str,
        priors: dict[str, float] | None = None,
        params: ParamsDiagnostic = ParamsDiagnostic(),
        graine: int = 0,
    ):
        self.c = contenu
        self.g = contenu.graphe
        self.params = params
        self.cibles = list(cibles)
        self.niveau_eleve = niveau_eleve
        self.kcs = self.g.sous_graphe(self.cibles)
        self.idx = {k: i for i, k in enumerate(self.kcs)}
        self.rng = np.random.default_rng(graine)
        self.graine = graine
        priors = priors or {}
        self.prior = np.array([priors.get(k, prior_selon_niveau(self.g.kcs[k].niveau, niveau_eleve)) for k in self.kcs])
        self.forts = [[self.idx[p] for p in self.g.prereqs(k, True) if p in self.idx] for k in self.kcs]
        self.faibles = [[self.idx[p.kc] for p in self.g.kcs[k].prereqs if not p.fort and p.kc in self.idx] for k in self.kcs]
        self.p_cond = self._calibrer_conditionnelles()
        self.etats = self._echantillonner(params.n_particules)
        self.observations: list[Observation] = []
        self._items_poses: set[str] = set()
        self._compteur_graines = 0
        self.termine = False
        self.raison_arret = ""

    # ------------------------------------------------------------------ a priori
    def _calibrer_conditionnelles(self) -> np.ndarray:
        """P(KC | prérequis forts OK), ajustée pour rapprocher la marginale a priori du prior de la KC,
        mais PLAFONNÉE (+0,25) : sans plafond, une KC profonde hériterait d'une quasi-certitude dès que
        ses prérequis sont observés acquis — faux pour une notion de l'année pas encore travaillée."""
        p_cond = self.prior.copy()
        for _ in range(3):
            etats = self._echantillonner(4000, p_cond)
            for i in range(len(self.kcs)):
                if self.forts[i]:
                    ok = etats[:, self.forts[i]].all(axis=1).mean()
                    p_cond[i] = np.clip(self.prior[i] / max(ok, 1e-3), self.prior[i], min(0.95, self.prior[i] + 0.25))
        return p_cond

    def _echantillonner(self, n: int, p_cond: np.ndarray | None = None) -> np.ndarray:
        p_cond = self.p_cond if p_cond is None else p_cond
        e = np.zeros((n, len(self.kcs)), dtype=bool)
        for i in range(len(self.kcs)):  # ordre topologique
            p = np.full(n, p_cond[i])
            if self.forts[i]:
                p = np.where(e[:, self.forts[i]].all(axis=1), p, self.params.fuite)
            for j in self.faibles[i]:
                p = np.where(e[:, j], p, p * self.params.penalite_faible)
            e[:, i] = self.rng.random(n) < p
        return e

    def _log_prior(self, e: np.ndarray) -> np.ndarray:
        lp = np.zeros(len(e))
        for i in range(len(self.kcs)):
            p = np.full(len(e), self.p_cond[i])
            if self.forts[i]:
                p = np.where(e[:, self.forts[i]].all(axis=1), p, self.params.fuite)
            for j in self.faibles[i]:
                p = np.where(e[:, j], p, p * self.params.penalite_faible)
            lp += np.log(np.where(e[:, i], p, 1 - p))
        return lp

    # ------------------------------------------------------------------ vraisemblance
    def _vraisemblance(self, e: np.ndarray, o: Observation) -> np.ndarray:
        pr = self.params
        colonnes = [self.idx[k] for k in o.mobilisees if k in self.idx]
        m = e[:, colonnes].all(axis=1)  # réussir exige TOUTES les compétences mobilisées
        if o.statut is Statut.CORRECT:
            return np.where(m, 1 - pr.p_slip, o.p_guess)
        if o.statut is Statut.INCORRECT:
            if o.erreur_type:
                kc_err = self.c.erreurs[o.erreur_type].kc
                if kc_err in self.idx:
                    m_err = e[:, self.idx[kc_err]]
                    # l'erreur typique est surtout produite quand SA KC n'est pas maîtrisée
                    return np.where(m_err, pr.p_slip * 0.15, pr.q_erreur_typique) * np.where(m, 0.5, 1.0)
            return np.where(m, pr.p_slip, 1 - o.p_guess)
        if o.statut is Statut.FORME:
            return np.where(m, 0.6, 0.35)
        return np.ones(len(e))

    def _log_vraisemblance(self, e: np.ndarray) -> np.ndarray:
        lv = np.zeros(len(e))
        for o in self.observations:
            lv += np.log(self._vraisemblance(e, o))
        return lv

    # ------------------------------------------------------------------ inférence
    def _mettre_a_jour(self, o: Observation) -> None:
        w = self._vraisemblance(self.etats, o)
        w = w / w.sum()
        idx = self.rng.choice(len(self.etats), size=len(self.etats), p=w)
        self.etats = self.etats[idx]
        # mouvements de Metropolis-Hastings : on bascule une KC au hasard par particule
        lp = self._log_prior(self.etats) + self._log_vraisemblance(self.etats)
        n, k = self.etats.shape
        for _ in range(self.params.balayages_mh):
            prop = self.etats.copy()
            col = self.rng.integers(0, k, size=n)
            prop[np.arange(n), col] = ~prop[np.arange(n), col]
            lp_prop = self._log_prior(prop) + self._log_vraisemblance(prop)
            accepte = np.log(self.rng.random(n)) < (lp_prop - lp)
            self.etats[accepte] = prop[accepte]
            lp[accepte] = lp_prop[accepte]

    def marginales(self) -> dict[str, float]:
        m = self.etats.mean(axis=0)
        return {k: float(m[i]) for k, i in self.idx.items()}

    # ------------------------------------------------------------------ choix de la question
    def _item_pour(self, kc: str, difficulte: int | None = None) -> Item | None:
        modeles = self.c.modeles_diagnostic(kc)
        if not modeles:
            return None
        self._compteur_graines += 1
        m = modeles[self._compteur_graines % len(modeles)]
        d = self.params.difficulte if difficulte is None else difficulte
        return m.instancier(self.graine * 10_000 + self._compteur_graines, d, qcm=self.params.qcm)

    def _difficultes(self, kc: str) -> list[int]:
        if self.params.strategie != "descendante":
            return [self.params.difficulte]
        return sorted({d for m in self.c.modeles_diagnostic(kc) for d in m.difficultes}, reverse=True)

    def _epreuve_large(self) -> Item | None:
        """Première question : l'exercice du chapitre qui mobilise le plus de compétences, au niveau
        le plus difficile (« on teste le présent, en ratissant large »)."""
        meilleur: tuple[int, str, int] | None = None
        for kc in self.cibles:
            for m in self.c.modeles_diagnostic(kc):
                d = max(m.difficultes)
                n = len([k for k in m.kcs_mobilisees(d) if k in self.idx])
                if meilleur is None or n > meilleur[0]:
                    meilleur = (n, kc, d)
        return None if meilleur is None else self._item_pour(meilleur[1], meilleur[2])

    def eligibles(self, marg: np.ndarray | None = None) -> set[str]:
        """KC qu'on a le droit de tester. Stratégie descendante : les cibles du chapitre, les parties
        des exercices ratés, la KC des erreurs typiques observées, puis — si l'une d'elles semble non
        acquise — ses prérequis forts (on continue de descendre). Le reste est validé par les acquis."""
        if self.params.strategie != "descendante":
            return set(self.kcs)
        marg = self.etats.mean(axis=0) if marg is None else marg
        el = set(self.cibles)
        echouees: set[str] = set()  # KC directement mises en cause par un échec observé
        for o in self.observations:
            if o.statut in (Statut.INCORRECT, Statut.FORME):
                echouees |= {k for k in o.mobilisees if k in self.idx}
            if o.erreur_type and self.c.erreurs[o.erreur_type].kc in self.idx:
                echouees.add(self.c.erreurs[o.erreur_type].kc)
        el |= echouees
        # on ne descend sous une KC que si un ÉCHEC la met en cause et qu'elle semble non acquise ;
        # une KC simplement pas encore testée se teste d'abord elle-même (on part du présent)
        pile = [k for k in el if k in echouees]
        while pile:
            k = pile.pop()
            if marg[self.idx[k]] < 0.5:
                for p in self.g.prereqs(k):  # prérequis forts ET faibles : on cherche la racine
                    if p in self.idx and p not in el:
                        el.add(p)
                        pile.append(p)
        return el

    def _gain_attendu(self, kc: str, item: Item) -> float:
        e = self.etats
        h0 = _entropie(e.mean(axis=0))
        issues = [Observation(kc, item.cle, Statut.CORRECT, None, item.proba_hasard, item.kcs),
                  Observation(kc, item.cle, Statut.INCORRECT, None, item.proba_hasard, item.kcs)]
        issues += [Observation(kc, item.cle, Statut.INCORRECT, err, item.proba_hasard, item.kcs) for err in item.spec.erreurs]
        lik = np.array([self._vraisemblance(e, o) for o in issues])  # (issues, particules)
        # normalisation : les vraisemblances d'issues « incorrect » se partagent la masse d'échec
        tot = lik.sum(axis=0, keepdims=True)
        lik = lik / tot
        gain = 0.0
        for row in lik:
            p_o = row.mean()
            if p_o < 1e-6:
                continue
            post = (e * row[:, None]).sum(axis=0) / row.sum()
            gain += p_o * (h0 - _entropie(post))
        return gain

    def _compte_kc(self, kc: str) -> int:
        return sum(1 for o in self.observations if o.kc == kc)

    def prochaine_question(self) -> Item | None:
        if self.termine:
            return None
        marg = self.etats.mean(axis=0)
        n = len(self.observations)
        if n >= self.params.questions_max:
            return self._arreter("budget de questions atteint")
        if n == 0 and self.params.strategie == "descendante":
            item = self._epreuve_large()
            if item is not None:
                self._items_poses.add(item.cle)
                return item
        eligibles = self.eligibles(marg)
        a_trancher = [k for k in self.kcs if k in eligibles]
        if n >= self.params.questions_min and all(
            marg[self.idx[k]] < self.params.seuil_bas or marg[self.idx[k]] > self.params.seuil_haut for k in a_trancher
        ):
            return self._arreter("toutes les compétences à vérifier sont tranchées")
        meilleur: tuple[float, Item] | None = None
        for kc in a_trancher:
            if self._compte_kc(kc) >= self.params.max_par_kc:
                continue
            p = marg[self.idx[kc]]
            if n >= self.params.questions_min and (p < 0.05 or p > 0.97):
                continue
            for d in self._difficultes(kc):
                item = self._item_pour(kc, d)
                if item is None:
                    continue
                temps = self.c.modeles[item.modele].temps_estime_s
                score = self._gain_attendu(kc, item) / (temps / 30.0) ** self.params.poids_temps
                if meilleur is None or score > meilleur[0] + 1e-9:
                    meilleur = (score, item)
        if meilleur is None:
            return self._arreter("plus aucune question informative disponible")
        if n >= self.params.questions_min and meilleur[0] < self.params.gain_min:
            return self._arreter("gain d'information attendu négligeable")
        self._items_poses.add(meilleur[1].cle)
        return meilleur[1]

    def _arreter(self, raison: str) -> None:
        self.termine = True
        self.raison_arret = raison
        return None

    def enregistrer(self, item: Item, verdict: Verdict) -> None:
        o = Observation(item.kcs[0], item.cle, verdict.statut, verdict.erreur_type, item.proba_hasard, item.kcs)
        self.observations.append(o)
        if verdict.statut is not Statut.ILLISIBLE:
            self._mettre_a_jour(o)

    # ------------------------------------------------------------------ résultat
    def resultat(self, seuil_parcours: float | None = None) -> ResultatDiagnostic:
        seuil_parcours = self.params.seuil_haut if seuil_parcours is None else seuil_parcours
        marg = self.marginales()
        frontiere = [
            k for k in self.kcs
            if marg[k] < 0.5 and all(marg[p] >= 0.5 for p in self.g.prereqs(k, True) if p in marg)
        ]
        a_travailler = {k for k in self.kcs if marg[k] < seuil_parcours} | set(self.cibles)
        parcours = parcours_remediation(self.c, a_travailler, marg)
        return ResultatDiagnostic(marg, frontiere, parcours, list(self.observations), self.raison_arret or "en cours")


def parcours_remediation(contenu: Contenu, a_travailler: set[str], marginales: dict[str, float]) -> list[str]:
    """Tri topologique des KC à travailler. Départage : niveau le plus bas d'abord, puis la KC qui
    débloque le plus d'autres KC à travailler, puis la moins maîtrisée. Déterministe."""
    g = contenu.graphe
    restants = set(a_travailler)
    ordre: list[str] = []
    while restants:
        prets = [k for k in restants if not any(p in restants for p in g.prereqs(k))]
        if not prets:  # impossible dans un DAG, garde-fou
            prets = list(restants)
        prets.sort(key=lambda k: (rang_niveau(g.kcs[k].niveau), -len(g.descendants(k, restants)), marginales.get(k, 0), k))
        ordre.append(prets[0])
        restants.remove(prets[0])
    return ordre
