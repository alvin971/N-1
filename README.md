# Tuteur mathématique adaptatif — noyau déterministe (MVP 6e → 3e)

Un professeur particulier de mathématiques qui **retrouve la racine d'une lacune**, même plusieurs
années en arrière, construit le parcours de rattrapage, vérifie la maîtrise, puis remonte au
niveau du chapitre. Premier périmètre : **« Nombres et calculs », chaîne des équations de 3e**.

Philosophie : **déterministe partout où c'est possible**.

| Besoin | Outil | Où |
|---|---|---|
| Mathématiques exactes | analyseur maison + SymPy | `src/tuteur/mathengine/` |
| Relations de prérequis | graphe YAML versionné (DAG) | `content/graphe.yaml`, `src/tuteur/graph/` |
| Erreurs typiques | règles exécutables (connaissance experte) | `content/erreurs_typiques.yaml`, modèles d'exercices |
| Exercices | générateurs paramétriques à graine | `src/tuteur/exercises/` |
| Mesure de la maîtrise | BKT + critères stricts | `src/tuteur/knowledge/` |
| Diagnostic | inférence bayésienne sur le sous-graphe + gain d'information | `src/tuteur/diagnostic/` |
| Décisions pédagogiques | machine à états + règles versionnées, journalisées | `src/tuteur/session/` |
| Explications | contenu pré-rédigé ; LLM UE optionnel sous garde-fous | `content/cours.yaml`, `src/tuteur/teacher/` |
| Lecture de copies | interface OCR + boucle d'active learning supervisée | `src/tuteur/ocr/` |
| RGPD | coffre d'identité séparé, pseudonymes aléatoires, filtrage PII | `src/tuteur/storage/`, `src/tuteur/privacy/` |

Aucun appel à un modèle de langage n'est nécessaire pour faire tourner le tuteur.

## Démarrage

```bash
pip install -e ".[dev]"
tuteur serveur                           # interface élève → http://127.0.0.1:8000
pytest                                   # ~210 tests
tuteur valider-contenu                   # cohérence graphe / erreurs / cours / modèles
tuteur session --chapitre equations_3e   # séance interactive (« ? » = indice)
tuteur benchmark --eleves 100            # diagnostic vs descente séquentielle
tuteur etapes "2(x+3) = x - 4" "2x + 3 = x - 4" "x = -7"
tuteur exercice eq.ax_plus_b.resoudre --difficulte 2 --graine 7 --qcm
tuteur graphe --chapitre equations_3e
```

## Ce qui est implémenté

- **Interface élève web** (`tuteur serveur`) : inscription avec consentement parental sous
  15 ans, choix du chapitre, test de départ, bilan expliqué, cours, exemples corrigés, exercices
  avec **clavier mathématique MathLive** (servi localement, aucun CDN tiers), indices, retour
  ciblé sur l'erreur typique, carte des compétences et parcours de rattrapage, export et
  effacement des données. Fonctionne sur téléphone et ordinateur, thème clair/sombre.
- **API HTTP** (FastAPI, doc interactive sur `/api/docs`) : jeton opaque par élève, cloisonnement,
  en-têtes de sécurité (CSP stricte), la bonne réponse n'est jamais envoyée au navigateur,
  progression reconstruite depuis le journal après redémarrage.

- **Graphe** : 34 KC du CE1 à la 3e (chaîne des équations), arêtes typées forte/faible et
  justifiées, chapitres, validation (DAG, niveaux cohérents, références).
- **Moteur maths** : lecture de la notation scolaire française sans `eval` ; équivalence
  exacte ; **prédicats de forme** (développée réduite, factorisée, fraction irréductible,
  dénominateur imposé) ; verdict à 4 issues ; **vérification ligne par ligne** des résolutions
  d'équations avec localisation et identification de l'erreur.
- **34 modèles d'exercices** paramétriques (un par KC au minimum), solution construite d'abord,
  **contrainte de pouvoir diagnostique** (une erreur typique ne doit jamais donner la bonne
  réponse), QCM dont les distracteurs sont produits par les erreurs typiques, exemples corrigés.
- **33 erreurs typiques** exécutables, chacune rattachée à la KC où se trouve la lacune réelle.
- **Diagnostic adaptatif** : environ 13 questions pour situer un élève de 3e sur 27 KC ;
  ≈ 97 % des KC bien classées et ≈ 84 % des lacunes racines retrouvées sur élèves simulés
  (vs 89,5 % et 60 % pour la descente séquentielle). Voir `docs/benchmarks.md`.
- **Session** : révision espacée → diagnostic → remédiation (descente dynamique sur erreur
  typique, adaptation de difficulté, exemples corrigés, escalade vers un humain) → transfert.
  Chaque décision est journalisée avec sa **probabilité** (évaluation hors ligne future).
- **Journal d'événements** en ajout seul ; l'état de maîtrise est une projection rejouable.
- **RGPD** : coffre d'identité séparé, consentements granulaires (règle des 15 ans), droit à
  l'effacement, filtrage des données personnelles avant tout LLM, passerelle LLM refusant les
  modèles hors UE.
- **OCR** : flux « confirmation avant verdict », suppression EXIF, curation des corrections,
  dataset versionné, porte de déploiement par catégorie. *Pas encore de modèle OCR branché.*

## Ce qui n'est pas encore fait (prochaines étapes)

1. Relecture du graphe et des erreurs typiques par 1 à 2 enseignants ; extension à ~200 KC
   (« Nombres et calculs » complet 6e → 3e).
2. Compte récupérable (connexion par lien envoyé au parent) ; persistance PostgreSQL ;
   tableau de bord parent / enseignant.
3. Pilote réel (quelques centaines d'élèves) : calibration des paramètres BKT et des a priori,
   test avant/après indépendant.
4. Choix et fine-tuning du modèle OCR (voir `docs/architecture.md` §OCR) ; LLM auto-hébergé UE
   pour le dialogue ouvert.
5. Optimisation de la politique (bandits contextuels) une fois les trajectoires journalisées.

Documentation : [`docs/architecture.md`](docs/architecture.md) · [`docs/rgpd.md`](docs/rgpd.md) ·
[`docs/benchmarks.md`](docs/benchmarks.md)
