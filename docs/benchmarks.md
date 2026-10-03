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

| Profil | Stratégie | Exactitude KC | Lacunes racines retrouvées | Précision | Questions |
|---|---|---|---|---|---|
| fort | **descendante** | **94,8 %** | 82,4 % | **85,3 %** | **11,1** |
| fort | exhaustive | 93,9 % | 83,5 % | 72,4 % | 13,7 |
| fort | descente naïve | 93,2 % | 67,8 % | 65,8 % | 7,1 |
| moyen | **descendante** | 95,1 % | 78,3 % | **91,8 %** | **13,5** |
| moyen | exhaustive | 95,2 % | 86,1 % | 89,1 % | 15,0 |
| moyen | descente naïve | 88,9 % | 55,2 % | 72,5 % | 10,7 |
| fragile | **descendante** | 96,2 % | 80,7 % | **94,9 %** | **15,8** |
| fragile | exhaustive | 96,3 % | 84,1 % | 93,0 % | 16,2 |
| fragile | descente naïve | 83,9 % | 59,0 % | 81,0 % | 14,7 |

Lecture : la stratégie descendante pose moins de questions et se trompe moins quand elle désigne une
lacune (précision), au prix d'un rappel un peu plus faible chez les élèves moyens (elle ne va pas
chercher une notion ancienne qu'aucun exercice raté ne met en cause). Un élève qui maîtrise tout est
diagnostiqué en 3 à 4 questions, sans jamais revenir au primaire. Les « forts » restent à ~11
questions en moyenne car le simulateur leur attribue environ une notion oubliée isolément.

## Cohérence du contenu (CI)

Pour chaque modèle × difficulté × 25 graines : bonne réponse acceptée (valeur et forme), chaque
erreur typique reconnue comme telle, QCM à bonne option unique. Voir `tests/test_exercices.py`.
