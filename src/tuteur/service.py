"""Service applicatif du tuteur, indépendant de tout framework web.

Toute la logique exposée à l'interface élève vit ici. Elle est utilisée par :
  * l'API HTTP FastAPI (`api/app.py`), pour un déploiement serveur ;
  * la version « tout dans le navigateur » (Pyodide, `api/static/local.js`), où ce module
    tourne directement dans la page : aucune donnée d'élève ne quitte l'appareil.

`requete(methode, chemin, corps, jeton)` est le point d'entrée unique, avec les mêmes chemins
que l'API HTTP. Les erreurs sont des `ErreurService(statut, message)`.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .contenu import Contenu, charger
from .knowledge import Niveau, ProfilEleve, prior_selon_niveau
from .mathengine import ErreurLecture, Statut
from .mathengine.latex import latex_vers_texte
from .session import Action, Session, TypeAction, reconstruire_profil
from .storage import CoffreIdentite, JournalEvenements
from .storage.identite import AGE_MAJORITE_NUMERIQUE, FINALITES

NIVEAUX_ELEVE = ("6e", "5e", "4e", "3e")


class ErreurService(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


@dataclass
class Service:
    contenu: Contenu
    coffre: CoffreIdentite
    journal: JournalEvenements
    verrou: threading.RLock = field(default_factory=threading.RLock)
    profils: dict[str, ProfilEleve] = field(default_factory=dict)
    seances: dict[str, tuple[str, Session]] = field(default_factory=dict)  # id séance -> (élève, séance)

    @classmethod
    def creer(cls, dossier_donnees: str | Path | None = None, contenu: Contenu | None = None) -> "Service":
        if dossier_donnees is None:
            coffre, journal = CoffreIdentite(), JournalEvenements()
        else:
            d = Path(dossier_donnees)
            d.mkdir(parents=True, exist_ok=True)
            coffre, journal = CoffreIdentite(d / "identite.sqlite3"), JournalEvenements(d / "journal.sqlite3")
        return cls(contenu or charger(), coffre, journal)

    # ------------------------------------------------------------------ outils
    def profil(self, eleve: str) -> ProfilEleve:
        if eleve not in self.profils:
            ident = self.coffre.lire(eleve)
            if ident is None:
                raise ErreurService(404, "élève inconnu")
            self.profils[eleve] = reconstruire_profil(self.journal, self.contenu, eleve, ident.niveau_scolaire)
        return self.profils[eleve]

    def eleve_du_jeton(self, jeton: str | None) -> str:
        if not jeton:
            raise ErreurService(401, "jeton manquant")
        with self.verrou:
            eleve = self.coffre.eleve_du_jeton(jeton)
        if eleve is None:
            raise ErreurService(401, "jeton invalide")
        return eleve

    def _seance(self, sid: str, eleve: str) -> Session:
        e_s = self.seances.get(sid)
        if e_s is None or e_s[0] != eleve:
            raise ErreurService(404, "séance introuvable")
        return e_s[1]

    # ------------------------------------------------------------------ inscription / RGPD
    def inscrire(self, corps: dict) -> dict:
        prenom = str(corps.get("prenom") or "").strip()
        niveau = corps.get("niveau")
        annee = corps.get("annee_naissance")
        contact = (corps.get("contact_parent") or None)
        if not 1 <= len(prenom) <= 40:
            raise ErreurService(422, "prénom manquant ou trop long")
        if not isinstance(annee, int) or not 2005 <= annee <= 2022:
            raise ErreurService(422, "année de naissance invalide")
        if niveau not in NIVEAUX_ELEVE:
            raise ErreurService(422, f"niveau attendu parmi {', '.join(NIVEAUX_ELEVE)}")
        if contact is not None and len(str(contact)) > 120:
            raise ErreurService(422, "contact parent trop long")
        if not corps.get("accord_service"):
            raise ErreurService(422, "l'accord au fonctionnement du service est nécessaire")
        mineur_15 = date.today().year - annee - 1 < AGE_MAJORITE_NUMERIQUE
        if mineur_15 and not (corps.get("accord_parent") and contact):
            raise ErreurService(422, "moins de 15 ans : l'accord d'un parent et son contact sont nécessaires")
        with self.verrou:
            ident = self.coffre.creer(prenom, annee, niveau, contact)
            self.coffre.consentir(ident.eleve, "service", True, par_parent=bool(corps.get("accord_parent")))
            jeton = self.coffre.emettre_jeton(ident.eleve)
        return {"jeton": jeton, "prenom": ident.prenom, "niveau": ident.niveau_scolaire}

    def moi(self, eleve: str) -> dict:
        with self.verrou:
            ident = self.coffre.lire(eleve)
            if ident is None:
                raise ErreurService(404, "élève inconnu")
            consent = {f: self.coffre.a_consenti(eleve, f) for f in FINALITES}
        return {"prenom": ident.prenom, "niveau": ident.niveau_scolaire, "consentements": consent}

    def consentir(self, eleve: str, corps: dict) -> dict:
        with self.verrou:
            try:
                self.coffre.consentir(eleve, str(corps.get("finalite")), bool(corps.get("accorde")), bool(corps.get("par_parent")))
            except (ValueError, PermissionError) as e:
                raise ErreurService(422, str(e)) from e
        return {"ok": True}

    def exporter(self, eleve: str) -> dict:
        """Droit d'accès et de portabilité (art. 15 et 20)."""
        with self.verrou:
            ident = self.coffre.lire(eleve)
            evts = [{"quand": e.quand.isoformat(), "type": e.type, "donnees": e.donnees} for e in self.journal.lire(eleve)]
        return {"identite": ident.__dict__ if ident else None, "evenements": evts}

    def effacer(self, eleve: str) -> dict:
        """Droit à l'effacement (art. 17) : identité, jetons, consentements, journal, séances."""
        with self.verrou:
            n = self.journal.effacer_eleve(eleve)
            self.coffre.effacer(eleve)
            self.profils.pop(eleve, None)
            for sid in [s for s, (e, _) in self.seances.items() if e == eleve]:
                del self.seances[sid]
        return {"efface": True, "evenements_supprimes": n}

    # ------------------------------------------------------------------ contenu
    def chapitres(self, eleve: str) -> list[dict]:
        with self.verrou:
            profil = self.profil(eleve)
            return [_resume_chapitre(self.contenu, profil, ch.id) for ch in self.contenu.graphe.chapitres.values()]

    def progression(self, eleve: str, chapitre: str) -> dict:
        with self.verrou:
            if chapitre not in self.contenu.graphe.chapitres:
                raise ErreurService(404, "chapitre inconnu")
            return _progression(self.contenu, self.profil(eleve), chapitre)

    # ------------------------------------------------------------------ séances
    def nouvelle_seance(self, eleve: str, corps: dict) -> dict:
        chapitre = corps.get("chapitre")
        with self.verrou:
            if chapitre not in self.contenu.graphe.chapitres:
                raise ErreurService(404, "chapitre inconnu")
            for sid in [s for s, (e, _) in self.seances.items() if e == eleve]:
                del self.seances[sid]  # une séance active par élève
            sid = uuid.uuid4().hex
            graine = uuid.UUID(sid).int % 1_000_000
            self.seances[sid] = (eleve, Session(self.contenu, self.profil(eleve), chapitre, journal=self.journal, graine=graine))
        return {"seance": sid}

    def action(self, eleve: str, sid: str) -> dict:
        with self.verrou:
            s = self._seance(sid, eleve)
            return _action_json(self.contenu, s, s.prochaine_action())

    def repondre(self, eleve: str, sid: str, corps: dict) -> dict:
        saisie = str(corps.get("saisie") or "")
        fmt = corps.get("format", "texte")
        if len(saisie) > 400 or fmt not in ("texte", "latex"):
            raise ErreurService(422, "réponse invalide")
        with self.verrou:
            s = self._seance(sid, eleve)
            if s.item_courant is None:
                raise ErreurService(409, "aucune question en attente")
            if fmt == "latex":
                try:
                    saisie = latex_vers_texte(saisie)
                except ErreurLecture as e:
                    return {"statut": Statut.ILLISIBLE.value, "juste": False, "texte": f"Je n'arrive pas à lire ta réponse : {e}.",
                            "lu": None, "erreur": None}
            r = s.repondre(saisie)
            err = self.contenu.erreurs.get(r.verdict.erreur_type) if r.verdict.erreur_type else None
            return {"statut": r.verdict.statut.value, "juste": r.verdict.juste, "texte": r.texte, "lu": r.verdict.lu,
                    "erreur": {"id": err.id, "titre": err.titre} if err else None}

    def aide(self, eleve: str, sid: str) -> dict:
        with self.verrou:
            return {"texte": self._seance(sid, eleve).demander_aide()}

    def sante(self) -> dict:
        return {"ok": True, "contenu": self.contenu.version}

    # ------------------------------------------------------------------ routage (version navigateur)
    def requete(self, methode: str, chemin: str, corps: Any = None, jeton: str | None = None) -> tuple[int, Any]:
        """Même contrat que l'API HTTP : renvoie (statut HTTP, données JSON-sérialisables)."""
        chemin = chemin.split("?", 1)[0].rstrip("/")
        corps = corps or {}
        for meth, motif, auth, fn, statut_ok in _ROUTES:
            if meth != methode:
                continue
            m = re.fullmatch(motif, chemin)
            if not m:
                continue
            try:
                args = m.groups()
                if auth:
                    eleve = self.eleve_du_jeton(jeton)
                    return statut_ok, fn(self, eleve, *args, corps)
                return statut_ok, fn(self, *args, corps)
            except ErreurService as e:
                return e.statut, {"erreur": e.message}
        return 404, {"erreur": "route inconnue"}

    def requete_json(self, methode: str, chemin: str, corps_json: str = "", jeton: str | None = None) -> str:
        statut, donnees = self.requete(methode, chemin, json.loads(corps_json) if corps_json else None, jeton)
        return json.dumps({"statut": statut, "donnees": donnees}, ensure_ascii=False)


_R = Callable[..., Any]
_ROUTES: list[tuple[str, str, bool, _R, int]] = [
    ("POST", r"/api/eleves", False, lambda s, c: s.inscrire(c), 201),
    ("GET", r"/api/sante", False, lambda s, c: s.sante(), 200),
    ("GET", r"/api/moi", True, lambda s, e, c: s.moi(e), 200),
    ("POST", r"/api/moi/consentements", True, lambda s, e, c: s.consentir(e, c), 200),
    ("GET", r"/api/moi/export", True, lambda s, e, c: s.exporter(e), 200),
    ("DELETE", r"/api/moi", True, lambda s, e, c: s.effacer(e), 200),
    ("GET", r"/api/chapitres", True, lambda s, e, c: s.chapitres(e), 200),
    ("GET", r"/api/chapitres/([\w.-]+)/progression", True, lambda s, e, ch, c: s.progression(e, ch), 200),
    ("POST", r"/api/seances", True, lambda s, e, c: s.nouvelle_seance(e, c), 201),
    ("GET", r"/api/seances/(\w+)/action", True, lambda s, e, sid, c: s.action(e, sid), 200),
    ("POST", r"/api/seances/(\w+)/reponse", True, lambda s, e, sid, c: s.repondre(e, sid, c), 200),
    ("POST", r"/api/seances/(\w+)/aide", True, lambda s, e, sid, c: s.aide(e, sid), 200),
]


# ---------------------------------------------------------------------- sérialisation


def _statut_kc(contenu: Contenu, profil: ProfilEleve, kc: str) -> tuple[float, str]:
    e = profil.etats.get(kc)
    if e is None:
        p = prior_selon_niveau(contenu.graphe.kcs[kc].niveau, profil.niveau_scolaire)
        return p, Niveau.NON_EVALUEE.value
    return e.p, e.niveau().value


def _progression(contenu: Contenu, profil: ProfilEleve, chapitre: str) -> dict:
    g = contenu.graphe
    ch = g.chapitres[chapitre]
    kcs = []
    for k in g.sous_graphe(list(ch.cibles)):
        p, statut = _statut_kc(contenu, profil, k)
        kcs.append({"id": k, "titre": g.kcs[k].titre, "niveau": g.kcs[k].niveau, "p": round(p, 3), "statut": statut,
                    "cible": k in ch.cibles, "prerequis": g.prereqs(k)})
    return {"chapitre": ch.id, "titre": ch.titre, "kcs": kcs}


def _resume_chapitre(contenu: Contenu, profil: ProfilEleve, chapitre: str) -> dict:
    ch = contenu.graphe.chapitres[chapitre]
    acquis = sum(1 for k in ch.cibles if _statut_kc(contenu, profil, k)[1] in
                 (Niveau.MAITRISEE.value, Niveau.CONSOLIDEE.value, Niveau.TRANSFEREE.value))
    return {"id": ch.id, "titre": ch.titre, "niveau": ch.niveau, "cibles": len(ch.cibles), "acquises": acquis,
            "competences": len(contenu.graphe.sous_graphe(list(ch.cibles)))}


def _action_json(contenu: Contenu, s: Session, a: Action) -> dict:
    g = contenu.graphe
    d: dict = {"type": a.type.value, "mode": a.mode.value, "texte": a.texte, "raison": a.raison,
               "parcours": [{"id": k, "titre": g.kcs[k].titre, "niveau": g.kcs[k].niveau} for k in s.file]}
    if a.type is TypeAction.QUESTION and a.item is not None:
        kc = g.kcs[a.item.kcs[0]]
        d["question"] = {
            "enonce": a.item.enonce,
            "choix": list(a.item.choix),
            "type_reponse": a.item.spec.type,
            "variable": a.item.spec.variable,
            "competence": kc.titre,
            "niveau": kc.niveau,
            "difficulte": a.item.difficulte,
        }
    if a.type is TypeAction.FIN:
        d["escalades"] = [g.kcs[k].titre for k in s.escalades]
    return d
