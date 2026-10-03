"""Le point d'entrée unique `Service.requete` (utilisé par la version navigateur) a le même
contrat que l'API HTTP."""

import json

from tuteur.service import Service

INSCRIPTION = {"prenom": "Léa", "annee_naissance": 2012, "niveau": "3e", "contact_parent": "p@e.fr",
               "accord_service": True, "accord_parent": True}


def test_parcours_par_requete(contenu):
    s = Service.creer(None, contenu)
    statut, ins = s.requete("POST", "/api/eleves", INSCRIPTION)
    assert statut == 201
    j = ins["jeton"]
    assert s.requete("GET", "/api/moi")[0] == 401
    assert s.requete("GET", "/api/moi", jeton="faux")[0] == 401
    assert s.requete("GET", "/api/moi", jeton=j)[1]["prenom"] == "Léa"
    statut, chs = s.requete("GET", "/api/chapitres", jeton=j)
    assert statut == 200 and {c["id"] for c in chs} >= {"equations_3e"}
    sid = s.requete("POST", "/api/seances", {"chapitre": "fractions_4e"}, j)[1]["seance"]
    a = s.requete("GET", f"/api/seances/{sid}/action", jeton=j)[1]
    assert a["type"] == "question"
    r = s.requete("POST", f"/api/seances/{sid}/reponse", {"saisie": r"\frac{1}{2}", "format": "latex"}, j)[1]
    assert r["statut"] in {"correct", "incorrect", "forme_non_conforme"}
    assert s.requete("GET", "/api/chapitres/fractions_4e/progression", jeton=j)[0] == 200
    assert s.requete("GET", "/api/chapitres/inconnu/progression", jeton=j)[0] == 404
    assert s.requete("GET", "/api/rien", jeton=j)[0] == 404
    assert s.requete("DELETE", "/api/moi", jeton=j)[1]["efface"] is True


def test_validation_inscription(contenu):
    s = Service.creer(None, contenu)
    assert s.requete("POST", "/api/eleves", {**INSCRIPTION, "accord_parent": False})[0] == 422
    assert s.requete("POST", "/api/eleves", {**INSCRIPTION, "niveau": "CP"})[0] == 422
    assert s.requete("POST", "/api/eleves", {**INSCRIPTION, "annee_naissance": "2012"})[0] == 422


def test_requete_json(contenu):
    s = Service.creer(None, contenu)
    r = json.loads(s.requete_json("POST", "/api/eleves", json.dumps(INSCRIPTION)))
    assert r["statut"] == 201 and r["donnees"]["jeton"]
