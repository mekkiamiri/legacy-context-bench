# Protocole

## Règles communes à toutes les configurations

1. **Même code :** Apache Roller, commit `52e064a0104c89e141100d22e5bc990899ba3c2f`.
2. **Même agent et même modèle** pour les 5 configurations ; modèle et version notés dans `results/<config>/answers.json` (`_meta`).
3. **Même consigne**, une session neuve par question : « Réponds à la question sur l'application Apache Roller présente dans le dossier courant. Cite les fichiers qui justifient ta réponse. »
4. **Aucune aide humaine** pendant la réponse.
5. **3 passages** par question et par configuration ; on garde la moyenne et l'écart.

## Ce qui est mesuré

| Mesure | Comment |
|---|---|
| Bonnes réponses | `bench/score.py` : part des critères présents dans la réponse, puis relecture humaine de chaque note |
| Tokens | total entrée + sortie rapporté par l'agent, y compris le coût de construction du contexte (indexation RAG, graphe) noté à part |
| Temps | horloge murale de la question à la réponse ; temps de préparation (index, graphe, démarrage de l'appli) noté à part |

## Familles de questions

- **structure** (7) : de quoi l'appli est faite. Pièges : dépendances commentées, mapping JPA en XML.
- **comportement** (8) : ce qui se passe à l'exécution. Pièges : commentaire qui contredit le code, traitements différés.
- **donnees** (5) : ce qui est stocké, et comment.

Hypothèse de départ (à confirmer ou à infirmer) : le graphe aide surtout la structure, l'exécution aide surtout le comportement, et aucune configuration seule n'est la meilleure partout.

## Biais connus

- Les questions sont écrites par une seule personne, qui connaît les réponses. Toute proposition de question est bienvenue (issue).
- La notation par mots-clés peut sur-noter une réponse qui cite un mot sans le comprendre : d'où la relecture humaine.
- Roller est un projet public : le modèle a peut-être vu son code à l'entraînement. Les pièges (commentaire faux, dépendance commentée) servent aussi à le détecter.

## Calibration (17/11/2026)
Après relecture humaine du passage 1 de la configuration « agent seul », et **avant** de mesurer les autres configurations, deux questions ont été corrigées :
- C02 : « numéro » ajouté aux mots-clés (une réponse juste était notée fausse).
- C08 : la réponse de référence couvrait un seul chemin ; l'approbation par un modérateur vide tout le cache du blog (`Comments.java:382`). Référence et critères élargis.
Les notes de toutes les configurations sont calculées avec ce fichier corrigé.

## Jeu difficile (17/11/2026)
Après une première mesure à 96-97 % pour l'agent seul, 10 questions plus difficiles ont été ajoutées (`questions/questions-difficiles.json`) : listes exhaustives, croisement configuration et code, pile d'appels à remonter.
**Erreur de l'auteur des questions, relevée par l'agent :** pour H03, la référence disait qu'un plugin existait sans être activé ; l'agent a répondu, aux 3 passages, que les 4 plugins sont actifs (ligne de continuation 528 de `roller.properties`). L'agent avait raison. La référence est corrigée et la question est gardée comme test de fausse prémisse.
