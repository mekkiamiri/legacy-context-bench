# 3. Agent + graphe du code

L'agent garde ses outils de base (Read, Grep, Glob) et peut en plus interroger un graphe du code : classes, méthodes, appels, héritage, et liens entre la configuration et le code.

- **Outil :** extracteur écrit pour le banc (`graph_build.py`, Python, bibliothèque standard seulement), et `graph_query.py` pour l'interroger. Générique pour un projet Java legacy : Maven ou Gradle, JSP, XML (web.xml, struts.xml, struts-config.xml, persistence.xml, orm.xml, hbm.xml, Spring XML), SQL.
- **Préparation sur Roller :** 1,0 s, graphe JSON de 7,2 Mo (783 types, 6 250 méthodes, 20 860 appels, 76 routes, 26 entités, 31 tables). Voir [DEMO.md](DEMO.md).
- **Ce qu'on attend :** bon pour la structure, les chemins d'appel et ce qui est déclaré en configuration ; aveugle sur ce que le code décide à l'exécution. L'hypothèse de départ (« aveugle sur le XML et les properties ») vaut pour les outils de graphe qui ne lisent que le Java ; cet extracteur relie volontairement la configuration au code.
- **Résultats :** `results/3-graphe/` (à venir).

## Commandes

```bash
# une fois par projet (et par commit) :
python3 configurations/3-graphe/graph_build.py <projet> .contexte/graphe.json
# requêtes :
python3 configurations/3-graphe/graph_query.py who-calls ThreadManager.registerLease   # appelants (interfaces comprises)
python3 configurations/3-graphe/graph_query.py callees CommentServlet.doPost           # appelés
python3 configurations/3-graphe/graph_query.py route /monblog/ [--dispatcher FORWARD]  # filtres, servlet, action, contrôleur
python3 configurations/3-graphe/graph_query.py table roller_properties                 # entité <-> table, CREATE TABLE, SQL
python3 configurations/3-graphe/graph_query.py neighbors CommentValidator              # héritage, usages, configuration
python3 configurations/3-graphe/graph_query.py find validator                          # cherche un nom
```

Graphe par défaut : variable `GRAPHE_JSON`, sinon `.contexte/graphe.json`. Option `--max N` pour la longueur des listes.

Mesure avec un agent (le lanceur construit le graphe s'il manque et note son temps dans `_meta.preparation`) :

```bash
python3 bench/run_agent.py --roller /tmp/roller --config 3-graphe --passes 3 --model claude-sonnet-5-5
```

L'agent reçoit `--tools Read,Grep,Glob,Bash`, la seule règle `Bash(python3 <banc>/configurations/3-graphe/graph_query.py:*)` et une phrase ajoutée au prompt système qui liste les requêtes. La consigne et la question restent celles de la configuration 1.

## Ce que contient le graphe

| Nœuds / arêtes | Source |
|---|---|
| classes, interfaces, enums, records ; méthodes (ligne de signature) ; champs | sources Java |
| hérite / implémente | `extends`, `implements`, résolus en nom complet par les imports et le paquetage |
| appelle | appels de méthodes dans les corps ; receveur typé par les champs, paramètres, variables locales, appels statiques, `this`/`super`, et le type de retour pour les appels chaînés `a.b().c()` |
| utilise | types du projet cités dans un fichier |
| route | `web.xml` (servlets, filtres dans l'ordre avec leurs dispatchers, listeners), `struts.xml` (namespace + action + extension), `struts-config.xml` (Struts 1), annotations `@RequestMapping`/`@GetMapping`…, `@Path`, `@WebServlet`, `@WebFilter` |
| mappe (entité -> table) | `orm.xml`, `*.hbm.xml`, `@Entity`/`@Table` ; unités de `persistence.xml` |
| table | `CREATE TABLE` dans `.sql`, `.ddl`, `.vm`, `.ftl`, Liquibase `createTable` |
| SQL dans une chaîne | chaîne Java contenant un mot SQL et un nom de table connu |
| référence de configuration | nom complet d'une classe du projet cité dans un `.xml`, `.properties`, `.jsp`, `.tld`, `.vm`, `.yml` ; clé `.properties` retrouvée même sur une ligne de continuation ; ligne **en commentaire** signalée comme inactive |
| ressource chargée | chaîne Java qui ressemble à un chemin de fichier (`/…/runtimeConfigDefs.xml`), reliée au fichier du projet de même nom |
| beans | `<bean id class>` des fichiers Spring XML |

## Limites, honnêtement

L'extracteur n'est **pas un compilateur**. Il masque commentaires et chaînes, suit les accolades et reconnaît les déclarations par expressions régulières.

- **Appels approximatifs.** Sur Roller, 92 % des appels vers le code du projet ont un receveur typé ; les autres (receveur issu d'un tableau, d'une expression, d'un champ hérité d'une bibliothèque…) sont gardés « par nom seul » et affichés à part comme « possibles ». Les appels vers le JDK et les bibliothèques sont ignorés.
- **Pas de surcharge** : `Classe#méthode` regroupe toutes les surcharges. **Pas de génériques** : `List<User>` est vu comme `List`. **Pas d'inférence de `var`**, de lambdas ni de références de méthode (`Foo::bar` n'est pas un appel).
- **Polymorphisme par nom** : `who-calls` élargit aux méthodes de même nom des interfaces, classes mères et implémentations. Un appel via l'interface est donc attribué à toutes les implémentations, même si une seule s'exécute.
- **Classes de même nom simple** (Roller a deux `RuntimeConfigProperty`) : résolues par les imports et le paquetage ; sinon l'appel reste « par nom seul ».
- **Rien de dynamique** : réflexion, `Class.forName` sur une valeur lue en configuration, injection Spring par annotations, réécriture d'URL faite dans un filtre (le cas de Roller, voir S04 dans DEMO.md), JPQL des requêtes nommées. Les noms de classes cités dans les `.properties` sont reliés, mais le graphe ne sait pas si le code les charge.
- **Routes** : correspondance d'URL selon la spécification servlet (exact, préfixe le plus long, extension, défaut) ; pas de `ServletContainerInitializer`, ni d'ordre entre `web-fragment`, ni de routes Spring MVC déclarées en XML. Les `web.xml` et `struts.xml` des dossiers de test sont ignorés.
- **Tables** : seules celles qui ont un `CREATE TABLE` lisible ou une entité. Les templates (`createdb.vm`) ne sont pas évalués.
- **JSP** : seules les classes citées par leur nom complet (imports `<%@ page import %>`) sont reliées ; les balises Struts (`<s:form action="…">`) ne le sont pas.
