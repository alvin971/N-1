import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from tuteur.api import creer_app  # noqa: E402

INSCRIPTION = {"prenom": "Léa", "annee_naissance": 2012, "niveau": "3e", "contact_parent": "p@e.fr",
               "accord_service": True, "accord_parent": True}


@pytest.fixture()
def client(contenu, tmp_path):
    return TestClient(creer_app(tmp_path, contenu))


def _inscrire(client, **kw):
    r = client.post("/api/eleves", json={**INSCRIPTION, **kw})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['jeton']}"}


def test_consentement_parental_exige_sous_15_ans(client):
    r = client.post("/api/eleves", json={**INSCRIPTION, "accord_parent": False})
    assert r.status_code == 422
    r = client.post("/api/eleves", json={**INSCRIPTION, "accord_service": False})
    assert r.status_code == 422


def test_authentification(client):
    assert client.get("/api/moi").status_code == 401
    assert client.get("/api/moi", headers={"Authorization": "Bearer faux"}).status_code == 401


def test_cloisonnement_entre_eleves(client):
    a, b = _inscrire(client), _inscrire(client, prenom="Sam")
    sid = client.post("/api/seances", json={"chapitre": "equations_3e"}, headers=a).json()["seance"]
    assert client.get(f"/api/seances/{sid}/action", headers=b).status_code == 404


def test_parcours_complet_et_reponse_latex(client):
    h = _inscrire(client)
    sid = client.post("/api/seances", json={"chapitre": "fractions_4e"}, headers=h).json()["seance"]
    a = client.get(f"/api/seances/{sid}/action", headers=h).json()
    assert a["type"] == "question" and "question" in a
    # la bonne réponse n'est jamais envoyée au navigateur : liste fermée des champs exposés
    assert set(a["question"]) == {"enonce", "choix", "type_reponse", "variable", "competence", "niveau", "difficulte",
                                  "etapes_possibles", "depart"}
    r = client.post(f"/api/seances/{sid}/reponse", json={"saisie": r"\frac{1}{2}", "format": "latex"}, headers=h).json()
    assert r["statut"] in {"correct", "incorrect", "forme_non_conforme"}
    assert client.post(f"/api/seances/{sid}/aide", headers=h).status_code == 200


def test_progression_persistante_apres_redemarrage(contenu, tmp_path):
    c1 = TestClient(creer_app(tmp_path, contenu))
    h = _inscrire(c1)
    sid = c1.post("/api/seances", json={"chapitre": "fractions_4e"}, headers=h).json()["seance"]
    for _ in range(3):
        c1.get(f"/api/seances/{sid}/action", headers=h)
        c1.post(f"/api/seances/{sid}/reponse", json={"saisie": "999"}, headers=h)
    avant = c1.get("/api/chapitres/fractions_4e/progression", headers=h).json()
    c2 = TestClient(creer_app(tmp_path, contenu))  # nouveau processus : état reconstruit depuis le journal
    apres = c2.get("/api/chapitres/fractions_4e/progression", headers=h).json()
    assert avant == apres


def test_export_et_effacement(client):
    h = _inscrire(client)
    export = client.get("/api/moi/export", headers=h)
    assert export.status_code == 200 and "Léa" in export.text
    assert client.delete("/api/moi", headers=h).json()["efface"] is True
    assert client.get("/api/moi", headers=h).status_code == 401


def test_entetes_securite_et_interface(client):
    r = client.get("/")
    assert r.status_code == 200 and "Tuteur de maths" in r.text
    assert "cdn" not in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
