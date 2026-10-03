"""Test de bout en bout de la version GitHub Pages (moteur Python exécuté dans le navigateur).

    python -m http.server 8080 --directory site &
    python scripts/e2e_site_statique.py http://127.0.0.1:8080/ captures/

Vérifie : chargement de Pyodide, inscription, séance complète au clavier mathématique (avec 25 %
d'erreurs typiques volontaires), absence de bonne réponse refusée, persistance de la progression
après rechargement de la page, absence d'erreur JavaScript. Code de sortie ≠ 0 en cas d'échec.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys

from playwright.sync_api import sync_playwright

ATTENDU = """
import json
from tuteur.exercises import texte_valeur
_s = [s for _, s in service.seances.values()][-1]
_i = _s.item_courant
json.dumps(None if _i is None else {
    "type": _i.spec.type,
    "juste": ("oui" if _i.spec.valeur else "non") if _i.spec.type == "booleen" else (_i.spec.texte_attendu or texte_valeur(_i.spec.valeur)),
    "erreurs": [texte_valeur(v) for v in _i.spec.erreurs.values()],
})
"""


def taper(page, texte: str) -> None:
    page.wait_for_timeout(250)
    page.click("#carte-action math-field")
    i = 0
    while i < len(texte):
        c = texte[i]
        if c == " ":
            i += 1
            continue
        page.keyboard.type("*" if c == "×" else c)
        if c in "^/":
            j = i + 1
            if j < len(texte) and texte[j] == "(":
                prof = 0
                while j < len(texte):
                    prof += texte[j] == "("
                    prof -= texte[j] == ")"
                    page.keyboard.type(texte[j])
                    j += 1
                    if prof == 0:
                        break
            else:
                while j < len(texte) and (texte[j].isdigit() or (texte[j] == "-" and j == i + 1)):
                    page.keyboard.type(texte[j])
                    j += 1
            page.keyboard.press("ArrowRight")
            i = j
            continue
        i += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("captures")
    ap.add_argument("--chromium", default=None)
    ap.add_argument("--questions-max", type=int, default=45)
    a = ap.parse_args()
    os.makedirs(a.captures, exist_ok=True)
    rng = random.Random(7)
    stats: collections.Counter = collections.Counter()
    problemes: list[str] = []
    erreurs_js: list[str] = []

    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=a.chromium) if a.chromium else p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 390, "height": 844}, locale="fr-FR")
        page = ctx.new_page()
        page.on("pageerror", lambda e: erreurs_js.append(str(e)))
        page.on("console", lambda m: m.type == "error" and erreurs_js.append(m.text))
        page.goto(a.url)
        page.wait_for_selector("#vue-chargement:not([hidden])", timeout=15000)
        page.screenshot(path=f"{a.captures}/0-chargement.png")
        page.wait_for_selector("#vue-inscription:not([hidden])", timeout=240000)
        print("Pyodide chargé, interface prête.")
        page.fill("input[name=prenom]", "Sam")
        page.fill("input[name=annee_naissance]", "2011")
        page.fill("input[name=contact_parent]", "parent@exemple.fr")
        page.check("input[name=accord_parent]")
        page.check("input[name=accord_service]")
        page.click("button[type=submit]")
        page.wait_for_selector(".chapitre", timeout=60000)
        page.screenshot(path=f"{a.captures}/1-chapitres.png")
        page.click(".chapitre button")

        n = 0
        while n < a.questions_max:
            page.wait_for_selector("#carte-action button.principal:not([disabled]), #carte-action .choix button", timeout=60000)
            page.wait_for_timeout(80)
            carte = page.inner_text("#carte-action")
            if "Retour aux chapitres" in carte:
                break
            libre = page.query_selector("#carte-action math-field:not([disabled])")
            choix = page.query_selector("#carte-action .choix button:not([disabled])")
            if not (libre or choix):
                page.click("#carte-action .actions button.principal")
                continue
            info = json.loads(page.evaluate(f"tuteurLocal.pyodide.runPython({json.dumps(ATTENDU)})"))
            erreur = bool(info["erreurs"]) and rng.random() < 0.25
            reponse = rng.choice(info["erreurs"]) if erreur else info["juste"]
            if choix:
                boutons = page.query_selector_all("#carte-action .choix button")
                cible = next((b for b in boutons if b.inner_text().strip().lower() == reponse.lower()), boutons[0])
                cible.click()
            else:
                taper(page, reponse)
                page.click("#carte-action .saisie button.principal")
            page.wait_for_selector("#carte-action .retour:not([hidden])", timeout=60000)
            classe = page.get_attribute("#carte-action .retour", "class") or ""
            mode = page.inner_text("#pastille-mode")
            stats[(mode, "erreur" if erreur else "juste", classe)] += 1
            if not erreur and any(k in classe for k in ("ko", "forme", "illisible")):
                problemes.append(f"bonne réponse refusée : {reponse!r} → {page.inner_text('#carte-action .retour')}")
            if "illisible" in classe:
                break
            n += 1
            if n == 3:
                page.screenshot(path=f"{a.captures}/2-question.png", full_page=True)
            page.click("#carte-action .actions button.principal")
        page.screenshot(path=f"{a.captures}/3-apres-{n}-questions.png", full_page=True)

        # persistance : après rechargement, l'élève retrouve son compte et sa progression
        page.wait_for_timeout(1200)
        page.reload()
        page.wait_for_selector("#vue-chapitres:not([hidden]), #vue-inscription:not([hidden])", timeout=240000)
        if page.is_visible("#vue-inscription"):
            problemes.append("progression perdue après rechargement de la page")
        else:
            page.screenshot(path=f"{a.captures}/4-apres-rechargement.png", full_page=True)
            print("Persistance après rechargement : OK")
        nav.close()

    for k, v in sorted(stats.items(), key=str):
        print(k, v)
    print(f"{n} questions jouées ; erreurs JavaScript : {erreurs_js[:5]}")
    problemes += [f"erreur JavaScript : {e}" for e in erreurs_js]
    for pb in problemes:
        print("PROBLÈME :", pb)
    if n < 10:
        problemes.append(f"trop peu de questions jouées ({n})")
    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(main())
