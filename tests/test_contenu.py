import pytest

from tuteur.graph import Graphe, GraphError


def test_contenu_valide(contenu):
    assert contenu.valider() == []


def test_dag_et_ordre(contenu):
    g = contenu.graphe
    pos = {k: i for i, k in enumerate(g.ordre_topologique)}
    for kc in g.kcs.values():
        for p in kc.prereqs:
            assert pos[p.kc] < pos[kc.id]


def test_cycle_detecte(tmp_path):
    (tmp_path / "g.yaml").write_text("""
version: t
kcs:
  - {id: a, titre: A, niveau: 5e, domaine: d, maitrise: m, prereqs: [{kc: b, force: forte, pourquoi: x}]}
  - {id: b, titre: B, niveau: 5e, domaine: d, maitrise: m, prereqs: [{kc: a, force: forte, pourquoi: x}]}
""")
    with pytest.raises(GraphError, match="cycle"):
        Graphe.depuis_yaml(tmp_path / "g.yaml")


def test_prerequis_de_niveau_superieur_refuse(tmp_path):
    (tmp_path / "g.yaml").write_text("""
version: t
kcs:
  - {id: a, titre: A, niveau: 3e, domaine: d, maitrise: m}
  - {id: b, titre: B, niveau: 5e, domaine: d, maitrise: m, prereqs: [{kc: a, force: forte, pourquoi: x}]}
""")
    with pytest.raises(GraphError, match="niveau supérieur"):
        Graphe.depuis_yaml(tmp_path / "g.yaml")


def test_racine_des_equations_remonte_au_primaire(contenu):
    g = contenu.graphe
    anc = g.ancetres("eq.avec_parentheses")
    assert {"lit.simple_distributivite", "rel.multiplication", "calc.tables_multiplication"} <= anc
