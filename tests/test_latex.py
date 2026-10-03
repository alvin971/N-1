import pytest
import sympy

from tuteur.mathengine import ErreurLecture, SpecReponse, Statut, corriger, valeur_de
from tuteur.mathengine.latex import latex_vers_texte


@pytest.mark.parametrize("latex, attendu", [
    (r"\frac{7}{3}", sympy.Rational(7, 3)),
    (r"-\frac{1}{2}", sympy.Rational(-1, 2)),
    (r"\frac{-7}{3}", sympy.Rational(-7, 3)),
    (r"3\times4", 12),
    (r"12\div4", 3),
    (r"2{,}5", sympy.Rational(5, 2)),
    (r"\sqrt{16}", 4),
    (r"2^{10}", 1024),
    (r"\left(-3\right)^2", 9),
])
def test_valeurs(latex, attendu):
    assert valeur_de(latex_vers_texte(latex)) == attendu


def test_forme_conservee_a_travers_latex():
    spec = SpecReponse("expression", sympy.Rational(2, 3), ("fraction_irreductible",))
    assert corriger(spec, latex_vers_texte(r"\frac{2}{3}")).statut is Statut.CORRECT
    assert corriger(spec, latex_vers_texte(r"\frac{4}{6}")).statut is Statut.FORME
    x = sympy.Symbol("x")
    dev = SpecReponse("expression", sympy.expand((x + 2) ** 2), ("developpee_reduite",))
    assert corriger(dev, latex_vers_texte(r"x^2+4x+4")).juste
    assert corriger(dev, latex_vers_texte(r"\left(x+2\right)^2")).statut is Statut.FORME


def test_ensembles():
    spec = SpecReponse("solutions", frozenset({sympy.Integer(-3), sympy.Integer(2)}))
    for latex in (r"S=\lbrace-3;2\rbrace", r"x=-3;x=2", r"\left\lbrace2;-3\right\rbrace"):
        assert corriger(spec, latex_vers_texte(latex)).juste, latex


@pytest.mark.parametrize("latex", [r"\frac{1}", r"\int_0^1 x", r"\sqrt[3]{8}", "x" * 500])
def test_refus(latex):
    with pytest.raises(ErreurLecture):
        latex_vers_texte(latex)
