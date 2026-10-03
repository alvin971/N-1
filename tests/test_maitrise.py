from datetime import datetime, timedelta, timezone

from tuteur.knowledge import Niveau, ProfilEleve, Tentative, mise_a_jour
from tuteur.mathengine import Statut

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def t(modele="m1", d=1, statut=Statut.CORRECT, err=None, aide=False, quand=T0, principale=True):
    return Tentative("cle", modele, d, statut, err, aide, quand, principale)


def test_bkt_monotone():
    p = 0.3
    assert mise_a_jour(p, True, 0.02) > p
    assert mise_a_jour(p, False, 0.02, apprentissage=False) < p


def test_qcm_moins_probant_que_saisie():
    assert mise_a_jour(0.3, True, 0.25, apprentissage=False) < mise_a_jour(0.3, True, 0.02, apprentissage=False)


def test_une_seule_bonne_reponse_ne_suffit_pas():
    prof = ProfilEleve("e", "4e")
    e = prof.enregistrer("kc", 0.9, t(d=2), 0.02)
    assert not e.est_maitrisee()


def test_un_seul_format_ne_suffit_pas():
    prof = ProfilEleve("e", "4e")
    for _ in range(6):
        e = prof.enregistrer("kc", 0.3, t(modele="m1", d=2), 0.02)
    assert e.p > 0.95 and not e.est_maitrisee()
    e = prof.enregistrer("kc", 0.3, t(modele="m2", d=1), 0.02)
    assert e.est_maitrisee() and e.niveau() is Niveau.MAITRISEE


def test_aide_non_comptee():
    prof = ProfilEleve("e", "4e")
    for m in ("m1", "m2", "m1", "m2"):
        e = prof.enregistrer("kc", 0.3, t(modele=m, d=2, aide=True), 0.02)
    assert not e.est_maitrisee()


def test_consolidation_et_rechute():
    prof = ProfilEleve("e", "4e")
    for m, d in (("m1", 1), ("m2", 2), ("m1", 2), ("m2", 1), ("m1", 2)):
        e = prof.enregistrer("kc", 0.5, t(modele=m, d=d), 0.02)
    assert e.est_maitrisee()
    e = prof.enregistrer("kc", 0.5, t(quand=T0 + timedelta(days=2)), 0.02)
    assert e.niveau() is Niveau.CONSOLIDEE
    e = prof.enregistrer("kc", 0.5, t(statut=Statut.INCORRECT, err="x.bug", quand=T0 + timedelta(days=3)), 0.02)
    assert e.maitrisee_le is None


def test_kc_secondaire_echec_non_informatif():
    prof = ProfilEleve("e", "4e")
    e = prof.enregistrer("kc", 0.5, t(statut=Statut.INCORRECT, principale=False), 0.02)
    assert e.p == 0.5
