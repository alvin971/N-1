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
    ig, desc = res["descendante (présent d'abord)"], res["descente séquentielle naïve"]
    assert ig.exactitude_kc > desc.exactitude_kc
    assert ig.rappel_frontiere > desc.rappel_frontiere


def test_explication_lisible(contenu):
    cibles = ["eq.ax_plus_b_egal_c"]
    kcs = contenu.graphe.sous_graphe(cibles)
    non = {"rel.soustraction"} | contenu.graphe.descendants("rel.soustraction", set(kcs))
    r = _derouler(contenu, EleveSimule({k for k in kcs if k not in non}, rng=random.Random(1)), cibles)
    assert any("Soustraire des nombres relatifs" in l for l in r.explication(contenu))


# ---------------------------------------------------------------------- stratégie descendante
# « Les maths fonctionnent par acquis » : on teste le présent avec un exercice large, une réussite
# valide toutes ses parties, on ne descend que dans les parties d'un exercice raté.


def _trace(contenu, eleve, cibles, graine=0):
    d = Diagnostic(contenu, cibles, "3e", graine=graine)
    items = []
    while (item := d.prochaine_question()) is not None:
        items.append(item)
        d.enregistrer(item, item.corriger(eleve.repondre(item, contenu)))
    return d, items


def test_eleve_fort_quelques_questions_au_niveau_du_present(contenu):
    from tuteur.graph import rang_niveau

    cibles = list(contenu.graphe.chapitres["equations_3e"].cibles)
    eleve = EleveSimule(set(contenu.graphe.sous_graphe(cibles)), p_slip=0.0, rng=random.Random(0))
    d, items = _trace(contenu, eleve, cibles)
    assert len(items) <= 5
    premier = items[0]
    assert premier.kcs[0] in cibles and premier.difficulte == 3 and len(premier.kcs) >= 10  # épreuve large
    # jamais de question de primaire ou de 6e à un élève qui réussit le présent
    assert all(rang_niveau(contenu.graphe.kcs[i.kcs[0]].niveau) >= rang_niveau("4e") for i in items)
    assert d.resultat().frontiere == []


def test_on_ne_descend_que_dans_les_parties_d_un_exercice_rate(contenu):
    g = contenu.graphe
    cibles = list(g.chapitres["equations_3e"].cibles)
    kcs = set(g.sous_graphe(cibles))
    non = {"frac.multiplication"} | g.descendants("frac.multiplication", kcs)
    eleve = EleveSimule(kcs - non, p_slip=0.0, rng=random.Random(1))
    d, items = _trace(contenu, eleve, cibles, graine=1)
    assert "frac.multiplication" in d.resultat().frontiere
    rates = set()
    for it in items:
        if it.kcs[0] not in cibles:
            # toute question sous le niveau du chapitre porte sur une partie d'un exercice déjà raté
            # (ou sur un prérequis d'une telle partie)
            assert it.kcs[0] in rates or any(it.kcs[0] in g.prereqs(r) for r in rates), it.kcs[0]
        if not it.corriger(eleve.repondre(it, contenu)).juste:
            rates |= set(it.kcs)


def test_strategie_exhaustive_toujours_disponible(contenu):
    from tuteur.diagnostic import ParamsDiagnostic

    cibles = ["eq.ax_plus_b_egal_c"]
    d = Diagnostic(contenu, cibles, "3e", params=ParamsDiagnostic(strategie="exhaustive"))
    assert d.eligibles() == set(d.kcs)


# ---------------------------------------------------------------------- démarche hypothèse → vérification


class _UneSeuleErreur(EleveSimule):
    """Sait tout, mais se trompe UNE fois (inattention) sur la première question ciblée."""

    def repondre(self, item, contenu):
        if not getattr(self, "_deja", False) and item.kcs[0] not in self._cibles:
            self._deja = True
            return "999999"
        return super().repondre(item, contenu)


def test_une_erreur_isolee_n_est_pas_une_lacune(contenu):
    cibles = list(contenu.graphe.chapitres["equations_3e"].cibles)
    kcs = set(contenu.graphe.sous_graphe(cibles))
    # on force un échec sur l'exercice complet pour obliger le test à descendre
    eleve = _UneSeuleErreur(kcs - {"eq.avec_parentheses"}, p_slip=0.0, rng=random.Random(0))
    eleve._cibles = set(cibles)
    d, items = _trace(contenu, eleve, cibles)
    r = d.resultat()
    for kc in r.frontiere:
        echecs, reussites = r.preuves[kc]
        assert echecs >= 2 and echecs > reussites, (kc, r.preuves[kc])
    # la notion ratée une seule fois a été revérifiée par un autre exercice, et n'est pas une lacune
    premiere_ciblee = next(i for i in items if i.kcs[0] not in cibles)
    assert premiere_ciblee.kcs[0] not in r.frontiere
    assert sum(1 for i in items if i.kcs[0] == premiere_ciblee.kcs[0]) >= 2


def test_une_lacune_exige_deux_preuves_directes(contenu):
    g = contenu.graphe
    cibles = list(g.chapitres["equations_3e"].cibles)
    kcs = set(g.sous_graphe(cibles))
    non = {"rel.soustraction"} | g.descendants("rel.soustraction", kcs)
    d, _ = _trace(contenu, EleveSimule(kcs - non, p_slip=0.0, rng=random.Random(3)), cibles, graine=3)
    r = d.resultat()
    assert "rel.soustraction" in r.frontiere and r.preuves["rel.soustraction"][0] >= 2
    # les échecs au-dessus sont expliqués par la lacune : ce ne sont pas des hypothèses séparées
    assert not any("rel.soustraction" in g.ancetres(h, inclure=False) for h in r.hypotheses)
