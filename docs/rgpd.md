# RGPD et mineurs — architecture et points à trancher

> Document d'ingénierie, pas un avis juridique. À valider avec un DPO / conseil spécialisé.

## Principes appliqués dans le code

| Principe | Mise en œuvre | Où |
|---|---|---|
| Séparation identité / pédagogie | Coffre d'identité distinct ; les événements ne portent qu'un pseudonyme | `storage/identite.py`, `storage/evenements.py` |
| Pseudonyme non dérivable | `uuid4` aléatoire, jamais un hash du nom ou de l'e-mail | `CoffreIdentite.creer` |
| Pseudonymisation ≠ anonymisation | Les données pédagogiques restent des données personnelles : mêmes protections | — |
| Minimisation | Prénom, année de naissance, niveau, contact parent ; pas d'établissement par défaut | `identite.py` |
| Consentement < 15 ans | Art. 45 loi Informatique et Libertés : consentement du mineur ET d'un parent pour les finalités fondées sur le consentement | `CoffreIdentite.consentir` |
| Finalités distinctes | `service`, `entrainement_ocr`, `recherche_pedagogique` ; retrait toujours possible | `FINALITES` |
| Effacement | Suppression du coffre + purge du journal par pseudonyme | `effacer`, `effacer_eleve` |
| Conservation limitée | Purge par type d'événement et par date | `purger_avant` |
| Photos | Suppression EXIF à la réception ; recadrage de la zone mathématique ; image jetée sans consentement d'entraînement | `ocr/flux.py`, `ocr/curation.py` |
| LLM | Hébergement UE exigé par le code ; filtrage des données personnelles ; données structurées seulement | `teacher/enseignant.py`, `privacy/pii.py` |
| Pas d'entraînement incontrôlé | Dataset OCR uniquement à partir de paires consenties, curées, versionnées, sans identifiant | `ocr/curation.py` |

Limite assumée : le filtrage par motifs **réduit** l'exposition du texte libre, il ne la supprime
pas. D'où l'exigence d'un modèle hébergé dans l'UE sous contrat de sous-traitance (art. 28)
interdisant l'entraînement sur les données.

## Doit rester dans l'UE

- Coffre d'identité, consentements.
- Journal d'événements, états de maîtrise, sauvegardes.
- Photos et inférence OCR.
- **Toute inférence LLM qui reçoit du texte d'élève.**
- Journaux techniques, observabilité, analytics (auto-hébergés).
- Annotation des données réelles.

Hébergeurs à privilégier : OVHcloud, Scaleway, Outscale… (qualification SecNumCloud utile pour les
marchés publics). Les clouds américains, même en région UE, restent soumis au CLOUD Act ; la
doctrine du ministère de l'Éducation nationale leur est défavorable.

## Peut sortir de l'UE

- Génération de données **synthétiques** (aucune donnée d'élève).
- Contenu pédagogique (graphe, modèles, cours), contenu statique non personnel.

## Fuites hors UE fréquentes à éviter

Sentry / Datadog / LangSmith en SaaS, Google Analytics / Firebase / Mixpanel, proxy terminant le
TLS hors UE, fournisseur d'e-mails, outils de support. Notifications push (FCM / APNs) : aucun
contenu personnel dans la charge utile.

## Points à trancher tôt

1. **Modèle commercial** : vente aux familles (vous êtes responsable de traitement) ou aux
   établissements (vous êtes en général sous-traitant ; accès via le GAR et l'ENT avec
   identifiants pseudonymes). Cela change l'architecture d'authentification et les contrats.
2. **AIPD** : quasi certainement obligatoire (personnes vulnérables, évaluation, technologie
   innovante).
3. **AI Act** : les systèmes qui évaluent les acquis ou orientent le parcours d'apprentissage
   dans des établissements d'enseignement relèvent de l'annexe III (haut risque). Calendrier
   d'application à vérifier (des reports ont été proposés). **Interdit** en milieu éducatif : la
   reconnaissance des émotions — aucune analyse webcam. L'architecture déterministe et
   journalisée facilite la documentation, la traçabilité et la supervision humaine (escalade
   intégrée à la session).
4. Base légale de chaque finalité (exécution du contrat, intérêt légitime, consentement) et
   durées de conservation.
