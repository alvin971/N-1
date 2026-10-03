import sympy

from tuteur.mathengine import SpecReponse, Statut, corriger, valeur_de

x = sympy.Symbol("x")


def spec_dev():
    return SpecReponse("expression", valeur_de("x^2+4x+4"), ("developpee_reduite",),
                       {"lit.carre_somme_sans_double_produit": valeur_de("x^2+4")})


def test_equivalent_mais_forme_non_conforme():
    # cas cité dans la conception : (x+2)² ≡ x²+4x+4, mais faux si on demande de développer
    assert corriger(spec_dev(), "(x+2)²").statut is Statut.FORME
    assert corriger(spec_dev(), "x² + 2x + 2x + 4").statut is Statut.FORME
    assert corriger(spec_dev(), "4 + 4x + x²").statut is Statut.CORRECT


def test_erreur_typique_reconnue():
    v = corriger(spec_dev(), "x² + 4")
    assert v.statut is Statut.INCORRECT and v.erreur_type == "lit.carre_somme_sans_double_produit"


def test_factorisee():
    spec = SpecReponse("expression", valeur_de("x^2-9"), ("factorisee",))
    assert corriger(spec, "(x-3)(x+3)").statut is Statut.CORRECT
    assert corriger(spec, "(x+3)(x-3)").statut is Statut.CORRECT
    assert corriger(spec, "x²-9").statut is Statut.FORME
    assert corriger(spec, "(x-3)²").statut is Statut.INCORRECT


def test_fraction_irreductible_et_ecritures():
    spec = SpecReponse("expression", sympy.Rational(2, 3), ("fraction_irreductible",))
    assert corriger(spec, "2/3").juste
    assert corriger(spec, "4/6").statut is Statut.FORME
    assert corriger(spec, "0,666").statut is Statut.INCORRECT


def test_solutions_formats():
    spec = SpecReponse("solutions", frozenset({sympy.Integer(-3), sympy.Integer(2)}))
    for s in ["x = -3 ou x = 2", "S = {-3 ; 2}", "{2;-3}", "2 ; -3", "x=2 et x=-3"]:
        assert corriger(spec, s).juste, s
    v = corriger(spec, "x = 2")
    assert v.statut is Statut.INCORRECT and "manque" in v.message


def test_ensemble_vide():
    spec = SpecReponse("solutions", frozenset())
    for s in ["aucune solution", "S = ∅", "pas de solution", "{}"]:
        assert corriger(spec, s).juste, s


def test_booleen():
    spec = SpecReponse("booleen", True)
    assert corriger(spec, "Oui").juste
    assert corriger(spec, "non").statut is Statut.INCORRECT
    assert corriger(spec, "peut-être").statut is Statut.ILLISIBLE


def test_division_par_zero():
    spec = SpecReponse("expression", sympy.Integer(1))
    assert corriger(spec, "1/0").statut is Statut.INCORRECT
