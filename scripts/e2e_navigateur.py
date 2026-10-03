"""Test de bout en bout dans un vrai navigateur : un « élève » joue une séance complète en tapant
ses réponses au clavier mathématique MathLive (LaTeX → serveur → correction).

Il répond juste, sauf dans 25 % des cas où il produit une erreur typique. Toute réponse juste
refusée, illisible ou jugée « mal écrite » est signalée : c'est un bug de la chaîne de saisie.

    pip install playwright           # Chromium doit être disponible
    python scripts/e2e_navigateur.py captures/ [--chromium /chemin/vers/chrome]
"""
import os
import argparse, collections, random, threading, time
import uvicorn
from playwright.sync_api import sync_playwright
from tuteur.api import creer_app
from tuteur.exercises import texte_valeur

ap = argparse.ArgumentParser()
ap.add_argument("captures")
ap.add_argument("--chromium", default=None)
ARGS = ap.parse_args()
SP = ARGS.captures
os.makedirs(SP, exist_ok=True)
app = creer_app()
etat = app.state.etat
threading.Thread(target=lambda: uvicorn.run(app, host="127.0.0.1", port=8766, log_level="warning"), daemon=True).start()
time.sleep(2)
rng = random.Random(4)
stats = collections.Counter()
illisibles = []

def reponse_pour(item):
    spec = item.spec
    if spec.erreurs and rng.random() < 0.25:
        return texte_valeur(rng.choice(list(spec.erreurs.values()))), "erreur"
    if spec.type == "solutions":
        return texte_valeur(spec.valeur), "juste"
    return spec.texte_attendu or texte_valeur(spec.valeur), "juste"

def taper(page, texte):
    page.wait_for_timeout(250)
    page.click("#carte-action math-field")
    i = 0
    while i < len(texte):
        c = texte[i]
        if c == " ":
            i += 1; continue
        if c == "×":
            page.keyboard.type("*"); i += 1; continue
        page.keyboard.type(c)
        if c in "^/":
            j = i + 1
            if j < len(texte) and texte[j] == "(":  # groupe entre parenthèses
                prof = 0
                while j < len(texte):
                    prof += texte[j] == "("; prof -= texte[j] == ")"
                    page.keyboard.type(texte[j]); j += 1
                    if prof == 0: break
            else:
                while j < len(texte) and (texte[j].isdigit() or texte[j] == "-" and j == i + 1):
                    page.keyboard.type(texte[j]); j += 1
            page.keyboard.press("ArrowRight")
            i = j; continue
        i += 1

with sync_playwright() as p:
    nav = p.chromium.launch(executable_path=ARGS.chromium) if ARGS.chromium else p.chromium.launch()
    for (w, h, suf) in ((1280, 860, "bureau"), (390, 844, "mobile")):
        page = nav.new_context(viewport={"width": w, "height": h}, locale="fr-FR").new_page()
        erreurs = []
        page.on("console", lambda m: m.type == "error" and erreurs.append(m.text))
        page.goto("http://127.0.0.1:8766/")
        page.fill("input[name=prenom]", "Sam"); page.fill("input[name=annee_naissance]", "2011")
        page.fill("input[name=contact_parent]", "parent@exemple.fr"); page.check("input[name=accord_parent]"); page.check("input[name=accord_service]")
        page.click("button[type=submit]"); page.wait_for_selector(".chapitre")
        page.click(".chapitre button")
        vus = set()
        for etape in range(260):
            page.wait_for_timeout(80)
            carte = page.inner_text("#carte-action")
            mode = page.inner_text("#pastille-mode")
            if page.query_selector("#carte-action .choix button:not([disabled])"):
                item = [s for _, s in etat.seances.values()][-1].item_courant
                cible = ("oui" if item.spec.valeur else "non") if item.spec.type == "booleen" else None
                boutons = page.query_selector_all("#carte-action .choix button")
                b = next((x for x in boutons if x.inner_text().lower() == (cible or "")), boutons[0])
                b.click(); page.wait_for_selector("#carte-action .retour:not([hidden])")
                page.click("#carte-action .actions button.principal"); continue
            if page.query_selector("#carte-action math-field:not([disabled])"):
                item = [s for _, s in etat.seances.values()][-1].item_courant
                rep, genre = reponse_pour(item)
                taper(page, rep)
                cle = f"q-{mode}-{genre}"
                page.click("#carte-action .saisie button.principal")
                page.wait_for_selector("#carte-action .retour:not([hidden])")
                classe = page.get_attribute("#carte-action .retour", "class")
                stats[(mode, genre, classe)] += 1
                if "illisible" in classe or (genre == "juste" and "ko" in classe) or "forme" in classe:
                    illisibles.append((item.enonce, rep, page.inner_text("#carte-action .retour"), page.evaluate("document.querySelector('#carte-action math-field').value")))
                    if "illisible" in classe:
                        break
                if cle not in vus and mode != "Test de départ":
                    vus.add(cle); page.screenshot(path=f"{SP}/{suf}-{len(vus):02d}-{cle}.png".replace(" ", "_"), full_page=True)
                page.click("#carte-action .actions button.principal"); continue
            titre = carte.split("\n")[0][:30]
            if titre not in vus:
                vus.add(titre); page.screenshot(path=f"{SP}/{suf}-{len(vus):02d}-texte.png", full_page=True)
            if "Retour aux chapitres" in carte:
                print(suf, "FIN :", carte.replace("\n", " | ")); break
            page.click("#carte-action button.principal")
        print(suf, "étapes", etape, "erreurs console", erreurs[:3])
    nav.close()
for k, v in sorted(stats.items(), key=str): print(k, v)
print("PROBLÈMES", len(illisibles))
for x in illisibles[:15]: print(x)
raise SystemExit(1 if illisibles else 0)
