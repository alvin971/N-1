import pytest

from tuteur.ocr import (
    CopieEleve, Decision, Hypothese, Metriques, OrdreInterdit, evaluer_candidate, porte_deploiement,
    supprimer_metadonnees_jpeg,
)
from tuteur.ocr.curation import VersionDataset

JPEG = b"\xff\xd8" + b"\xff\xe0\x00\x04JF" + b"\xff\xe1\x00\x08Exif" + b"GP" + b"\xff\xda\x00\x02DATA\xff\xd9"


class FauxOCR:
    version = "ocr-test-1"

    def __init__(self, *hyps):
        self.hyps = [Hypothese(t, c) for t, c in hyps]

    def transcrire(self, image, n_meilleures=3):
        return self.hyps


def test_exif_supprime():
    propre = supprimer_metadonnees_jpeg(JPEG)
    assert b"Exif" not in propre and b"DATA" in propre and b"JF" in propre


def test_confirmation_obligatoire_avant_verdict():
    c = CopieEleve("p", "3x + 5 = 20", JPEG, consentement_entrainement=True)
    c.transcrire(FauxOCR(("3x = 15\nx = 5", 0.9)))
    with pytest.raises(OrdreInterdit):
        c.corriger()
    c.confirmer("3x = 15\nx = 5")
    assert c.corriger().juste
    with pytest.raises(OrdreInterdit):
        c.confirmer("autre chose")  # pas de « correction de l'OCR » après avoir vu le verdict


def _copie(hyps, finale, consent=True):
    c = CopieEleve("p", "2x = 6", JPEG, consentement_entrainement=consent)
    c.transcrire(FauxOCR(*hyps))
    c.confirmer(finale)
    c.corriger()
    return c


def test_curation():
    assert evaluer_candidate(_copie([("x = 3", 0.99)], "x = 3", consent=False), set(), 1.0)[0] is Decision.REJETEE
    assert evaluer_candidate(_copie([("x = 8", 0.6), ("x = 3", 0.3)], "x = 3"), set(), 1.0)[0] is Decision.ACCEPTEE
    assert evaluer_candidate(_copie([("x = 8", 0.6)], "x = 3 + 2 - 2 + 0 * 7"), set(), 1.0)[0] is Decision.REVUE_HUMAINE
    assert evaluer_candidate(_copie([("x = 3", 0.99)], "x = 3"), set(), 0.2)[0] is Decision.REVUE_HUMAINE
    c = _copie([("x = 3", 0.99)], "x = 3")
    assert evaluer_candidate(c, {c.empreinte}, 1.0)[0] is Decision.REJETEE  # jeu de référence protégé


def test_manifeste_deterministe():
    c = evaluer_candidate(_copie([("x = 8", 0.6), ("x = 3", 0.3)], "x = 3"), set(), 1.0)[2]
    assert VersionDataset([c]).manifeste()["version"] == VersionDataset([c]).manifeste()["version"]
    assert "eleve" not in str(VersionDataset([c]).manifeste())


def test_porte_de_deploiement():
    a = Metriques({"fractions": 0.05, "ratures": 0.08}, {})
    assert porte_deploiement(a, Metriques({"fractions": 0.03, "ratures": 0.07}, {}))[0]
    ok, raisons = porte_deploiement(a, Metriques({"fractions": 0.01, "ratures": 0.10}, {}))
    assert not ok and any("ratures" in r for r in raisons)
