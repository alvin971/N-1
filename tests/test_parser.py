import pytest
import sympy

from tuteur.mathengine import ErreurLecture, lire, lire_equation, valeur_de
from tuteur.mathengine.ast import Equation

x = sympy.Symbol("x")


@pytest.mark.parametrize("saisie, attendu", [
    ("3,5", sympy.Rational(7, 2)),
    ("3.5", sympy.Rational(7, 2)),
    ("1 000 + 2", 1002),
    ("12 : 4", 3),
    ("7 ÷ 2", sympy.Rational(7, 2)),
    ("2 × 3", 6),
    ("2·3", 6),
    ("−4 + 1", -3),
    ("2*-3", -6),
    ("(-3)²", 9),
    ("-3²", -9),
    ("2³", 8),
    ("√(9)", 3),
    ("racine(16)", 4),
    ("[2+3]×2", 10),
])
def test_nombres(saisie, attendu):
    assert valeur_de(saisie) == attendu


@pytest.mark.parametrize("saisie, attendu", [
    ("2x", 2 * x),
    ("2x²", 2 * x**2),
    ("3(x+1)", 3 * x + 3),
    ("(x+1)(x-2)", (x + 1) * (x - 2)),
    ("x(x+1)", x * (x + 1)),
    ("-x^2", -x**2),
    ("x/2 + 1", x / 2 + 1),
    ("2x - (x - 1)", x + 1),
])
def test_expressions(saisie, attendu):
    assert sympy.expand(valeur_de(saisie) - attendu) == 0


@pytest.mark.parametrize("saisie", ["", "3 4", "2 +", "(x+1", "x+1)", "2 $ 3", "x = 1 = 2", "a" * 300])
def test_illisible(saisie):
    with pytest.raises(ErreurLecture):
        lire(saisie)


def test_equation():
    eq = lire_equation("3x + 5 = 20")
    assert isinstance(eq, Equation)


def test_pas_d_execution_de_code():
    # parse_expr de SymPy exécuterait ceci ; notre analyseur refuse simplement de le lire
    with pytest.raises(ErreurLecture):
        lire("__import__('os').system('echo pwned')")
