import pytest

from tuteur.contenu import charger


@pytest.fixture(scope="session")
def contenu():
    return charger()
