# Démonstration réelle : graphe du code d'Apache Roller

Sorties copiées telles quelles (22/11/2026, Roller au commit `52e064a`, MacBook Apple M4 Pro, Python 3.15, aucune dépendance).
Pour les reproduire : cloner Roller dans `/tmp/roller` (voir le README du banc), puis lancer les commandes depuis la racine du banc.

## Construction du graphe : 1,0 s, 7,2 Mo

Mesuré 4 fois : 1,0 à 1,1 s. Aucun token consommé. 92 % des appels ont un receveur typé ; les 8 % restants sont gardés « par nom seul » et signalés comme incertains.

```
$ python3 configurations/3-graphe/graph_build.py /tmp/roller .contexte/graphe.json
783 types, 6250 méthodes, 20860 appels (19237 typés, 1623 par nom seul), 76 routes, 26 entités, 31 tables, 241 références de configuration
construit en 1.0 s, 7.2 Mo -> .contexte/graphe.json
```

## D05 : « Où sont rangés les réglages modifiables à chaud, et où sont leurs valeurs par défaut ? »

Ratée 3 fois sur 3 par l'agent seul. Le graphe répond **si l'agent connaît un nom de départ**. Avec un mot du code, `find` donne la table :

```
$ python3 configurations/3-graphe/graph_query.py find properties --max 4
Classes (4) :
  org.apache.roller.weblogger.business.PropertiesManager  app/src/main/java/org/apache/roller/weblogger/business/PropertiesManager.java:29
  org.apache.roller.weblogger.business.jpa.JPAPropertiesManagerImpl  app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAPropertiesManagerImpl.java:48
  org.apache.roller.planet.business.PropertiesTest  app/src/test/java/org/apache/roller/planet/business/PropertiesTest.java:39
  org.apache.roller.weblogger.business.PropertiesTest  app/src/test/java/org/apache/roller/weblogger/business/PropertiesTest.java:40
Méthodes (23) :
  Planet.getPropertiesManager  app/src/main/java/org/apache/roller/planet/business/Planet.java:37
  JPAPlanetImpl.getPropertiesManager  app/src/main/java/org/apache/roller/planet/business/jpa/JPAPlanetImpl.java:123
  PropertyExpander.expandProperties  app/src/main/java/org/apache/roller/util/PropertyExpander.java:59
  PropertyExpander.expandSystemProperties  app/src/main/java/org/apache/roller/util/PropertyExpander.java:93
  ... 19 de plus
Tables (2) :
  rag_properties  app/src/main/resources/sql/310-to-400-migration.vm:24
  roller_properties  app/src/main/resources/sql/createdb.vm:256
Entités (2) :
  org.apache.roller.planet.pojos.RuntimeConfigProperty -> rag_properties
  org.apache.roller.weblogger.pojos.RuntimeConfigProperty -> roller_properties
Configuration (1) :
  app/src/test/resources/log4j2.xml:67  <Logger name="org.apache.roller.weblogger.business.jpa.JPAPropertiesManagerImpl" -> JPAPropertiesManagerImpl  (EN COMMENTAIRE, inactive)
Ressources chargées (21) :
  WebloggerImpl charge /roller-version.properties  app/src/main/java/org/apache/roller/weblogger/business/WebloggerImpl.java:108
  JPAMediaFileManagerImpl charge migration-status.properties  app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAMediaFileManagerImpl.java:73
  SmileysPlugin charge smileys.properties  app/src/main/java/org/apache/roller/weblogger/business/plugins/entry/SmileysPlugin.java:62
  DatabaseInstaller charge /roller-version.properties  app/src/main/java/org/apache/roller/weblogger/business/startup/DatabaseInstaller.java:61
  ... 17 de plus
```

Puis `table` donne la réponse complète en une commande : l'entité, le mapping XML (pas d'annotation), le `CREATE TABLE`, le SQL écrit à la main, et le fichier de valeurs par défaut chargé par la classe qui lit ces réglages (`runtimeConfigDefs.xml`). **Les deux critères de D05 sont trouvés.**

```
$ python3 configurations/3-graphe/graph_query.py table roller_properties --max 8
Entité org.apache.roller.weblogger.pojos.RuntimeConfigProperty -> table roller_properties  (orm.xml, app/src/main/resources/org/apache/roller/weblogger/pojos/RuntimeConfigProperty.orm.xml:25)
  unité de persistance « RollerPU »  app/src/main/resources/META-INF/persistence.xml:23

CREATE TABLE roller_properties  app/src/main/resources/sql/createdb.vm:256
     256 | create table roller_properties (
     257 |     name     varchar(255) not null primary key,
     258 |     value    $db.TEXT_SQL_TYPE
     259 | );

SQL écrit à la main citant roller_properties (3 classes) :
  JPAPropertiesManagerImpl  app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAPropertiesManagerImpl.java:203
  DatabaseInstaller  app/src/main/java/org/apache/roller/weblogger/business/startup/DatabaseInstaller.java:600  (+8 autres lignes)
  DatabaseInstallerUpgradeTest  app/src/test/java/org/apache/roller/weblogger/business/startup/DatabaseInstallerUpgradeTest.java:59  (+7 autres lignes)

Classes qui utilisent RuntimeConfigProperty (22) : BootstrapSecurity, FrontpageSettings, GlobalConfig, JPAPropertiesManagerImpl, PlanetConfig, PlanetRuntimeConfig, PropertiesManager, Register ...
Fichiers de configuration chargés par ces classes :
  PlanetRuntimeConfig charge /org/apache/roller/planet/config/planetRuntimeConfigDefs.xml  (app/src/main/java/org/apache/roller/planet/config/PlanetRuntimeConfig.java:43)
  WebloggerRuntimeConfig charge /org/apache/roller/weblogger/config/runtimeConfigDefs.xml  (app/src/main/java/org/apache/roller/weblogger/config/WebloggerRuntimeConfig.java:46)
```

## H01 : « Dans quel ordre les filtres servlet s'appliquent-ils à GET /monblog/ ? »

Réponse exacte, avec les numéros de ligne de `web.xml` : les 8 filtres, dans l'ordre, sans IPBanFilter (FORWARD seulement), sans les filtres de sel (`/roller-ui/*`) ni struts2 (`*.rol`).

```
$ python3 configurations/3-graphe/graph_query.py route /monblog/
/monblog/  (dispatcher REQUEST)

Filtres appliqués, dans l'ordre de déclaration (8) :
   1. CharEncodingFilter  org.apache.roller.weblogger.ui.core.filters.CharEncodingFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:117
   2. BootstrapSecurityFilter  org.apache.roller.weblogger.ui.core.filters.BootstrapSecurityFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:134
   3. SpringFirewallExceptionFilter  org.apache.roller.weblogger.ui.core.filters.SpringFirewallExceptionFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:145
   4. securityFilter  org.springframework.web.filter.DelegatingFilterProxy  [/*]  app/src/main/webapp/WEB-INF/web.xml:153
   5. BootstrapFilter  org.apache.roller.weblogger.ui.core.filters.BootstrapFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:160
   6. PersistenceSessionFilter  org.apache.roller.weblogger.ui.core.filters.PersistenceSessionFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:168
   7. InitFilter  org.apache.roller.weblogger.ui.core.filters.InitFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:175
   8. RequestMappingFilter  org.apache.roller.weblogger.ui.rendering.filters.RequestMappingFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:202

Aucune servlet, action ni contrôleur déclaré pour ce chemin.
Si l'URL est traitée quand même, la réécriture est faite par du code (souvent un filtre ci-dessus) : le graphe ne la voit pas. Regarder les filtres sur /*.
```

## C06 : « Avec deux serveurs en cluster, comment évite-t-on qu'une tâche planifiée tourne deux fois ? »

`who-calls` passe par l'interface : on demande `ThreadManager.registerLease`, on obtient les deux implémentations et l'appelant réel, `RollerTaskWithLeasing.run`. `neighbors` relie le verrou à sa table.

```
$ python3 configurations/3-graphe/graph_query.py who-calls ThreadManager.registerLease
Cibles (3, interfaces et implémentations comprises) :
  ThreadManager.registerLease (abstraite)  app/src/main/java/org/apache/roller/weblogger/business/runnable/ThreadManager.java:77
  JPAThreadManagerImpl.registerLease  app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAThreadManagerImpl.java:63
  ThreadManagerImpl.registerLease  app/src/main/java/org/apache/roller/weblogger/business/runnable/ThreadManagerImpl.java:186

Appelants sûrs (receveur typé) : 3
  RollerTaskWithLeasing.run  app/src/main/java/org/apache/roller/weblogger/business/runnable/RollerTaskWithLeasing.java:60  -> ThreadManager.registerLease
  TaskLockTest.testTaskLockCRUD  app/src/test/java/org/apache/roller/weblogger/business/TaskLockTest.java:64  -> ThreadManager.registerLease
  TaskLockTest.testTaskLockCRUD  app/src/test/java/org/apache/roller/weblogger/business/TaskLockTest.java:69  -> ThreadManager.registerLease
```

```
$ python3 configurations/3-graphe/graph_query.py neighbors TaskLock
class org.apache.roller.weblogger.pojos.TaskLock  app/src/main/java/org/apache/roller/weblogger/pojos/TaskLock.java:30-172
  implémente : Serializable
  utilise (1) : UUIDGenerator
  utilisée par (4) : JPAThreadManagerImpl, TaskScheduler, ThreadManager, ThreadManagerImpl
  appelée depuis (3 classes) : JPAThreadManagerImpl (5), ThreadManagerImpl (5), TaskScheduler (1)
  citée en configuration : app/src/main/resources/org/apache/roller/weblogger/pojos/TaskLock.orm.xml:23  <entity metadata-complete="true" name="TaskLock" class="org.apache.roller.weblog
  entité -> table roller_tasklock  (orm.xml, app/src/main/resources/org/apache/roller/weblogger/pojos/TaskLock.orm.xml:25)

```

## H04 : « Combien de validateurs de commentaires existent, et combien sont activés par défaut ? »

Les 5 implémentations viennent de l'héritage ; les 3 activées, des références de configuration, avec la ligne commentée d'Akismet repérée comme inactive.

```
$ python3 configurations/3-graphe/graph_query.py neighbors CommentValidator
interface org.apache.roller.weblogger.ui.rendering.plugins.comments.CommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/CommentValidator.java:25-38
  sous-types directs : AkismetCommentValidator, BannedwordslistCommentValidator, ExcessLinksCommentValidator, ExcessSizeCommentValidator, TrackbackLinkbackCommentValidator
  utilise (2) : WeblogEntryComment, RollerMessages
  utilisée par (6) : AkismetCommentValidator, BannedwordslistCommentValidator, CommentValidationManager, ExcessLinksCommentValidator, ExcessSizeCommentValidator, TrackbackLinkbackCommentValidator
  appelée depuis (1 classes) : CommentValidationManager (2)

```

```
$ python3 configurations/3-graphe/graph_query.py find validator --max 5
Classes (9) :
  org.apache.roller.weblogger.ui.core.filters.SaltValidator  app/src/main/java/org/apache/roller/weblogger/ui/core/filters/SaltValidator.java:35
  org.apache.roller.weblogger.ui.rendering.plugins.comments.AkismetCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/AkismetCommentValidator.java:42
  org.apache.roller.weblogger.ui.rendering.plugins.comments.BannedwordslistCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/BannedwordslistCommentValidator.java:31
  org.apache.roller.weblogger.ui.rendering.plugins.comments.CommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/CommentValidator.java:25
  org.apache.roller.weblogger.ui.rendering.plugins.comments.ExcessLinksCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/ExcessLinksCommentValidator.java:33
  ... 4 de plus
Méthodes (9) :
  SaltValidator.SaltValidator  app/src/main/java/org/apache/roller/weblogger/ui/core/filters/SaltValidator.java:42
  AkismetCommentValidator.AkismetCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/AkismetCommentValidator.java:48
  CommentValidationManager.addCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/CommentValidationManager.java:55
  ExcessLinksCommentValidator.ExcessLinksCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/ExcessLinksCommentValidator.java:38
  ExcessSizeCommentValidator.ExcessSizeCommentValidator  app/src/main/java/org/apache/roller/weblogger/ui/rendering/plugins/comments/ExcessSizeCommentValidator.java:35
  ... 4 de plus
Configuration (4) :
  app/src/main/resources/org/apache/roller/weblogger/config/roller.properties:185  comment.validator.classnames -> BannedwordslistCommentValidator
  app/src/main/resources/org/apache/roller/weblogger/config/roller.properties:186  comment.validator.classnames -> ExcessLinksCommentValidator
  app/src/main/resources/org/apache/roller/weblogger/config/roller.properties:187  comment.validator.classnames -> ExcessSizeCommentValidator
  app/src/main/resources/org/apache/roller/weblogger/config/roller.properties:188  #org.apache.roller.weblogger.ui.rendering.plugins.comments.AkismetCommentValidat -> AkismetCommentValidator  (EN COMMENTAIRE, inactive)
```

## Une limite, montrée telle quelle : S04, l'URL publique d'un billet

Le graphe voit tout ce qui est déclaré (web.xml, struts.xml, annotations) mais pas ce que le code décide à l'exécution. Pour `/monblog/entry/mon-billet`, la réécriture vers `PageServlet` est faite par `RequestMappingFilter` et `WeblogRequestMapper`, en Java : le graphe le dit au lieu d'inventer une route.

```
$ python3 configurations/3-graphe/graph_query.py route /monblog/entry/mon-billet
/monblog/entry/mon-billet  (dispatcher REQUEST)

Filtres appliqués, dans l'ordre de déclaration (8) :
   1. CharEncodingFilter  org.apache.roller.weblogger.ui.core.filters.CharEncodingFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:117
   2. BootstrapSecurityFilter  org.apache.roller.weblogger.ui.core.filters.BootstrapSecurityFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:134
   3. SpringFirewallExceptionFilter  org.apache.roller.weblogger.ui.core.filters.SpringFirewallExceptionFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:145
   4. securityFilter  org.springframework.web.filter.DelegatingFilterProxy  [/*]  app/src/main/webapp/WEB-INF/web.xml:153
   5. BootstrapFilter  org.apache.roller.weblogger.ui.core.filters.BootstrapFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:160
   6. PersistenceSessionFilter  org.apache.roller.weblogger.ui.core.filters.PersistenceSessionFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:168
   7. InitFilter  org.apache.roller.weblogger.ui.core.filters.InitFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:175
   8. RequestMappingFilter  org.apache.roller.weblogger.ui.rendering.filters.RequestMappingFilter  [/*]  app/src/main/webapp/WEB-INF/web.xml:202

Aucune servlet, action ni contrôleur déclaré pour ce chemin.
Si l'URL est traitée quand même, la réécriture est faite par du code (souvent un filtre ci-dessus) : le graphe ne la voit pas. Regarder les filtres sur /*.
```

## Ce que ça montre pour le talk

- **Le graphe excelle sur ce qui est déclaré** : ordre des filtres, actions Struts, mapping entité -> table, classes citées dans les `.properties` (y compris en commentaire).
- **Il faut un nom pour entrer** : le graphe ne comprend pas une question, il répond à `table roller_properties`. Le RAG trouve le nom, le graphe donne la structure autour.
- **Il est aveugle à l'exécution** : réécriture d'URL dans du code, valeurs lues en base, ordre réel des appels (configuration 4).
