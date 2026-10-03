import pytest

from tuteur.mathengine import StatutLigne, verifier_resolution


def test_resolution_juste():
    r = verifier_resolution(["3x + 5 = 20", "3x = 15", "x = 5"])
    assert r.juste and r.premiere_erreur is None


def test_resolution_non_terminee():
    r = verifier_resolution(["3x + 5 = 20", "3x = 15"])
    assert not r.juste and r.premiere_erreur is None and not r.terminee


@pytest.mark.parametrize("lignes, ligne_fautive, erreur", [
    (["3x + 5 = 20", "3x = 20 + 5", "x = 25/3"], 1, "eq.transposition_sans_changement_signe"),
    (["4x = 12", "x = 8"], 1, "eq.soustrait_au_lieu_de_diviser"),
    (["4x = 3", "x = 4/3"], 1, "eq.division_inversee"),
    (["-3x = 12", "x = 4"], 1, "eq.signe_du_coefficient"),
    (["2(x + 3) = 10", "2x + 3 = 10"], 1, "lit.distributivite_premier_terme_seulement"),
    (["5 - (x - 1) = 2", "5 - x - 1 = 2"], 1, "lit.signe_moins_devant_parenthese"),
    (["2x + 3 = x + 7", "3x + 3 = 7"], 1, "eq.transposition_sans_changement_signe"),
])
def test_erreur_localisee_et_diagnostiquee(lignes, ligne_fautive, erreur):
    r = verifier_resolution(lignes)
    assert r.premiere_erreur == ligne_fautive
    assert r.lignes[ligne_fautive].statut is StatutLigne.ERREUR
    assert r.lignes[ligne_fautive].erreur_type == erreur


def test_ligne_illisible():
    r = verifier_resolution(["2x = 4", "x = = 2"])
    assert r.lignes[1].statut is StatutLigne.ILLISIBLE
