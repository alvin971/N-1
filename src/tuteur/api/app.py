"""API HTTP du tuteur (FastAPI) + service de l'interface élève.

Deux bases distinctes, dans deux fichiers distincts :
  * `identite.sqlite3`  — coffre d'identité (prénom, contact parent, consentements, jetons) ;
  * `journal.sqlite3`   — journal pédagogique, indexé par pseudonyme uniquement.

Authentification : jeton opaque remis à l'inscription (empreinte seule stockée), envoyé en
`Authorization: Bearer …`. Aucune route ne prend l'identifiant de l'élève en paramètre :
un élève ne peut accéder qu'à ses propres données.

MVP mono-processus : l'état des séances est en mémoire, protégé par un verrou ; la progression
est reconstruite depuis le journal au premier accès (event sourcing). Passage à l'échelle :
voir docs/architecture.md §11.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..contenu import Contenu, charger
from ..knowledge import Niveau, ProfilEleve, prior_selon_niveau
from ..mathengine import ErreurLecture, Statut
from ..mathengine.latex import latex_vers_texte
from ..session import Action, Session, TypeAction, reconstruire_profil
from ..storage import CoffreIdentite, JournalEvenements
from ..storage.identite import AGE_MAJORITE_NUMERIQUE

STATIQUE = Path(__file__).parent / "static"
NIVEAUX_ELEVE = ("6e", "5e", "4e", "3e")

# Aucune ressource tierce : MathLive est servi localement (un CDN verrait l'adresse IP de chaque élève).
# 'unsafe-inline' pour les styles uniquement : MathLive injecte ses feuilles de style.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


# ---------------------------------------------------------------------- schémas


class Inscription(BaseModel):
    prenom: str = Field(min_length=1, max_length=40)
    annee_naissance: int = Field(ge=2005, le=2022)
    niveau: str
    contact_parent: str | None = Field(default=None, max_length=120)
    accord_service: bool
    accord_parent: bool = False


class NouvelleSeance(BaseModel):
    chapitre: str


class Reponse(BaseModel):
    saisie: str = Field(max_length=400)
    format: str = Field(default="texte", pattern="^(texte|latex)$")


class Consentement(BaseModel):
    finalite: str
    accorde: bool
    par_parent: bool = False


# ---------------------------------------------------------------------- état applicatif


@dataclass
class Etat:
    contenu: Contenu
    coffre: CoffreIdentite
    journal: JournalEvenements
    verrou: threading.RLock
    profils: dict[str, ProfilEleve]
    seances: dict[str, tuple[str, Session]]  # id séance -> (élève, séance)

    def profil(self, eleve: str) -> ProfilEleve:
        if eleve not in self.profils:
            ident = self.coffre.lire(eleve)
            if ident is None:
                raise HTTPException(404, "élève inconnu")
            self.profils[eleve] = reconstruire_profil(self.journal, self.contenu, eleve, ident.niveau_scolaire)
        return self.profils[eleve]


def creer_app(dossier_donnees: str | Path | None = None, contenu: Contenu | None = None) -> FastAPI:
    if dossier_donnees is None:
        coffre, journal = CoffreIdentite(), JournalEvenements()
    else:
        d = Path(dossier_donnees)
        d.mkdir(parents=True, exist_ok=True)
        coffre, journal = CoffreIdentite(d / "identite.sqlite3"), JournalEvenements(d / "journal.sqlite3")
    etat = Etat(contenu or charger(), coffre, journal, threading.RLock(), {}, {})
    app = FastAPI(title="Tuteur mathématique", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.etat = etat

    @app.middleware("http")
    async def entetes_securite(request: Request, call_next):
        r: Response = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "no-referrer"
        r.headers["Content-Security-Policy"] = CSP
        if request.url.path.startswith("/api/"):
            r.headers["Cache-Control"] = "no-store"
        return r

    def eleve_courant(authorization: str = Header(default="")) -> str:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "jeton manquant")
        with etat.verrou:
            eleve = etat.coffre.eleve_du_jeton(authorization[7:].strip())
        if eleve is None:
            raise HTTPException(401, "jeton invalide")
        return eleve

    # ------------------------------------------------------------------ inscription / RGPD
    @app.post("/api/eleves", status_code=201)
    def inscrire(ins: Inscription):
        if ins.niveau not in NIVEAUX_ELEVE:
            raise HTTPException(422, f"niveau attendu parmi {', '.join(NIVEAUX_ELEVE)}")
        if not ins.accord_service:
            raise HTTPException(422, "l'accord au fonctionnement du service est nécessaire")
        mineur_15 = date.today().year - ins.annee_naissance - 1 < AGE_MAJORITE_NUMERIQUE
        if mineur_15 and not (ins.accord_parent and ins.contact_parent):
            raise HTTPException(422, "moins de 15 ans : l'accord d'un parent et son contact sont nécessaires")
        with etat.verrou:
            ident = etat.coffre.creer(ins.prenom, ins.annee_naissance, ins.niveau, ins.contact_parent)
            etat.coffre.consentir(ident.eleve, "service", True, par_parent=ins.accord_parent)
            jeton = etat.coffre.emettre_jeton(ident.eleve)
        return {"jeton": jeton, "prenom": ident.prenom, "niveau": ident.niveau_scolaire}

    @app.get("/api/moi")
    def moi(eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            ident = etat.coffre.lire(eleve)
            assert ident is not None
            consent = {f: etat.coffre.a_consenti(eleve, f) for f in ("service", "entrainement_ocr", "recherche_pedagogique")}
        return {"prenom": ident.prenom, "niveau": ident.niveau_scolaire, "consentements": consent}

    @app.post("/api/moi/consentements")
    def consentir(c: Consentement, eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            try:
                etat.coffre.consentir(eleve, c.finalite, c.accorde, c.par_parent)
            except (ValueError, PermissionError) as e:
                raise HTTPException(422, str(e)) from e
        return {"ok": True}

    @app.get("/api/moi/export")
    def exporter(eleve: str = Depends(eleve_courant)):
        """Droit d'accès et de portabilité (art. 15 et 20)."""
        with etat.verrou:
            ident = etat.coffre.lire(eleve)
            evts = [{"quand": e.quand.isoformat(), "type": e.type, "donnees": e.donnees} for e in etat.journal.lire(eleve)]
        corps = json.dumps({"identite": ident.__dict__ if ident else None, "evenements": evts}, ensure_ascii=False, indent=2)
        return Response(corps, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="mes-donnees.json"'})

    @app.delete("/api/moi")
    def effacer(eleve: str = Depends(eleve_courant)):
        """Droit à l'effacement (art. 17) : identité, jetons, consentements, journal, séances."""
        with etat.verrou:
            n = etat.journal.effacer_eleve(eleve)
            etat.coffre.effacer(eleve)
            etat.profils.pop(eleve, None)
            for sid in [s for s, (e, _) in etat.seances.items() if e == eleve]:
                del etat.seances[sid]
        return {"efface": True, "evenements_supprimes": n}

    # ------------------------------------------------------------------ contenu
    @app.get("/api/chapitres")
    def chapitres(eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            profil = etat.profil(eleve)
            return [_resume_chapitre(etat.contenu, profil, ch.id) for ch in etat.contenu.graphe.chapitres.values()]

    @app.get("/api/chapitres/{chapitre}/progression")
    def progression(chapitre: str, eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            if chapitre not in etat.contenu.graphe.chapitres:
                raise HTTPException(404, "chapitre inconnu")
            return _progression(etat.contenu, etat.profil(eleve), chapitre)

    # ------------------------------------------------------------------ séances
    @app.post("/api/seances", status_code=201)
    def nouvelle_seance(ns: NouvelleSeance, eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            if ns.chapitre not in etat.contenu.graphe.chapitres:
                raise HTTPException(404, "chapitre inconnu")
            for sid in [s for s, (e, _) in etat.seances.items() if e == eleve]:
                del etat.seances[sid]  # une séance active par élève
            sid = uuid.uuid4().hex
            graine = uuid.UUID(sid).int % 1_000_000
            etat.seances[sid] = (eleve, Session(etat.contenu, etat.profil(eleve), ns.chapitre, journal=etat.journal, graine=graine))
        return {"seance": sid}

    def _seance(sid: str, eleve: str) -> Session:
        e_s = etat.seances.get(sid)
        if e_s is None or e_s[0] != eleve:
            raise HTTPException(404, "séance introuvable")
        return e_s[1]

    @app.get("/api/seances/{sid}/action")
    def action(sid: str, eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            s = _seance(sid, eleve)
            return _action_json(etat.contenu, s, s.prochaine_action())

    @app.post("/api/seances/{sid}/reponse")
    def repondre(sid: str, rep: Reponse, eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            s = _seance(sid, eleve)
            if s.item_courant is None:
                raise HTTPException(409, "aucune question en attente")
            saisie = rep.saisie
            if rep.format == "latex":
                try:
                    saisie = latex_vers_texte(rep.saisie)
                except ErreurLecture as e:
                    return {"statut": Statut.ILLISIBLE.value, "juste": False, "texte": f"Je n'arrive pas à lire ta réponse : {e}.",
                            "lu": None, "erreur": None}
            r = s.repondre(saisie)
            err = etat.contenu.erreurs.get(r.verdict.erreur_type) if r.verdict.erreur_type else None
            return {"statut": r.verdict.statut.value, "juste": r.verdict.juste, "texte": r.texte, "lu": r.verdict.lu,
                    "erreur": {"id": err.id, "titre": err.titre} if err else None}

    @app.post("/api/seances/{sid}/aide")
    def aide(sid: str, eleve: str = Depends(eleve_courant)):
        with etat.verrou:
            return {"texte": _seance(sid, eleve).demander_aide()}

    @app.get("/api/sante")
    def sante():
        return {"ok": True, "contenu": etat.contenu.version}

    @app.exception_handler(HTTPException)
    async def erreur_http(_: Request, exc: HTTPException):
        return JSONResponse({"erreur": exc.detail}, status_code=exc.status_code)

    if STATIQUE.exists():
        app.mount("/", StaticFiles(directory=STATIQUE, html=True), name="statique")
    return app


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
