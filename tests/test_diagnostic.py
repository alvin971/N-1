import random

from tuteur.diagnostic import Diagnostic, parcours_remediation
from tuteur.simulation import EleveSimule
from tuteur.simulation.benchmark import evaluer


def _derouler(contenu, eleve, cibles, graine=0):
    d = Diagnostic(contenu, cibles, "3e", graine=graine)
    while (item := d.prochaine_question()) is not None:
        d.enregistrer(item, item.corriger(eleve.repondre(item, contenu)))
    return d.resultat()


def test_retrouve_une_lacune_de_5e(contenu):
    """Cas du cahier des charges : un élève de 3e bloqué en équations à cause des relatifs de 5e."""
    cibles = ["eq.ax_plus_b_egal_c"]
    kcs = contenu.graphe.sous_graphe(cibles)
    trouve = 0
    for g in range(5):
        lacune = "rel.soustraction"
        non = {lacune} | contenu.graphe.descendants(lacune, set(kcs))
        eleve = EleveSimule({k for k in kcs if k not in non}, rng=random.Random(g))
        r = _derouler(contenu, eleve, cibles, g)
        trouve += lacune in r.frontiere
        assert len(r.observations) <= 18
        assert r.parcours.index(lacune) < r.parcours.index("eq.ax_plus_b_egal_c")
    assert trouve >= 4


def test_eleve_qui_sait_tout(contenu):
    cibles = ["eq.ax_plus_b_egal_c"]
    eleve = EleveSimule(set(contenu.graphe.sous_graphe(cibles)), p_slip=0.0, rng=random.Random(0))
    r = _derouler(contenu, eleve, cibles)
    assert r.frontiere == []
    assert r.marginales["eq.ax_plus_b_egal_c"] > 0.85


def test_parcours_respecte_les_prerequis(contenu):
    g = contenu.graphe
    a_travailler = {"eq.ax_plus_b_egal_c", "eq.x_plus_a_egal_b", "rel.soustraction", "rel.addition"}
    p = parcours_remediation(contenu, a_travailler, {})
    for k in p:
        for pre in g.prereqs(k):
            if pre in a_travailler:
                assert p.index(pre) < p.index(k)


def test_meilleur_que_la_descente_sequentielle(contenu):
    res = evaluer(contenu, n_eleves=25, graine=3)
    ig, desc = res["gain d'information"], res["descente séquentielle"]
    assert ig.exactitude_kc > desc.exactitude_kc
    assert ig.rappel_frontiere > desc.rappel_frontiere


def test_explication_lisible(contenu):
    cibles = ["eq.ax_plus_b_egal_c"]
    kcs = contenu.graphe.sous_graphe(cibles)
    non = {"rel.soustraction"} | contenu.graphe.descendants("rel.soustraction", set(kcs))
    r = _derouler(contenu, EleveSimule({k for k in kcs if k not in non}, rng=random.Random(1)), cibles)
    assert any("Soustraire des nombres relatifs" in l for l in r.explication(contenu))
