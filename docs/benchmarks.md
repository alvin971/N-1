# Benchmarks

## Diagnostic adaptatif (élèves simulés)

Reproduire : `tuteur benchmark --eleves 100 [--chapitre …] [--niveau …]` (graine 1).

**Protocole**
- Vérité terrain : 0 à 2 lacunes racines tirées dans le sous-graphe, propagées à leurs
  descendants. Les KC du niveau de l'élève sont non maîtrisées avec une probabilité de 0,6, et
  3 % de KC sont oubliées isolément. Ce processus est **différent** de l'a priori du diagnostic,
  pour éviter d'évaluer le modèle sur ses propres hypothèses.
- Élève simulé : 8 % d'erreurs d'inattention ; produit une erreur typique dans 60 % des cas
  quand la KC de cette erreur n'est pas maîtrisée ; sinon réponse fausse quelconque. Ses
  réponses sont des **textes** passés dans le vrai correcteur.
- Référence : la « descente séquentielle » de l'hypothèse initiale (échec → on teste les
  prérequis, réussite → on s'arrête).

**Résultats (contenu 2026.10-mvp1, 100 élèves par chapitre)**

| Chapitre | Méthode | Exactitude KC | Lacunes racines retrouvées | Précision (frontière) | Questions |
|---|---|---|---|---|---|
| Équations 3e (27 KC) | gain d'information | **97,4 %** | **84,2 %** | **93,8 %** | 12,7 |
| | descente séquentielle | 89,5 % | 60,4 % | 80,2 % | 11,6 |
| Fractions 4e | gain d'information | **97,8 %** | **92,5 %** | **95,2 %** | 7,2 |
| | descente séquentielle | 91,8 % | 84,2 % | 89,0 % | 6,8 |
| Calcul littéral 3e | gain d'information | **96,5 %** | **87,7 %** | **93,7 %** | 6,8 |
| | descente séquentielle | 93,2 % | 84,8 % | 92,5 % | 6,5 |

**Réglages comparés (équations 3e, 30 à 40 élèves)**
- QCM au lieu de la saisie libre : exactitude 87,8 %, lacunes racines retrouvées 50 %. Le hasard
  à 25 % coûte cher ; le QCM est à réserver aux distracteurs issus d'erreurs typiques.
- Probabilité conditionnelle non plafonnée : lacunes racines retrouvées 66 %. Les notions de
  l'année « héritaient » d'une fausse certitude.
- Poids du temps de réponse 1 / 0,5 / 0 : même exactitude ; 0,5 retenu (moins de questions,
  évite d'ouvrir le test par des tables de multiplication).

**Limites** : ce sont des élèves *simulés*. Ces chiffres valident l'algorithme, pas l'efficacité
pédagogique. La prochaine mesure sérieuse est un pilote réel comparant le diagnostic court à un
test long exhaustif sur un échantillon d'élèves.

## Stratégie « descendante » (on part du présent) — par profil d'élève

Reproduire : `tuteur benchmark --eleves 60` (profils fort / moyen / fragile, chapitre équations 3e,
31 KC). Profils : fort = aucune lacune racine, 15 % de notions de 3e non acquises ; moyen = 0–1
lacune, 45 % ; fragile = 1–3 lacunes, 75 % ; plus 3 % de notions oubliées isolément partout.

Avec la règle « une lacune exige 2 preuves directes » (démarche hypothèse → vérification) :

| Profil | Stratégie | Exactitude KC | Lacunes confirmées | + hypothèses signalées | Précision | Questions |
|---|---|---|---|---|---|---|
| fort | **descendante** | **94,9 %** | 76,5 % | 79,2 % | **85,3 %** | **11,5** |
| fort | exhaustive | 93,5 % | 82,2 % | 82,2 % | 71,8 % | 13,9 |
| fort | descente naïve | 93,0 % | 68,0 % | 68,0 % | 68,0 % | 7,2 |
| moyen | **descendante** | 94,5 % | 60,0 % | 67,3 % | 87,2 % | 15,3 |
| moyen | exhaustive | 94,8 % | 85,3 % | 85,3 % | 87,9 % | 15,3 |
| moyen | descente naïve | 88,3 % | 53,9 % | 53,9 % | 72,0 % | 11,0 |
| fragile | **descendante** | 95,2 % | 55,1 % | 65,2 % | **96,0 %** | 17,1 |
| fragile | exhaustive | 96,2 % | 83,1 % | 83,1 % | 92,3 % | 16,3 |
| fragile | descente naïve | 84,2 % | 59,5 % | 59,5 % | 80,7 % | 14,9 |

Lecture honnête :
- la rigueur a un coût : à budget égal (18 questions), un élève qui a 2 ou 3 lacunes ne peut pas les
  voir toutes confirmées dès le test ; elles restent « à vérifier » ou sont découvertes pendant
  l'entraînement (descente sur erreur typique, compétence qui résiste) ;
- la stratégie exhaustive « trouve » plus de lacunes car elle conclut sur des probabilités ; dans ce
  simulateur, ses probabilités sont justes car les élèves simulés suivent le même modèle que le
  diagnostic. Sur de vrais élèves, une conclusion fondée sur deux preuves directes est plus robuste
  qu'une probabilité issue d'un modèle imparfait — à vérifier lors du pilote ;
- les élèves simulés ne rédigent pas leurs résolutions : l'apport de la « copie » ligne par ligne
  (une preuve directe et localisée à chaque équation) n'est pas mesuré ici.

## Cohérence du contenu (CI)

Pour chaque modèle × difficulté × 25 graines : bonne réponse acceptée (valeur et forme), chaque
erreur typique reconnue comme telle, QCM à bonne option unique. Voir `tests/test_exercices.py`.
