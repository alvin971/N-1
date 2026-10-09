"""« Regarder la copie » : une résolution rédigée ligne par ligne localise l'erreur et la nomme."""

import pytest

from tuteur.exercises import REGISTRE
from tuteur.knowledge import ProfilEleve
from tuteur.mathengine import Statut
from tuteur.service import Service
from tuteur.session import Mode, Session, TypeAction


def _item():
    it = REGISTRE["eq.parentheses.resoudre"].instancier(1, 1)  # 8(x - 6) = -88 → x = -5
    assert it.equation_depart == "8(x - 6) = -88"
    return it


@pytest.mark.parametrize("lignes, statut, erreur", [
    (["8x - 48 = -88", "8x = -40", "x = -5"], Statut.CORRECT, None),
    (["8x - 6 = -88", "8x = -82", "x = -41/4"], Statut.INCORRECT, "lit.distributivite_premier_terme_seulement"),
    (["8x - 48 = -88", "8x = -136", "x = -17"], Statut.INCORRECT, "eq.transposition_sans_changement_signe"),
    (["x = -5"], Statut.CORRECT, None),
    (["-5"], Statut.CORRECT, None),
])
def test_correction_ligne_par_ligne(lignes, statut, erreur):
    v, _ = _item().corriger_etapes(lignes)
    assert v.statut is statut and v.erreur_type == erreur


def test_produit_nul_et_synthese():
    assert not REGISTRE["eq.produit_nul.resoudre"].instancier(1, 1).etapes_possibles  # « x = … ou x = … »
    synthese = REGISTRE["eq.parentheses.resoudre"].instancier(1, 3)
    assert synthese.etapes_possibles and "(" in synthese.equation_depart


def test_la_copie_est_une_preuve_directe_dans_le_diagnostic(contenu):
    s = Session(contenu, ProfilEleve("p", "3e"), "equations_3e", graine=0)
    a = s.prochaine_action()
    while not (a.type is TypeAction.QUESTION and a.item.etapes_possibles and a.mode is Mode.DIAGNOSTIC):
        s.repondre(a.item.spec.affichage() if a.item.spec.type != "booleen" else "oui")
        a = s.prochaine_action()
    depart = a.item.equation_depart
    # première ligne fausse : distributivité incomplète sur l'énoncé (si parenthèses), sinon transposition
    if "(" in depart.split("=")[0]:
        k = depart.split("(")[0]
        dedans = depart.split("(")[1].split(")")[0].replace(" ", "")
        fautive = f"{k}x{dedans[1:]} = {depart.split('=')[1].strip()}"
    else:
        fautive = depart.replace("=", "= 0 +", 1)
    r = s.repondre("", [fautive, "x = 1000"])
    assert r.verdict.statut is Statut.INCORRECT
    assert r.etapes == ()  # pendant le test, pas de correction ligne par ligne affichée
    assert s.diagnostic.observations[-1].statut is Statut.INCORRECT


def test_service_accepte_les_lignes_en_latex(contenu):
    s = Service.creer(None, contenu)
    ins = {"prenom": "Léa", "annee_naissance": 2008, "niveau": "4e", "accord_service": True}
    j = s.requete("POST", "/api/eleves", ins)[1]["jeton"]
    sid = s.requete("POST", "/api/seances", {"chapitre": "equations_3e"}, j)[1]["seance"]
    a = s.requete("GET", f"/api/seances/{sid}/action", jeton=j)[1]
    assert a["question"]["etapes_possibles"] is True and a["question"]["depart"]
    statut, r = s.requete("POST", f"/api/seances/{sid}/reponse",
                          {"lignes": [r"x=\frac{1}{2}"], "format": "latex"}, j)
    assert statut == 200 and r["statut"] in {"correct", "incorrect", "forme_non_conforme"}
    assert s.requete("POST", f"/api/seances/{sid}/reponse", {"lignes": ["x"] * 25}, j)[0] in (409, 422)
