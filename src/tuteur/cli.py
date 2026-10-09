"""Interface en ligne de commande (démonstration et outillage).

    tuteur valider-contenu
    tuteur graphe --chapitre equations_3e
    tuteur exercice eq.ax_plus_b.resoudre --difficulte 2 --graine 7
    tuteur etapes "3x + 5 = 20" "3x = 20 + 5" "x = 25/3"
    tuteur session --chapitre equations_3e --niveau 3e          (interactif ; « ? » = indice)
    tuteur benchmark --eleves 100
    tuteur serveur --port 8000                                 (interface élève dans le navigateur)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone


def _contenu():
    from .contenu import charger

    return charger()


def cmd_valider(_: argparse.Namespace) -> int:
    c = _contenu()
    pbs = c.valider()
    for p in pbs:
        print(f"✗ {p}")
    if not pbs:
        print(f"✓ contenu {c.version} valide : {len(c.graphe.kcs)} KC, {len(c.modeles)} modèles, {len(c.erreurs)} erreurs typiques")
    return 1 if pbs else 0


def cmd_graphe(a: argparse.Namespace) -> int:
    c = _contenu()
    g = c.graphe
    for k in g.sous_graphe(list(g.chapitres[a.chapitre].cibles)):
        kc = g.kcs[k]
        pre = ", ".join(f"{p.kc}{'' if p.fort else ' (faible)'}" for p in kc.prereqs)
        print(f"[{kc.niveau:>3}] {k:<40} ← {pre or '—'}")
    return 0


def cmd_exercice(a: argparse.Namespace) -> int:
    c = _contenu()
    item = c.modeles[a.modele].instancier(a.graine, a.difficulte, qcm=a.qcm)
    print(item.enonce)
    if item.choix:
        print("Choix :", " | ".join(item.choix))
    print("Réponse attendue :", item.spec.affichage())
    for e, v in item.spec.erreurs.items():
        from .exercises import texte_valeur

        print(f"  si erreur « {c.erreurs[e].titre} » → {texte_valeur(v)}")
    print("Solution :", " / ".join(item.solution_redigee))
    return 0


def cmd_etapes(a: argparse.Namespace) -> int:
    from .mathengine import verifier_resolution

    c = _contenu()
    r = verifier_resolution(a.lignes)
    for l in r.lignes:
        err = f" — {c.erreurs[l.erreur_type].titre}" if l.erreur_type else ""
        print(f"{'✓' if l.statut.value == 'ok' else '✗'} {l.texte}  {l.message}{err}")
    print("Résolution juste et complète." if r.juste else "Résolution incorrecte ou incomplète.")
    return 0


def cmd_session(a: argparse.Namespace) -> int:
    from .knowledge import ProfilEleve
    from .session import Session, TypeAction
    from .storage import JournalEvenements

    c = _contenu()
    journal = JournalEvenements(a.journal) if a.journal else None
    s = Session(c, ProfilEleve("demo", a.niveau), a.chapitre, journal=journal, graine=a.graine)
    print(f"Chapitre : {c.graphe.chapitres[a.chapitre].titre}. Tape « ? » pour un indice, « q » pour quitter.\n")
    while True:
        act = s.prochaine_action()
        if act.type is TypeAction.FIN:
            print(act.texte)
            return 0
        if act.type is not TypeAction.QUESTION:
            print(f"\n[{act.type.value}] {act.texte}\n")
            if input("(Entrée pour continuer) ").strip().lower() == "q":
                return 0
            continue
        print(f"[{act.mode.value}] {act.texte}")
        if act.item and act.item.choix:
            print("   Choix : " + " | ".join(act.item.choix))
        while True:
            rep = input("> ").strip()
            if rep == "q":
                return 0
            if rep == "?":
                print(s.demander_aide())
                continue
            break
        r = s.repondre(rep)
        print(f"   {r.texte}\n")


def cmd_benchmark(a: argparse.Namespace) -> int:
    from .simulation.benchmark import evaluer

    contenu = _contenu()
    for profil in (["fort", "moyen", "fragile"] if a.profil == "tous" else [None if a.profil == "historique" else a.profil]):
        debut = datetime.now(timezone.utc)
        res = evaluer(contenu, a.chapitre, a.niveau, a.eleves, a.graine, profil=profil)
        duree = (datetime.now(timezone.utc) - debut).total_seconds()
        print(f"\n{a.eleves} élèves simulés « {profil or 'historique'} », chapitre {a.chapitre} ({duree:.0f} s)")
        for nom, m in res.items():
            print(m.ligne(nom))
    return 0


def cmd_serveur(a: argparse.Namespace) -> int:
    import uvicorn

    from .api import creer_app

    print(f"Interface élève : http://{a.hote}:{a.port}/  ·  API : http://{a.hote}:{a.port}/api/docs")
    uvicorn.run(creer_app(a.donnees), host=a.hote, port=a.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tuteur", description="Tuteur mathématique adaptatif (noyau déterministe)")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("valider-contenu").set_defaults(f=cmd_valider)
    g = sp.add_parser("graphe")
    g.add_argument("--chapitre", default="equations_3e")
    g.set_defaults(f=cmd_graphe)
    e = sp.add_parser("exercice")
    e.add_argument("modele")
    e.add_argument("--graine", type=int, default=0)
    e.add_argument("--difficulte", type=int, default=1)
    e.add_argument("--qcm", action="store_true")
    e.set_defaults(f=cmd_exercice)
    t = sp.add_parser("etapes")
    t.add_argument("lignes", nargs="+")
    t.set_defaults(f=cmd_etapes)
    s = sp.add_parser("session")
    s.add_argument("--chapitre", default="equations_3e")
    s.add_argument("--niveau", default="3e")
    s.add_argument("--graine", type=int, default=0)
    s.add_argument("--journal", help="fichier SQLite du journal d'événements")
    s.set_defaults(f=cmd_session)
    b = sp.add_parser("benchmark")
    b.add_argument("--chapitre", default="equations_3e")
    b.add_argument("--niveau", default="3e")
    b.add_argument("--eleves", type=int, default=100)
    b.add_argument("--graine", type=int, default=1)
    b.add_argument("--profil", default="tous", choices=["tous", "fort", "moyen", "fragile", "historique"])
    b.set_defaults(f=cmd_benchmark)
    w = sp.add_parser("serveur", help="API + interface élève")
    w.add_argument("--donnees", default="donnees", help="dossier des bases SQLite (identité et journal séparés)")
    w.add_argument("--hote", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)
    w.set_defaults(f=cmd_serveur)
    a = p.parse_args(argv)
    try:
        return a.f(a)
    except (EOFError, KeyboardInterrupt):
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
