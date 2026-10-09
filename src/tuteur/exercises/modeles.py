"""Catalogue des modèles d'exercices du MVP (un ou plusieurs par KC).

Chaque modèle :
  - construit la solution d'abord ;
  - déclare les réponses produites par les erreurs typiques qu'il sait détecter
    (identifiants définis dans content/erreurs_typiques.yaml) ;
  - fournit une solution rédigée (sert d'exemple corrigé, sans LLM).
"""

from __future__ import annotations

import random
from math import gcd

import sympy

from ..mathengine import SpecReponse
from ..mathengine.ast import symbole
from .base import Brouillon, modele

X = symbole("x")
R = sympy.Rational


# ---------------------------------------------------------------------- helpers d'écriture


def p(n: int) -> str:
    """Nombre entre parenthèses s'il est négatif : (-3)."""
    return f"({n})" if n < 0 else str(n)


def terme(n: int, premier: bool = False) -> str:
    """« + 3 » / « - 3 » (ou « 3 » / « -3 » en tête)."""
    if premier:
        return str(n)
    return f"+ {n}" if n >= 0 else f"- {-n}"


def coef_x(a: int, premier: bool = True) -> str:
    s = {1: "x", -1: "-x"}.get(a, f"{a}x")
    if premier:
        return s
    return f"+ {s}" if a > 0 else f"- {s[1:]}"


def fr(a, b=None) -> str:
    if b is None:
        v = sympy.Rational(a)
        a, b = v.p, v.q
    return str(a) if b == 1 else f"{a}/{b}"


def nz(rng: random.Random, lo: int, hi: int) -> int:
    while True:
        v = rng.randint(lo, hi)
        if v != 0:
            return v


def sol(*vals) -> frozenset:
    return frozenset(sympy.nsimplify(v) for v in vals)


# ====================================================================== calcul sur les entiers


def _somme_sans_retenue(a: int, b: int) -> int:
    r, k = 0, 1
    while a or b:
        r += ((a % 10 + b % 10) % 10) * k
        a, b, k = a // 10, b // 10, k * 10
    return r


@modele("calc.addition.posee", ["calc.addition_entiers"], erreurs=("calc.retenue_oubliee",))
def _(rng, d):
    n = {1: 2, 2: 3, 3: 4}[d]
    a, b = rng.randint(10 ** (n - 1), 10**n - 1), rng.randint(10 ** (n - 1), 10**n - 1)
    return Brouillon(
        f"Calcule {a} + {b}.",
        SpecReponse("expression", sympy.Integer(a + b), ("entier",), {"calc.retenue_oubliee": sympy.Integer(_somme_sans_retenue(a, b))}),
        (f"On additionne chiffre par chiffre en commençant par les unités, sans oublier les retenues : {a} + {b} = {a + b}.",),
    )


def _soustraction_petit_du_grand(a: int, b: int) -> int:
    r, k = 0, 1
    while a or b:
        r += abs(a % 10 - b % 10) * k
        a, b, k = a // 10, b // 10, k * 10
    return r


@modele("calc.soustraction.posee", ["calc.soustraction_entiers"], erreurs=("calc.soustraction_petit_du_grand",))
def _(rng, d):
    n = {1: 2, 2: 3, 3: 4}[d]
    a = rng.randint(10 ** (n - 1) + 10, 10**n - 1)
    b = rng.randint(10 ** (n - 1), a - 1)
    return Brouillon(
        f"Calcule {a} - {b}.",
        SpecReponse("expression", sympy.Integer(a - b), ("entier",), {"calc.soustraction_petit_du_grand": sympy.Integer(_soustraction_petit_du_grand(a, b))}),
        (f"On soustrait colonne par colonne ; quand le chiffre du haut est plus petit, on fait une retenue : {a} - {b} = {a - b}.",),
    )


@modele("calc.tables.produit", ["calc.tables_multiplication"], erreurs=("calc.table_voisine",), difficultes=(1, 2), temps_estime_s=10)
def _(rng, d):
    a = rng.randint(2, 5) if d == 1 else rng.randint(6, 9)
    b = rng.randint(3, 9)
    return Brouillon(
        f"Calcule {a} × {b}.",
        SpecReponse("expression", sympy.Integer(a * b), ("entier",), {"calc.table_voisine": sympy.Integer(a * (b - 1))}),
        (f"{a} × {b} = {a * b} (table de {a}).",),
    )


@modele("calc.multiplication.posee", ["calc.multiplication_entiers"], erreurs=("calc.multiplication_decalage_oublie",), temps_estime_s=60)
def _(rng, d):
    a = rng.randint(12, 99) if d < 3 else rng.randint(102, 999)
    b = rng.randint(12, 49) if d == 1 else rng.randint(12, 99)
    return Brouillon(
        f"Calcule {a} × {b}.",
        SpecReponse("expression", sympy.Integer(a * b), ("entier",),
                    {"calc.multiplication_decalage_oublie": sympy.Integer(a * (b % 10) + a * (b // 10))}),
        (f"{a} × {b} = {a} × {b % 10} + {a} × {b // 10 * 10} = {a * (b % 10)} + {a * (b // 10) * 10} = {a * b}.",),
    )


@modele("calc.division.quotient", ["calc.division_euclidienne"], erreurs=("calc.division_reste_pour_quotient",))
def _(rng, d):
    b = rng.randint(3, 9) if d < 3 else rng.randint(11, 25)
    q = rng.randint(3, 12 if d == 1 else 40)
    r = rng.randint(1, b - 1)
    a = b * q + r
    return Brouillon(
        f"Quel est le quotient de la division euclidienne de {a} par {b} ?",
        SpecReponse("expression", sympy.Integer(q), ("entier",), {"calc.division_reste_pour_quotient": sympy.Integer(r)}),
        (f"{a} = {b} × {q} + {r} avec {r} < {b} : le quotient est {q} et le reste {r}.",),
    )


@modele("calc.diviseur.test", ["calc.multiples_diviseurs"], qcm_possible=False, temps_estime_s=25)
def _(rng, d):
    k = rng.randint(3, 9) if d == 1 else rng.randint(6, 15)
    vrai = rng.random() < 0.5
    n = k * rng.randint(4, 15) + (0 if vrai else rng.randint(1, k - 1))
    q, r = divmod(n, k)
    return Brouillon(
        f"{k} est-il un diviseur de {n} ? (réponds oui ou non)",
        SpecReponse("booleen", vrai),
        (f"{n} = {k} × {q} + {r} : le reste {'est nul, donc oui' if r == 0 else f'vaut {r}, donc non'}.",),
    )


@modele("calc.priorites.expression", ["calc.priorites_operatoires"], erreurs=("calc.priorites_gauche_a_droite",))
def _(rng, d):
    if d == 1:
        a, b, c = rng.randint(2, 15), rng.randint(2, 9), rng.randint(2, 9)
        return Brouillon(
            f"Calcule {a} + {b} × {c}.",
            SpecReponse("expression", sympy.Integer(a + b * c), ("entier",), {"calc.priorites_gauche_a_droite": sympy.Integer((a + b) * c)}),
            (f"La multiplication est prioritaire : {a} + {b} × {c} = {a} + {b * c} = {a + b * c}.",),
        )
    b, c = rng.randint(2, 9), rng.randint(2, 9)
    a = b * c + rng.randint(1, 30)
    e = rng.randint(2, 6)
    return Brouillon(
        f"Calcule {a} - {b} × {c} + {e}.",
        SpecReponse("expression", sympy.Integer(a - b * c + e), ("entier",),
                    {"calc.priorites_gauche_a_droite": sympy.Integer((a - b) * c + e)}),
        (f"D'abord le produit : {b} × {c} = {b * c}. Puis de gauche à droite : {a} - {b * c} + {e} = {a - b * c + e}.",),
    )


# ====================================================================== fractions


@modele("frac.quotient.ecriture", ["frac.quotient_entiers"], erreurs=("frac.quotient_inverse",), difficultes=(1, 2))
def _(rng, d):
    while True:
        a, b = rng.randint(2, 20 if d == 1 else 60), rng.randint(2, 9 if d == 1 else 15)
        if gcd(a, b) == 1:
            break
    return Brouillon(
        f"Écris le résultat de {a} ÷ {b} sous la forme d'une fraction.",
        SpecReponse("expression", R(a, b), ("fraction_irreductible",), {"frac.quotient_inverse": R(b, a)}),
        (f"Le quotient de {a} par {b} est le nombre qui multiplié par {b} donne {a} : c'est {a}/{b}.",),
    )


@modele("frac.quantite.calcul", ["frac.fraction_d_une_quantite"], erreurs=("frac.quantite_oubli_numerateur",))
def _(rng, d):
    b = rng.randint(2, 6 if d == 1 else 12)
    a = rng.randint(2, b + (0 if d < 3 else 6))
    if gcd(a, b) != 1:
        a = 1 + b if d == 3 else max(2, b - 1)
    n = b * rng.randint(2, 10 if d == 1 else 25)
    return Brouillon(
        f"Calcule {a}/{b} de {n}.",
        SpecReponse("expression", R(a * n, b), ("entier",), {"frac.quantite_oubli_numerateur": R(n, b)}),
        (f"{a}/{b} de {n} = ({n} ÷ {b}) × {a} = {n // b} × {a} = {a * n // b}.",),
    )


@modele("frac.egalite.denominateur_donne", ["frac.egalite_fractions"], erreurs=("frac.egalite_seul_denominateur", "frac.egalite_additive"))
def _(rng, d):
    b = rng.randint(2, 7 if d == 1 else 12)
    a = rng.randint(1, b - 1) if d < 3 else rng.randint(b + 1, 3 * b)
    k = rng.randint(2, 5 if d == 1 else 9)
    n = b * k
    return Brouillon(
        f"Écris la fraction {a}/{b} avec le dénominateur {n}.",
        SpecReponse("expression", R(a, b), (f"denominateur:{n}",),
                    {"frac.egalite_seul_denominateur": R(a, n), "frac.egalite_additive": R(a + n - b, n)},
                    texte_attendu=f"{a * k}/{n}"),
        (f"{n} = {b} × {k}, donc on multiplie numérateur ET dénominateur par {k} : {a}/{b} = {a * k}/{n}.",),
    )


@modele("frac.simplification.irreductible", ["frac.simplification"])
def _(rng, d):
    while True:
        p_, q_ = rng.randint(1, 9), rng.randint(2, 11)
        if gcd(p_, q_) == 1 and p_ != q_:
            break
    g = rng.choice([2, 3, 5]) if d == 1 else rng.choice([4, 6, 8, 9, 12, 15])
    return Brouillon(
        f"Simplifie au maximum la fraction {p_ * g}/{q_ * g}.",
        SpecReponse("expression", R(p_, q_), ("fraction_irreductible",)),
        (f"{p_ * g} = {g} × {p_} et {q_ * g} = {g} × {q_} : on divise par {g}, {p_ * g}/{q_ * g} = {fr(p_, q_)}.",),
    )


@modele("frac.addition.meme_den", ["frac.addition_meme_denominateur"], erreurs=("frac.addition_num_et_den",))
def _(rng, d):
    den = rng.randint(3, 9 if d == 1 else 15)
    a, c = rng.randint(1, den), rng.randint(1, den)
    op = "+" if d < 3 or rng.random() < 0.5 else "-"
    v = R(a + c, den) if op == "+" else R(a - c, den)
    erreurs = {"frac.addition_num_et_den": R(a + c, 2 * den)} if op == "+" else {}
    return Brouillon(
        f"Calcule {a}/{den} {op} {c}/{den}.",
        SpecReponse("expression", v, (), erreurs),
        (f"Même dénominateur : on {'additionne' if op == '+' else 'soustrait'} les numérateurs et on garde {den} : {a}/{den} {op} {c}/{den} = {a + c if op == '+' else a - c}/{den}.",),
    )


@modele("frac.addition.den_multiples", ["frac.addition_denominateurs_multiples"],
        erreurs=("frac.addition_num_et_den", "frac.addition_den_non_converti"), temps_estime_s=60)
def _(rng, d):
    b = rng.randint(2, 6)
    k = rng.randint(2, 4 if d == 1 else 6)
    a, c = rng.randint(1, b + 2), rng.randint(1, b * k)
    n = b * k
    v = R(a, b) + R(c, n)
    return Brouillon(
        f"Calcule {a}/{b} + {c}/{n}.",
        SpecReponse("expression", v, (), {"frac.addition_num_et_den": R(a + c, b + n), "frac.addition_den_non_converti": R(a + c, n)}),
        (f"{n} = {b} × {k} : {a}/{b} = {a * k}/{n}.", f"{a * k}/{n} + {c}/{n} = {a * k + c}/{n}."),
    )


@modele("frac.addition.quelconque", ["frac.addition_quelconque"],
        erreurs=("frac.addition_num_et_den", "frac.addition_den_non_converti"), temps_estime_s=75)
def _(rng, d):
    while True:
        b, dd = rng.randint(2, 7), rng.randint(2, 9)
        if b != dd and b % dd and dd % b:
            break
    a, c = rng.randint(1, 9), rng.randint(1, 9)
    op = "+" if d < 3 else rng.choice("+-")
    v = R(a, b) + R(c, dd) if op == "+" else R(a, b) - R(c, dd)
    num = (a + c) if op == "+" else (a - c)
    return Brouillon(
        f"Calcule {a}/{b} {op} {c}/{dd} et donne le résultat sous forme irréductible.",
        SpecReponse("expression", v, ("fraction_irreductible",),
                    {"frac.addition_num_et_den": R(num, b + dd), "frac.addition_den_non_converti": R(num, b * dd)}),
        (f"Dénominateur commun {b * dd} : {a}/{b} = {a * dd}/{b * dd} et {c}/{dd} = {c * b}/{b * dd}.",
         f"{a * dd}/{b * dd} {op} {c * b}/{b * dd} = {fr(v)} (forme irréductible)."),
    )


@modele("frac.multiplication.produit", ["frac.multiplication"], erreurs=("frac.confusion_multiplication_division",))
def _(rng, d):
    a, b, c, dd = rng.randint(1, 9), rng.randint(2, 9), rng.randint(1, 9), rng.randint(2, 9)
    if d >= 2:
        a = -a
    v = R(a, b) * R(c, dd)
    return Brouillon(
        f"Calcule {fr(a, b) if a > 0 else f'({a}/{b})'} × {c}/{dd} et donne le résultat sous forme irréductible.",
        SpecReponse("expression", v, ("fraction_irreductible",), {"frac.confusion_multiplication_division": R(a * dd, b * c)}),
        (f"On multiplie les numérateurs entre eux et les dénominateurs entre eux : {a * c}/{b * dd} = {fr(v)}.",),
    )


@modele("frac.division.quotient", ["frac.division"], erreurs=("frac.confusion_multiplication_division", "frac.division_inverse_premiere"), temps_estime_s=60)
def _(rng, d):
    a, b, c, dd = rng.randint(1, 9), rng.randint(2, 9), rng.randint(1, 9), rng.randint(2, 9)
    v = R(a, b) / R(c, dd)
    return Brouillon(
        f"Calcule {a}/{b} ÷ {c}/{dd} et donne le résultat sous forme irréductible.",
        SpecReponse("expression", v, ("fraction_irreductible",),
                    {"frac.confusion_multiplication_division": R(a * c, b * dd), "frac.division_inverse_premiere": R(b * c, a * dd)}),
        (f"Diviser par {c}/{dd}, c'est multiplier par son inverse {dd}/{c} : {a}/{b} × {dd}/{c} = {a * dd}/{b * c} = {fr(v)}.",),
    )


# ====================================================================== relatifs


@modele("rel.addition.calcul", ["rel.addition"], erreurs=("rel.addition_signes",), temps_estime_s=20)
def _(rng, d):
    m = 10 if d == 1 else 50
    a, b = rng.randint(1, m), rng.randint(1, m)
    if a == b:
        b += 1
    a, b = (-a, b) if rng.random() < 0.5 else (a, -b)
    err = (1 if a > 0 else -1) * (abs(a) + abs(b))
    return Brouillon(
        f"Calcule {p(a)} + {p(b)}.",
        SpecReponse("expression", sympy.Integer(a + b), ("entier",), {"rel.addition_signes": sympy.Integer(err)}),
        (f"Signes contraires : on soustrait les distances à zéro ({max(abs(a), abs(b))} - {min(abs(a), abs(b))}) et on prend le signe de celui qui a la plus grande distance à zéro : {a + b}.",),
    )


@modele("rel.soustraction.calcul", ["rel.soustraction"], erreurs=("rel.moins_moins",), temps_estime_s=20)
def _(rng, d):
    m = 10 if d == 1 else 40
    a, b = nz(rng, -m, m), rng.randint(1, m)
    return Brouillon(
        f"Calcule {p(a)} - ({-b}).",
        SpecReponse("expression", sympy.Integer(a + b), ("entier",), {"rel.moins_moins": sympy.Integer(a - b)}),
        (f"Soustraire {-b}, c'est ajouter son opposé {b} : {p(a)} - ({-b}) = {p(a)} + {b} = {a + b}.",),
    )


@modele("rel.multiplication.calcul", ["rel.multiplication"], erreurs=("rel.regle_signes",), temps_estime_s=15)
def _(rng, d):
    a, b = rng.randint(2, 9), rng.randint(2, 9 if d == 1 else 15)
    sa, sb = rng.choice([(-1, -1), (-1, 1), (1, -1)])
    a, b = sa * a, sb * b
    return Brouillon(
        f"Calcule {p(a)} × {p(b)}.",
        SpecReponse("expression", sympy.Integer(a * b), ("entier",), {"rel.regle_signes": sympy.Integer(-a * b)}),
        (f"{'Deux facteurs négatifs : le produit est positif' if a < 0 and b < 0 else 'Un seul facteur négatif : le produit est négatif'} ; {abs(a)} × {abs(b)} = {abs(a * b)}, donc {a * b}.",),
    )


@modele("rel.division.calcul", ["rel.division"], erreurs=("rel.regle_signes",), temps_estime_s=15)
def _(rng, d):
    b, q = rng.randint(2, 9), rng.randint(2, 9 if d == 1 else 15)
    sb, sq = rng.choice([(-1, -1), (-1, 1), (1, -1)])
    b, q = sb * b, sq * q
    a = b * q
    return Brouillon(
        f"Calcule {p(a)} ÷ {p(b)}.",
        SpecReponse("expression", sympy.Integer(q), ("entier",), {"rel.regle_signes": sympy.Integer(-q)}),
        (f"Même règle des signes que pour le produit ; {abs(a)} ÷ {abs(b)} = {abs(q)}, donc {q}.",),
    )


# ====================================================================== calcul littéral


@modele("lit.substitution.valeur", ["lit.substitution"], erreurs=("lit.substitution_concatenation", "lit.carre_double"))
def _(rng, d):
    k, v, c = rng.randint(2, 9), rng.randint(2, 9), rng.randint(1, 20)
    if d < 3:
        return Brouillon(
            f"Calcule {k}x + {c} pour x = {v}.",
            SpecReponse("expression", sympy.Integer(k * v + c), ("entier",), {"lit.substitution_concatenation": sympy.Integer(int(f"{k}{v}") + c)}),
            (f"{k}x signifie {k} × x : {k} × {v} + {c} = {k * v} + {c} = {k * v + c}.",),
        )
    return Brouillon(
        f"Calcule {k}x² + {c} pour x = {v}.",
        SpecReponse("expression", sympy.Integer(k * v * v + c), ("entier",),
                    {"lit.carre_double": sympy.Integer(k * 2 * v + c), "lit.substitution_concatenation": sympy.Integer(k * int(f"{v}2") + c)}),
        (f"x² = x × x = {v} × {v} = {v * v} ; puis {k} × {v * v} + {c} = {k * v * v + c}.",),
    )


@modele("lit.reduction.somme", ["lit.reduction"], erreurs=("lit.reduction_melange",))
def _(rng, d):
    m = 9 if d == 1 else 15
    a, b, c, e = rng.randint(1, m), rng.randint(1, m), rng.randint(1, m), rng.randint(1, m)
    if d >= 2:
        c, e = -c, rng.choice([e, -e])
    expr = f"{coef_x(a)} {terme(b)} {coef_x(c, premier=False)} {terme(e)}"
    v = (a + c) * X + (b + e)
    return Brouillon(
        f"Réduis l'expression {expr}.",
        SpecReponse("expression", v, ("developpee_reduite",), {"lit.reduction_melange": (a + b + c + e) * X}),
        (f"On regroupe les termes en x : {a} {terme(c)} = {a + c}, et les nombres : {b} {terme(e)} = {b + e}.",
         f"Résultat : {sympy.sstr(v).replace('*', '')}."),
    )


@modele("lit.distributivite.simple", ["lit.simple_distributivite"], erreurs=("lit.distributivite_premier_terme_seulement",))
def _(rng, d):
    k, b = rng.randint(2, 9), nz(rng, -9, 9) if d >= 2 else rng.randint(1, 9)
    if d == 3:
        k = -k
    v = sympy.expand(k * (X + b))
    return Brouillon(
        f"Développe et réduis {p(k) if k < 0 else k}(x {terme(b)}).",
        SpecReponse("expression", v, ("developpee_reduite",), {"lit.distributivite_premier_terme_seulement": k * X + b}),
        (f"On multiplie chaque terme de la parenthèse par {k} : {k} × x + {p(k)} × {p(b)} = {sympy.sstr(v).replace('*', '')}.",),
    )


@modele("lit.distributivite.double", ["lit.double_distributivite"],
        erreurs=("lit.double_distrib_premiers_derniers", "lit.carre_somme_sans_double_produit"), temps_estime_s=60)
def _(rng, d):
    if d == 2:
        a = nz(rng, -9, 9)
        v = sympy.expand((X + a) ** 2)
        return Brouillon(
            f"Développe et réduis (x {terme(a)})².",
            SpecReponse("expression", v, ("developpee_reduite",), {"lit.carre_somme_sans_double_produit": X**2 + a**2}),
            (f"(x {terme(a)})² = (x {terme(a)})(x {terme(a)}) = x² {terme(a)}x {terme(a)}x {terme(a * a)} = {sympy.sstr(v).replace('**', '^').replace('*', '')}.",),
        )
    a, b = nz(rng, -9, 9), nz(rng, -9, 9)
    m, n = (1, 1) if d == 1 else (rng.randint(2, 5), rng.randint(1, 4))
    v = sympy.expand((m * X + a) * (n * X + b))
    return Brouillon(
        f"Développe et réduis ({coef_x(m)} {terme(a)})({coef_x(n)} {terme(b)}).",
        SpecReponse("expression", v, ("developpee_reduite",), {"lit.double_distrib_premiers_derniers": m * n * X**2 + a * b}),
        (f"Chaque terme du premier facteur multiplie chaque terme du second : 4 produits, puis on réduit : {sympy.sstr(v).replace('**', '^').replace('*', '')}.",),
    )


@modele("lit.factorisation.facteur_commun", ["lit.factorisation_facteur_commun"], erreurs=("lit.facteur_commun_oubli_du_1",))
def _(rng, d):
    k = rng.randint(2, 9)
    if d == 1:
        return Brouillon(
            f"Factorise {k}x + {k}.",
            SpecReponse("expression", k * X + k, ("factorisee",), {"lit.facteur_commun_oubli_du_1": k * X}, texte_attendu=f"{k}(x + 1)"),
            (f"{k}x + {k} = {k} × x + {k} × 1 = {k}(x + 1).",),
        )
    if d == 2:
        b = rng.randint(2, 9)
        return Brouillon(
            f"Factorise {k}x + {k * b}.",
            SpecReponse("expression", k * X + k * b, ("factorisee",), texte_attendu=f"{k}(x + {b})"),
            (f"{k * b} = {k} × {b}, donc {k}x + {k * b} = {k}(x + {b}).",),
        )
    b = rng.randint(2, 9)
    return Brouillon(
        f"Factorise x² + {b}x.",
        SpecReponse("expression", X**2 + b * X, ("factorisee",), texte_attendu=f"x(x + {b})"),
        (f"x² + {b}x = x × x + {b} × x = x(x + {b}).",),
    )


@modele("lit.factorisation.difference_carres", ["lit.difference_carres"], erreurs=("lit.difference_carres_confondue_carre",), difficultes=(1, 2))
def _(rng, d):
    a = rng.randint(2, 9 if d == 1 else 12)
    return Brouillon(
        f"Factorise x² - {a * a}.",
        SpecReponse("expression", X**2 - a * a, ("factorisee",), {"lit.difference_carres_confondue_carre": (X - a) ** 2},
                    texte_attendu=f"(x - {a})(x + {a})"),
        (f"x² - {a * a} = x² - {a}² = (x - {a})(x + {a}).",),
    )


# ====================================================================== équations


@modele("eq.tester.valeur", ["eq.tester_solution"], qcm_possible=False, temps_estime_s=45)
def _(rng, d):
    a, c = rng.randint(2, 9), rng.randint(1, 9)
    if a == c:
        c += 1
    x0 = rng.randint(-5 if d >= 2 else 1, 8)
    b = rng.randint(-10, 10)
    e = a * x0 + b - c * x0
    v = x0 if rng.random() < 0.5 else x0 + rng.choice([-1, 1])
    vrai = v == x0
    g, dr = a * v + b, c * v + e
    return Brouillon(
        f"Le nombre {v} est-il solution de l'équation {coef_x(a)} {terme(b)} = {coef_x(c)} {terme(e)} ? (oui ou non)",
        SpecReponse("booleen", vrai),
        (f"Pour x = {v} : membre de gauche {a} × {p(v)} {terme(b)} = {g} ; membre de droite {c} × {p(v)} {terme(e)} = {dr}.",
         f"{'Les deux membres sont égaux : oui.' if vrai else 'Les deux membres sont différents : non.'}"),
    )


@modele("eq.x_plus_a.resoudre", ["eq.x_plus_a_egal_b"], erreurs=("eq.transposition_sans_changement_signe",), temps_estime_s=30)
def _(rng, d):
    m = 10 if d == 1 else 30
    a, b = nz(rng, -m, m) if d >= 2 else rng.randint(1, m), rng.randint(-m, m)
    return Brouillon(
        f"Résous l'équation x {terme(a)} = {b}.",
        SpecReponse("solutions", sol(b - a), (), {"eq.transposition_sans_changement_signe": sol(b + a)}),
        (f"x {terme(a)} = {b}", f"x = {b} {terme(-a)}", f"x = {b - a}"),
    )


@modele("eq.ax.resoudre", ["eq.ax_egal_b"], erreurs=("eq.soustrait_au_lieu_de_diviser", "eq.division_inversee", "eq.signe_du_coefficient"))
def _(rng, d):
    a = rng.randint(2, 9)
    if d >= 2:
        a = rng.choice([a, -a])
    if d < 3:
        x0 = nz(rng, -9, 9) if d >= 2 else rng.randint(2, 9)
        b = a * x0
    else:
        b = nz(rng, -30, 30)
        while b % a == 0:
            b += 1
    v = R(b, a)
    errs = {"eq.soustrait_au_lieu_de_diviser": sol(b - a), "eq.division_inversee": sol(R(a, b))}
    if d >= 2:
        errs["eq.signe_du_coefficient"] = sol(-v)
    return Brouillon(
        f"Résous l'équation {a}x = {b}" + (" (solution sous forme irréductible)." if d == 3 else "."),
        SpecReponse("solutions", sol(v), ("fraction_irreductible",), errs),
        (f"{a}x = {b}", f"x = {b}/{p(a)}", f"x = {fr(v)}"),
    )


@modele("eq.ax_plus_b.resoudre", ["eq.ax_plus_b_egal_c"], erreurs=("eq.transposition_sans_changement_signe", "eq.soustrait_au_lieu_de_diviser"), temps_estime_s=60)
def _(rng, d):
    a = rng.randint(2, 9) * (rng.choice([1, -1]) if d >= 2 else 1)
    b = nz(rng, -15, 15)
    if d < 3:
        x0 = rng.randint(-6 if d >= 2 else 1, 9)
        c = a * x0 + b
        v = R(x0)
    else:
        c = rng.randint(-30, 30)
        v = R(c - b, a)
    return Brouillon(
        f"Résous l'équation {coef_x(a)} {terme(b)} = {c}.",
        SpecReponse("solutions", sol(v), ("fraction_irreductible",),
                    {"eq.transposition_sans_changement_signe": sol(R(c + b, a)), "eq.soustrait_au_lieu_de_diviser": sol(c - b - a)}),
        (f"{coef_x(a)} {terme(b)} = {c}", f"{coef_x(a)} = {c} {terme(-b)}", f"{coef_x(a)} = {c - b}", f"x = {fr(v)}"),
    )


@modele("eq.deux_membres.resoudre", ["eq.inconnue_deux_membres", "lit.reduction"], erreurs=("eq.transposition_sans_changement_signe",), temps_estime_s=75)
def _(rng, d):
    while True:
        a, c = rng.randint(2, 9), rng.randint(1, 8)
        if d >= 2:
            c = rng.choice([c, -c])
        if a != c and a + c != 0:
            break
    b, e = nz(rng, -12, 12), nz(rng, -12, 12)
    if d == 1:
        x0 = rng.randint(1, 9)
        e = (a - c) * x0 + b
    v = R(e - b, a - c)
    return Brouillon(
        f"Résous l'équation {coef_x(a)} {terme(b)} = {coef_x(c)} {terme(e)}.",
        SpecReponse("solutions", sol(v), ("fraction_irreductible",), {"eq.transposition_sans_changement_signe": sol(R(e - b, a + c))}),
        (f"{coef_x(a)} {terme(b)} = {coef_x(c)} {terme(e)}", f"{coef_x(a)} {coef_x(-c, premier=False)} = {e} {terme(-b)}",
         f"{coef_x(a - c)} = {e - b}", f"x = {fr(v)}"),
    )


@modele("eq.parentheses.resoudre", ["eq.avec_parentheses", "lit.simple_distributivite"],
        erreurs=("lit.distributivite_premier_terme_seulement", "eq.transposition_sans_changement_signe"), temps_estime_s=90)
def _(rng, d):
    k, b = rng.randint(2, 9), nz(rng, -9, 9)
    if d == 1:
        x0 = rng.randint(-5, 9)
        c = k * (x0 + b)
        v = R(x0)
        return Brouillon(
            f"Résous l'équation {k}(x {terme(b)}) = {c}.",
            SpecReponse("solutions", sol(v), ("fraction_irreductible",), {"lit.distributivite_premier_terme_seulement": sol(R(c - b, k))}),
            (f"{k}(x {terme(b)}) = {c}", f"{k}x {terme(k * b)} = {c}", f"{k}x = {c - k * b}", f"x = {fr(v)}"),
        )
    if d == 3:
        # exercice de synthèse : parenthèses + coefficient fractionnaire + x dans les deux membres
        while True:
            pn, q = rng.randint(1, 7), rng.randint(2, 5)
            if gcd(pn, q) == 1 and R(pn, q) != k:
                break
        coef = R(pn, q)
        t = nz(rng, -4, 4)
        v = R(q * t)  # solution construite d'abord : multiple de q, pour un second membre entier
        c = int(k * (v + b) - coef * v)
        return Brouillon(
            f"Résous l'équation {k}(x {terme(b)}) = ({pn}/{q})x {terme(c)}.",
            SpecReponse("solutions", sol(v), ("fraction_irreductible",),
                        {"lit.distributivite_premier_terme_seulement": sol((c - b) / (k - coef)),
                         "eq.transposition_sans_changement_signe": sol((c - k * b) / (k + coef))}),
            (f"{k}(x {terme(b)}) = ({pn}/{q})x {terme(c)}", f"{k}x {terme(k * b)} = ({pn}/{q})x {terme(c)}",
             f"{k}x - ({pn}/{q})x = {c} {terme(-k * b)}", f"({fr(k - coef)})x = {c - k * b}", f"x = {fr(v)}"),
        )
    while True:
        m = rng.randint(1, 9) * rng.choice([1, -1])
        if m != k and k - m != 0:
            break
    n = nz(rng, -20, 20)
    v = R(n - k * b, k - m)
    return Brouillon(
        f"Résous l'équation {k}(x {terme(b)}) = {coef_x(m)} {terme(n)}.",
        SpecReponse("solutions", sol(v), ("fraction_irreductible",), {"lit.distributivite_premier_terme_seulement": sol(R(n - b, k - m))}),
        (f"{k}(x {terme(b)}) = {coef_x(m)} {terme(n)}", f"{k}x {terme(k * b)} = {coef_x(m)} {terme(n)}",
         f"{coef_x(k - m)} = {n - k * b}", f"x = {fr(v)}"),
    )


@modele("eq.coeff_fraction.resoudre", ["eq.coefficients_fractionnaires", "frac.division"],
        erreurs=("eq.coeff_fractionnaire_multiplie", "eq.transposition_sans_changement_signe"), temps_estime_s=90)
def _(rng, d):
    while True:
        pn, q = rng.randint(1, 7), rng.randint(2, 9)
        if gcd(pn, q) == 1 and pn != q:
            break
    b = nz(rng, -10, 10)
    t = rng.randint(-5, 6) or 1
    x0 = R(q * t, 1) if d < 3 else R(rng.randint(-20, 20), rng.randint(1, 5))
    c = R(pn, q) * x0 + b
    return Brouillon(
        f"Résous l'équation ({pn}/{q})x {terme(b)} = {fr(c)}.",
        SpecReponse("solutions", sol(x0), ("fraction_irreductible",),
                    {"eq.coeff_fractionnaire_multiplie": sol((c - b) * R(pn, q)), "eq.transposition_sans_changement_signe": sol((c + b) * R(q, pn))}),
        (f"({pn}/{q})x = {fr(c)} {terme(-b)} = {fr(c - b)}", f"x = {fr(c - b)} × {q}/{pn}", f"x = {fr(x0)}"),
    )


@modele("eq.produit_nul.resoudre", ["eq.produit_nul"], erreurs=("eq.produit_nul_signes",), temps_estime_s=60)
def _(rng, d):
    a, b = nz(rng, -9, 9), nz(rng, -9, 9)
    if a == b:
        b = -b if b != -b else b + 1
    if d == 3:
        # cas classique de 3e : il faut d'abord FACTORISER (x² + kx = 0 → x(x + k) = 0)
        m, k = rng.randint(1, 4), nz(rng, -12, 12)
        while gcd(m, abs(k)) != 1:
            k += 1 if k > 0 else -1
        ecrit = "x²" if m == 1 else f"{m}x²"
        return Brouillon(
            f"Résous l'équation {ecrit} {coef_x(k, premier=False)} = 0.",
            SpecReponse("solutions", sol(0, R(-k, m)), ("fraction_irreductible",), {"eq.produit_nul_signes": sol(0, R(k, m))}),
            (f"On factorise par x : x({coef_x(m)} {terme(k)}) = 0.", "Un produit est nul si l'un au moins de ses facteurs est nul.",
             f"x = 0 ou {coef_x(m)} {terme(k)} = 0", f"x = 0 ou x = {fr(R(-k, m))}"),
        )
    if d == 1:
        return Brouillon(
            f"Résous l'équation (x {terme(a)})(x {terme(b)}) = 0.",
            SpecReponse("solutions", sol(-a, -b), (), {"eq.produit_nul_signes": sol(a, b)}),
            ("Un produit est nul si l'un au moins de ses facteurs est nul.",
             f"x {terme(a)} = 0 ou x {terme(b)} = 0", f"x = {-a} ou x = {-b}"),
        )
    m = rng.randint(2, 5)
    while gcd(m, abs(a)) != 1:
        a += 1 if a > 0 else -1
    return Brouillon(
        f"Résous l'équation ({m}x {terme(a)})(x {terme(b)}) = 0.",
        SpecReponse("solutions", sol(R(-a, m), -b), ("fraction_irreductible",), {"eq.produit_nul_signes": sol(R(a, m), b)}),
        ("Un produit est nul si l'un au moins de ses facteurs est nul.",
         f"{m}x {terme(a)} = 0 ou x {terme(b)} = 0", f"x = {fr(R(-a, m))} ou x = {-b}"),
    )


# ====================================================================== compétences mobilisées
#
# « Les maths fonctionnent par acquis » : un exercice d'un niveau donné contient toutes ses parties
# techniques. Pour chaque modèle et chaque difficulté, on liste les compétences qu'une RÉUSSITE
# valide (en plus de la compétence principale). Le diagnostic part du présent avec les exercices
# les plus larges et ne descend que dans les parties d'un exercice raté.
# À faire relire par un enseignant : c'est de la connaissance didactique, pas du code.

_REL = ("rel.addition", "rel.soustraction")
_EQ_BASE = ("eq.x_plus_a_egal_b", "eq.ax_egal_b", "eq.ax_plus_b_egal_c")
_SOL_FRAC = ("frac.quotient_entiers", "frac.simplification", "calc.multiples_diviseurs", "rel.division")

MOBILISE: dict[str, dict[int, tuple[str, ...]]] = {
    # équations (3e)
    "eq.parentheses.resoudre": {
        1: ("lit.simple_distributivite", "rel.multiplication", *_EQ_BASE, *_REL),
        2: ("lit.simple_distributivite", "rel.multiplication", "eq.inconnue_deux_membres", "lit.reduction",
            *_EQ_BASE, *_REL, *_SOL_FRAC),
        3: ("lit.simple_distributivite", "rel.multiplication", "eq.inconnue_deux_membres", "lit.reduction",
            "eq.coefficients_fractionnaires", "frac.division", "frac.multiplication", "frac.addition_quelconque",
            *_EQ_BASE, *_REL, *_SOL_FRAC),
    },
    "eq.coeff_fraction.resoudre": {
        1: ("frac.division", "frac.multiplication", *_EQ_BASE, *_REL),
        2: ("frac.division", "frac.multiplication", *_EQ_BASE, *_REL),
        3: ("frac.division", "frac.multiplication", "frac.addition_quelconque", *_EQ_BASE, *_REL, *_SOL_FRAC),
    },
    "eq.produit_nul.resoudre": {
        1: ("eq.x_plus_a_egal_b", *_REL),
        2: (*_EQ_BASE, *_REL, *_SOL_FRAC),
        3: ("lit.factorisation_facteur_commun", "lit.simple_distributivite", *_EQ_BASE, *_REL, *_SOL_FRAC),
    },
    # équations (4e)
    "eq.deux_membres.resoudre": {
        1: ("lit.reduction", *_EQ_BASE),
        2: ("lit.reduction", *_EQ_BASE, *_REL, *_SOL_FRAC),
        3: ("lit.reduction", *_EQ_BASE, *_REL, *_SOL_FRAC),
    },
    "eq.ax_plus_b.resoudre": {
        1: ("eq.x_plus_a_egal_b", "eq.ax_egal_b"),
        2: ("eq.x_plus_a_egal_b", "eq.ax_egal_b", *_REL, "rel.division"),
        3: ("eq.x_plus_a_egal_b", "eq.ax_egal_b", *_REL, *_SOL_FRAC),
    },
    "eq.ax.resoudre": {2: ("rel.division",), 3: _SOL_FRAC},
    "eq.x_plus_a.resoudre": {2: _REL, 3: _REL},
    # calcul littéral
    "lit.distributivite.double": {
        1: ("lit.simple_distributivite", "lit.reduction", "rel.multiplication", "rel.addition"),
        2: ("lit.simple_distributivite", "lit.reduction", "rel.multiplication", "rel.addition"),
        3: ("lit.simple_distributivite", "lit.reduction", "rel.multiplication", "rel.addition", "calc.multiplication_entiers"),
    },
    "lit.factorisation.facteur_commun": {2: ("calc.multiples_diviseurs",)},
    "lit.factorisation.difference_carres": {1: ("calc.tables_multiplication",), 2: ("calc.tables_multiplication",)},
    "lit.distributivite.simple": {2: ("rel.multiplication",), 3: ("rel.multiplication",)},
    "lit.reduction.somme": {2: ("rel.addition",), 3: ("rel.addition",)},
    "lit.substitution.valeur": {1: ("calc.priorites_operatoires",), 2: ("calc.priorites_operatoires",),
                                3: ("calc.priorites_operatoires",)},
    # fractions
    "frac.division.quotient": {d: ("frac.multiplication", "frac.simplification", "calc.multiplication_entiers") for d in (1, 2, 3)},
    "frac.multiplication.produit": {1: ("frac.simplification", "calc.multiplication_entiers"),
                                    2: ("frac.simplification", "calc.multiplication_entiers", "rel.multiplication"),
                                    3: ("frac.simplification", "calc.multiplication_entiers", "rel.multiplication")},
    "frac.addition.quelconque": {1: ("frac.egalite_fractions", "frac.addition_meme_denominateur", "frac.simplification"),
                                 2: ("frac.egalite_fractions", "frac.addition_meme_denominateur", "frac.simplification"),
                                 3: ("frac.egalite_fractions", "frac.addition_meme_denominateur", "frac.simplification",
                                     "rel.addition")},
    "frac.addition.den_multiples": {d: ("frac.egalite_fractions", "frac.addition_meme_denominateur") for d in (1, 2, 3)},
    # relatifs
    "rel.division.calcul": {d: ("rel.multiplication",) for d in (1, 2)},
}


def _appliquer_mobilise() -> None:
    from dataclasses import replace

    from .base import REGISTRE

    for id_modele, par_difficulte in MOBILISE.items():
        REGISTRE[id_modele] = replace(REGISTRE[id_modele], mobilise=par_difficulte)


_appliquer_mobilise()
