"""Conversion du LaTeX produit par un clavier mathématique (MathLive) vers la notation scolaire
lue par `parser.py`.

On ne délègue PAS cette conversion au navigateur : l'export « ascii-math » de MathLive rend
`\\times` par « xx », que notre analyseur lirait comme x × x. Couvre le sous-ensemble utile au
collège : fractions, puissances, racines, ×, ÷, parenthèses, virgule décimale, ensembles.
"""

from __future__ import annotations

import re

from .parser import ErreurLecture

_SIMPLES = [
    (r"\left", ""), (r"\right", ""), (r"\bigl", ""), (r"\bigr", ""),
    (r"\times", "×"), (r"\cdot", "×"), (r"\div", "÷"), (r"\le", "≤"), (r"\ge", "≥"),
    (r"\lbrace", "{"), (r"\rbrace", "}"), (r"\{", "{"), (r"\}", "}"),
    (r"\emptyset", "∅"), (r"\varnothing", "∅"), (r"\varnothing", "∅"),
    (r"\,", " "), (r"\;", " "), (r"\:", " "), (r"\!", ""), (r"\ ", " "), (r"\quad", " "),
    ("{,}", ","), ("−", "-"),
]
_MOTS = re.compile(r"\\(?:mathrm|text|operatorname|mathit|textrm)\{([^{}]*)\}")
_PLACEHOLDER = re.compile(r"\\placeholder(?:\[[^\]]*\])?\{[^{}]*\}")


def _groupe(s: str, i: int) -> tuple[str, int]:
    """Lit un argument LaTeX à partir de s[i] : {…} équilibré ou un seul caractère."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        raise ErreurLecture("expression incomplète")
    if s[i] != "{":
        if s[i] == "\\":
            m = re.match(r"\\[a-zA-Z]+", s[i:])
            if m:
                return m.group(), i + m.end()
        return s[i], i + 1
    prof, j = 0, i
    while j < len(s):
        if s[j] == "{":
            prof += 1
        elif s[j] == "}":
            prof -= 1
            if prof == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ErreurLecture("accolade non fermée")


def _convertir(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        if s.startswith(r"\frac", i) or s.startswith(r"\dfrac", i) or s.startswith(r"\tfrac", i):
            i += 5 if s.startswith(r"\frac", i) else 6
            num, i = _groupe(s, i)
            den, i = _groupe(s, i)
            out.append(f"(({_convertir(num)})/({_convertir(den)}))")
            continue
        if s.startswith(r"\sqrt", i):
            i += 5
            if i < len(s) and s[i] == "[":
                raise ErreurLecture("racine n-ième non prise en charge")
            arg, i = _groupe(s, i)
            out.append(f"√({_convertir(arg)})")
            continue
        if s[i] == "^":
            arg, i = _groupe(s, i + 1)
            c = _convertir(arg)
            out.append(f"^({c})" if len(c) > 1 else f"^{c}")
            continue
        if s[i] in "{}":
            out.append("(" if s[i] == "{" else ")")
            i += 1
            continue
        if s[i] == "\\":
            m = re.match(r"\\[a-zA-Z]+", s[i:])
            raise ErreurLecture(f"commande non prise en charge : {m.group() if m else s[i:i + 2]}")
        out.append(s[i])
        i += 1
    return "".join(out)


def latex_vers_texte(latex: str) -> str:
    s = latex.strip()
    if len(s) > 400:
        raise ErreurLecture("saisie trop longue")
    s = _PLACEHOLDER.sub("", s)
    s = _MOTS.sub(lambda m: f" {m.group(1)} ", s)
    for a, b in _SIMPLES:
        s = s.replace(a, b)
    # accolades d'ensemble « {2;3} » : on les garde comme accolades littérales, elles sont
    # gérées par la lecture des ensembles de solutions ; les autres deviennent des parenthèses.
    ensemble = re.fullmatch(r"\s*(S\s*=\s*)?\{([^{}]*)\}\s*", s)
    if ensemble:
        return (ensemble.group(1) or "") + "{" + _convertir(ensemble.group(2)) + "}"
    return re.sub(r"\s+", " ", _convertir(s)).strip()
