from datetime import date

import pytest

from tuteur.privacy import filtrer
from tuteur.storage import CoffreIdentite, JournalEvenements
from tuteur.storage.evenements import Evenement
from tuteur.storage.identite import Identite


def test_filtrage_pii():
    f = filtrer("Je m'appelle Léa, collège Jean Moulin en 4e B, lea@exemple.fr, 06 12 34 56 78, Mme Durand", ("Léa",))
    for fuite in ("Léa", "Jean Moulin", "lea@exemple.fr", "06 12", "Durand", "4e B"):
        assert fuite not in f.texte
    assert filtrer("Combien font 3 × 4 ?").texte == "Combien font 3 × 4 ?"


def test_pseudonyme_aleatoire_et_coffre_separe():
    coffre = CoffreIdentite()
    a = coffre.creer("Léa", 2012, "3e", "parent@exemple.fr")
    b = coffre.creer("Léa", 2012, "3e", "parent@exemple.fr")
    assert a.eleve != b.eleve and "Léa" not in a.eleve


def test_moins_de_15_ans_consentement_parental():
    ident = Identite("x", "Léa", date.today().year - 13, "4e", "p@e.fr")
    assert CoffreIdentite.consentement_parental_requis(ident)
    coffre = CoffreIdentite()
    with pytest.raises(ValueError):
        coffre.creer("Léa", date.today().year - 13, "4e")
    a = coffre.creer("Léa", date.today().year - 13, "4e", "p@e.fr")
    with pytest.raises(PermissionError):
        coffre.consentir(a.eleve, "entrainement_ocr", True, par_parent=False)
    coffre.consentir(a.eleve, "entrainement_ocr", True, par_parent=True)
    assert coffre.a_consenti(a.eleve, "entrainement_ocr")
    coffre.consentir(a.eleve, "entrainement_ocr", False, par_parent=False)  # retrait toujours possible
    assert not coffre.a_consenti(a.eleve, "entrainement_ocr")


def test_journal_ajout_seul_et_effacement():
    from datetime import datetime, timezone
    import sqlite3

    j = JournalEvenements()
    j.ajouter(Evenement("p1", datetime.now(timezone.utc), "reponse", {}, "v", "v"))
    with pytest.raises(sqlite3.DatabaseError):
        j.db.execute("UPDATE evenements SET type = 'x'")
    assert j.effacer_eleve("p1") == 1
    assert list(j.lire("p1")) == []
