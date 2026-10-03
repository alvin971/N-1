import sympy
from hypothesis import given, settings
from hypothesis import strategies as st

from tuteur.mathengine import equivalentes, valeur_de

x = sympy.Symbol("x")
entiers = st.integers(min_value=-9, max_value=9)


@settings(max_examples=60, deadline=None)
@given(entiers, entiers)
def test_developpement_equivalent(a, b):
    assert equivalentes(valeur_de(f"(x + ({a}))(x + ({b}))"), sympy.expand((x + a) * (x + b)))


@settings(max_examples=60, deadline=None)
@given(entiers, entiers.filter(lambda v: v != 0))
def test_non_equivalent_si_constante_differente(a, d):
    assert not equivalentes(valeur_de(f"(x + ({a}))²"), sympy.expand((x + a) ** 2) + d)


def test_racines():
    assert equivalentes(valeur_de("√(8)"), 2 * sympy.sqrt(2))
    assert not equivalentes(valeur_de("√(8)"), 3)
