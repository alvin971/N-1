"""API HTTP du tuteur (FastAPI) + service de l'interface élève.

Couche HTTP fine au-dessus de `tuteur.service.Service`, qui porte toute la logique (et qui
tourne aussi tel quel dans le navigateur pour la version GitHub Pages).

Deux bases distinctes, dans deux fichiers distincts :
  * `identite.sqlite3`  — coffre d'identité (prénom, contact parent, consentements, jetons) ;
  * `journal.sqlite3`   — journal pédagogique, indexé par pseudonyme uniquement.

Authentification : jeton opaque remis à l'inscription (empreinte seule stockée), envoyé en
`Authorization: Bearer …`. Aucune route ne prend l'identifiant de l'élève en paramètre :
un élève ne peut accéder qu'à ses propres données.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..contenu import Contenu
from ..service import ErreurService, Service

STATIQUE = Path(__file__).parent / "static"

# Aucune ressource tierce : MathLive est servi localement (un CDN verrait l'adresse IP de chaque élève).
# 'unsafe-inline' pour les styles uniquement : MathLive injecte ses feuilles de style.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


# ---------------------------------------------------------------------- schémas (documentation OpenAPI)


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


def creer_app(dossier_donnees: str | Path | None = None, contenu: Contenu | None = None) -> FastAPI:
    svc = Service.creer(dossier_donnees, contenu)
    app = FastAPI(title="Tuteur mathématique", version="0.3.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.etat = svc

    @app.middleware("http")
    async def entetes_securite(request: Request, call_next):
        r: Response = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "no-referrer"
        r.headers["Content-Security-Policy"] = CSP
        if request.url.path.startswith("/api/"):
            r.headers["Cache-Control"] = "no-store"
        return r

    @app.exception_handler(ErreurService)
    async def erreur_service(_: Request, exc: ErreurService):
        return JSONResponse({"erreur": exc.message}, status_code=exc.statut)

    def eleve_courant(authorization: str = Header(default="")) -> str:
        return svc.eleve_du_jeton(authorization[7:].strip() if authorization.startswith("Bearer ") else None)

    @app.post("/api/eleves", status_code=201)
    def inscrire(ins: Inscription):
        return svc.inscrire(ins.model_dump())

    @app.get("/api/moi")
    def moi(eleve: str = Depends(eleve_courant)):
        return svc.moi(eleve)

    @app.post("/api/moi/consentements")
    def consentir(c: Consentement, eleve: str = Depends(eleve_courant)):
        return svc.consentir(eleve, c.model_dump())

    @app.get("/api/moi/export")
    def exporter(eleve: str = Depends(eleve_courant)):
        corps = json.dumps(svc.exporter(eleve), ensure_ascii=False, indent=2)
        return Response(corps, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="mes-donnees.json"'})

    @app.delete("/api/moi")
    def effacer(eleve: str = Depends(eleve_courant)):
        return svc.effacer(eleve)

    @app.get("/api/chapitres")
    def chapitres(eleve: str = Depends(eleve_courant)):
        return svc.chapitres(eleve)

    @app.get("/api/chapitres/{chapitre}/progression")
    def progression(chapitre: str, eleve: str = Depends(eleve_courant)):
        return svc.progression(eleve, chapitre)

    @app.post("/api/seances", status_code=201)
    def nouvelle_seance(ns: NouvelleSeance, eleve: str = Depends(eleve_courant)):
        return svc.nouvelle_seance(eleve, ns.model_dump())

    @app.get("/api/seances/{sid}/action")
    def action(sid: str, eleve: str = Depends(eleve_courant)):
        return svc.action(eleve, sid)

    @app.post("/api/seances/{sid}/reponse")
    def repondre(sid: str, rep: Reponse, eleve: str = Depends(eleve_courant)):
        return svc.repondre(eleve, sid, rep.model_dump())

    @app.post("/api/seances/{sid}/aide")
    def aide(sid: str, eleve: str = Depends(eleve_courant)):
        return svc.aide(eleve, sid)

    @app.get("/api/sante")
    def sante():
        return svc.sante()

    if STATIQUE.exists():
        app.mount("/", StaticFiles(directory=STATIQUE, html=True), name="statique")
    return app
