import pytest

from tuteur.exercises import REGISTRE, texte_valeur
from tuteur.mathengine import Statut

CAS = [(m, d) for m in REGISTRE.values() for d in m.difficultes]


@pytest.mark.parametrize("modele, difficulte", CAS, ids=[f"{m.id}-d{d}" for m, d in CAS])
def test_modele_coherent(modele, difficulte):
    for graine in range(25):
        item = modele.instancier(graine, difficulte, qcm=(graine % 2 == 0))
        # 1. la bonne réponse affichée est acceptée (valeur ET forme)
        bonne = ("oui" if item.spec.valeur else "non") if item.spec.type == "booleen" else item.spec.affichage()
        assert item.corriger(bonne).statut is Statut.CORRECT, (item.enonce, bonne)
        # 2. pouvoir diagnostique : chaque erreur typique est reconnue comme telle
        for err, val in item.spec.erreurs.items():
            v = item.corriger(texte_valeur(val))
            assert v.statut is Statut.INCORRECT and v.erreur_type == err, (item.enonce, err, texte_valeur(val))
        # 3. QCM : exactement une option juste
        if item.est_qcm:
            assert sum(item.corriger(c).juste for c in item.choix) == 1, item.choix


def test_reproductible():
    m = REGISTRE["eq.ax_plus_b.resoudre"]
    assert m.instancier(42, 2) == m.instancier(42, 2)


def test_chaque_kc_a_un_modele_diagnostique(contenu):
    for kc in contenu.graphe.kcs:
        assert contenu.modeles_diagnostic(kc), kc
