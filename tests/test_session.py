import random
from datetime import datetime, timezone

from tuteur.knowledge import ProfilEleve
from tuteur.session import Session, TypeAction, horloge_fixe, reconstruire_profil
from tuteur.storage import JournalEvenements
from tuteur.simulation import EleveSimule


def _jouer(contenu, eleve, session, horloge, max_questions=300):
    n = 0
    while True:
        a = session.prochaine_action()
        if a.type is TypeAction.FIN:
            return a, n
        if a.type is TypeAction.QUESTION:
            r = session.repondre(eleve.repondre(a.item, contenu))
            n += 1
            if not r.verdict.juste and a.mode.value == "remediation":
                eleve.apprendre(a.item.kcs[0], contenu)
            horloge.avancer(seconds=30)
        assert n < max_questions


def _eleve(contenu, lacune, cibles, graine):
    kcs = contenu.graphe.sous_graphe(cibles)
    non = {lacune} | contenu.graphe.descendants(lacune, set(kcs))
    return EleveSimule({k for k in kcs if k not in non}, p_apprentissage=0.5, rng=random.Random(graine))


def test_session_complete_et_rejouable(contenu):
    eleve = _eleve(contenu, "rel.soustraction", list(contenu.graphe.chapitres["equations_3e"].cibles), 2)
    h = horloge_fixe(datetime(2026, 10, 3, tzinfo=timezone.utc))
    journal = JournalEvenements()
    profil = ProfilEleve("pseudo-1", "3e")
    s = Session(contenu, profil, "equations_3e", journal=journal, graine=2, horloge=h)
    fin, n = _jouer(contenu, eleve, s, h)
    assert "Séance terminée" in fin.texte
    # la lacune racine a été travaillée AVANT les équations
    reponses = [e.donnees for e in journal.lire("pseudo-1", ("reponse",)) if e.donnees["mode"] == "remediation"]
    kcs_travaillees = [r["kcs"][0] for r in reponses]
    assert "rel.soustraction" in s.resultat_diagnostic.frontiere
    assert kcs_travaillees[0] == "rel.soustraction"
    assert kcs_travaillees.index("rel.soustraction") < kcs_travaillees.index("eq.x_plus_a_egal_b")
    # chaque décision journalise sa probabilité (évaluation hors ligne future)
    assert all(0 < d.proba <= 1 for d in s.decisions)
    # projection : rejouer le journal redonne exactement le même état
    p2 = reconstruire_profil(journal, contenu, "pseudo-1", "3e")
    assert {k: round(e.p, 9) for k, e in profil.etats.items()} == {k: round(e.p, 9) for k, e in p2.etats.items()}
    # le journal ne contient aucune donnée d'identité
    assert all(e.eleve == "pseudo-1" for e in journal.lire("pseudo-1"))


def test_question_illisible_reposee(contenu):
    s = Session(contenu, ProfilEleve("p", "3e"), "equations_3e", graine=0)
    a = s.prochaine_action()
    r = s.repondre("2 +")
    assert r.verdict.statut.value == "illisible"
    assert s.prochaine_action().item == a.item


def test_aide_marque_la_tentative(contenu):
    j = JournalEvenements()
    s = Session(contenu, ProfilEleve("p", "3e"), "equations_3e", journal=j, graine=0)
    a = s.prochaine_action()
    assert s.demander_aide().startswith("Indice")
    s.repondre(a.item.spec.affichage() if a.item.spec.type != "booleen" else "oui")
    assert next(j.lire("p", ("reponse",))).donnees["aide"] is True
