import pytest

from tuteur.exercises import REGISTRE
from tuteur.mathengine import Statut
from tuteur.teacher import EnseignantDeterministe, PasserelleLLM, RegionNonAutorisee, egalites_fausses


class FauxClient:
    def __init__(self, reponse, region="UE"):
        self.reponse, self.region, self.nom = reponse, region, "faux"
        self.recu = None

    def completer(self, systeme, utilisateur):
        self.recu = utilisateur
        return self.reponse


def _item_et_verdict():
    item = REGISTRE["eq.ax_plus_b.resoudre"].instancier(1, 1)
    return item, item.corriger("x = 1000")


def test_region_hors_ue_refusee(contenu):
    with pytest.raises(RegionNonAutorisee):
        PasserelleLLM(FauxClient("ok", region="US"), EnseignantDeterministe(contenu))


def test_calcul_faux_rejete(contenu):
    item, v = _item_et_verdict()
    p = PasserelleLLM(FauxClient("Regarde : 3 × 4 = 13, donc c'est simple."), EnseignantDeterministe(contenu))
    assert "13" not in p.reformuler(item, v)
    assert p.journal_refus


def test_reponse_non_divulguee(contenu):
    item, v = _item_et_verdict()
    p = PasserelleLLM(FauxClient(f"La réponse est {item.spec.affichage()}"), EnseignantDeterministe(contenu))
    assert p.reformuler(item, v) == EnseignantDeterministe(contenu).retour(item, v)


def test_pii_filtree_avant_envoi(contenu):
    item, v = _item_et_verdict()
    client = FauxClient("Reprends la méthode : on isole le terme en x.")
    PasserelleLLM(client, EnseignantDeterministe(contenu)).reformuler(item, v, "moi c'est Léa, j'ai pas compris", prenom="Léa")
    assert "Léa" not in client.recu


def test_egalites():
    assert egalites_fausses("2 + 2 = 4 et 5 × 3 = 15") == []
    assert egalites_fausses("7 - 10 = 3") == ["7 - 10 = 3"]


def test_retour_erreur_typique(contenu):
    item = REGISTRE["lit.distributivite.simple"].instancier(0, 1)
    v = item.corriger(list(item.spec.erreurs.values())[0].__str__().replace("*", ""))
    assert v.statut is Statut.INCORRECT
    assert "chaque terme" in EnseignantDeterministe(contenu).retour(item, v).lower()
