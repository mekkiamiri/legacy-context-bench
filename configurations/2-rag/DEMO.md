# Démonstration réelle : index BM25 sur Apache Roller

Sorties copiées telles quelles (22/11/2026, Roller au commit `52e064a`, MacBook Apple M4 Pro, Python 3.15, aucune dépendance).
Pour les reproduire : cloner Roller dans `/tmp/roller` (voir le README du banc), puis lancer les commandes depuis la racine du banc.

## Construction de l'index : 2,3 s, 1,5 Mo

Mesuré 4 fois : 2,3 à 3,0 s (la première fois, cache disque froid). Aucun token consommé : pas d'embedding, pas d'appel réseau.

```
$ python3 configurations/2-rag/rag_index.py /tmp/roller .contexte/rag-index.json.gz
1146 fichiers, 10073 morceaux, 40451 termes
construit en 2.3 s, 1.5 Mo -> .contexte/rag-index.json.gz
```

## D05 : « Où sont rangés les réglages modifiables à chaud, et où sont leurs valeurs par défaut ? »

L'agent seul a raté cette question 3 fois sur 3 : il trouve `runtimeConfigDefs.xml` mais ne nomme jamais la table `roller_properties`.

### 1. La question telle quelle, en français : l'index ne trouve rien d'utile

Un index lexical cherche des mots, pas un sens. Les mots français de la question ne sont pas dans le code anglais ; pire, « rangés » devient `range` et ramène des méthodes sur les plages de dates.

```
$ python3 configurations/2-rag/rag_search.py "Où sont rangés les réglages modifiables à chaud par l'administrateur, et où sont leurs valeurs par défaut ?" --k 5 --lignes 3
1. app/src/main/resources/ApplicationResources_fr.properties:1001-1014  [bloc]  score 13.9  (defaut)
    1001 | # --- Default comments settings
    1003 | websiteSettings.defaultCommentSettings=Paramètres par défaut pour les commentaires
    1004 | websiteSettings.defaultAllowComments=Par défaut, autoriser les commentaires pour les nouvelles publications
2. app/src/main/java/org/apache/roller/weblogger/business/FileContentManagerImpl.java:363-380  [méthode FileContentManagerImpl.matchContentType]  score 10.9  (range)
     364 |      * Super simple contentType range rule matching
     366 |     private boolean matchContentType(String rangeRule, String contentType) {
     367 |         if (rangeRule.equals("*/*")) {
3. app/src/main/java/org/apache/roller/util/DateUtil.java:317-323  [méthode DateUtil.isValidDateRange]  score 10.9  (range)
     321 |     public static boolean isValidDateRange(Date startDate, Date endDate) {
     322 |         return isValidDateRange(startDate, endDate, true);
4. app/src/main/java/org/apache/roller/weblogger/webservices/atomprotocol/RollerAtomService.java:176-195  [méthode RollerAtomService.getAcceptedContentTypeRange]  score 10.0  (range)
     177 |      * Build accept range by taking things that appear to be content-type rules
     180 |     private List<String> getAcceptedContentTypeRange() throws WebloggerException {
5. app/src/main/java/org/apache/roller/util/DateUtil.java:326-346  [méthode DateUtil.isValidDateRange]  score 9.6  (range)
     331 |     public static boolean isValidDateRange(Date startDate, Date endDate, boolean equalOK) {
```

### 2. Reformulée avec des mots du code (ce que l'agent est invité à faire) : trouvé

`runtimeConfigDefs.xml` sort au rang 2, et **`roller_properties` apparaît dans deux extraits** (ligne 28 de `runtimeConfigDefs.xml`, ligne 203 de `JPAPropertiesManagerImpl`). Les deux critères de D05 sont sous les yeux de l'agent dès le premier appel.

```
$ python3 configurations/2-rag/rag_search.py "runtime properties stored database table default value" --k 5
1. app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAPropertiesManagerImpl.java:68-90  [méthode JPAPropertiesManagerImpl.initialize]  score 22.4  (runtime, property, database, table, default)
      72 |     public void initialize() throws InitializationException {
      74 |         Map<String, RuntimeConfigProperty> props;
      76 |             // retrieve properties from database
      77 |             props = this.getProperties();
      79 |             // if any default props missing from the properties DB table,
      85 |             log.fatal("Failed to initialize runtime configuration properties."+
2. app/src/main/resources/org/apache/roller/weblogger/config/runtimeConfigDefs.xml:1-39  [bloc]  score 21.7  (runtime, property, stored, database, table, default)
       1 | <?xml version="1.0" encoding="ISO-8859-1" ?>
      22 |   Users of Roller should never need to edit this file.  The properties
      25 |   This file defines what properties are made available to get/set
      28 |   These runtime properties are stored in the database (roller_properties
      29 |   table) and the code *must* be able to make use of changed values during
      33 |   of property we are dealing with, its default value, and information
3. app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAPropertiesManagerImpl.java:165-211  [méthode JPAPropertiesManagerImpl.initializeMissingProps]  score 21.4  (runtime, property, database, table, default, value)
     166 |      * This method compares the property definitions in the RuntimeConfigDefs
     172 |     private Map<String, RuntimeConfigProperty> initializeMissingProps(Map<String, RuntimeConfigProperty> props) {
     196 |                         RuntimeConfigProperty newprop =
     197 |                                 new RuntimeConfigProperty(
     198 |                                         propDef.getName(), propDef.getDefaultValue());
     203 |                             " not yet in roller_properties database table, will store with " +
4. app/src/main/resources/org/apache/roller/planet/config/planetRuntimeConfigDefs.xml:1-37  [bloc]  score 18.6  (runtime, property, stored, database, default, value)
       1 | <?xml version="1.0" encoding="ISO-8859-1" ?>
      22 |   Users of Roller should never need to edit this file.  The properties listed
      25 |   This file defines what properties are made available to get/set
      27 |   are stored in the database and the code *must* be able to make
      28 |   use of changed values during runtime.
      31 |   of property we are dealing with, it's default value, and information
5. docs/roller-install-guide.adoc:672-695  [bloc]  score 18.5  (runtime, property, stored, database, default)
     672 | == Review optional features
     679 | These are the defaults for a new Roller 7 installation. Upgraded sites retain
     680 | their saved runtime settings, and local configuration can override startup
     681 | defaults. The features most sites want come first; the later ones serve
     687 | settings in the web interface and clicks *Save*. They are stored in the database
     694 | _roller.properties_ or _runtimeConfigDefs.xml_ files.
```

## C06 : « Avec deux serveurs en cluster, comment évite-t-on qu'une tâche planifiée tourne deux fois ? »

Avec des mots du code, la réponse (un bail en base, `TaskLock`, `JPAThreadManagerImpl.registerLease`, preuve ligne 73) est dans les 5 premiers résultats.

```
$ python3 configurations/2-rag/rag_search.py "task lock lease cluster scheduled" --k 5
1. app/src/main/resources/org/apache/roller/weblogger/config/roller.properties:233-244  [bloc]  score 32.8  (task, lease, cluster, scheduled)
     233 | # Tasks which are enabled.  Only tasks listed here will be run.
     234 | tasks.enabled=ScheduledEntriesTask,ResetHitCountsTask
     240 | tasks.ScheduledEntriesTask.class=org.apache.roller.weblogger.business.runnable.ScheduledEntriesTask
     241 | tasks.ScheduledEntriesTask.startTime=immediate
     242 | tasks.ScheduledEntriesTask.interval=1
     243 | tasks.ScheduledEntriesTask.leaseTime=30
2. app/src/main/java/org/apache/roller/weblogger/business/runnable/ScheduledEntriesTask.java:80-83  [méthode ScheduledEntriesTask.getLeaseTime]  score 27.8  (task, lease, scheduled)
      81 |     public int getLeaseTime() {
      82 |         return this.leaseTime;
3. app/src/test/java/org/apache/roller/weblogger/business/TaskLockTest.java:50-81  [méthode TaskLockTest.testTaskLockCRUD]  score 27.8  (task, lock, lease)
      55 |     public void testTaskLockCRUD() throws Exception {
      59 |         // need a test task to play with
      64 |         assertTrue(mgr.registerLease(task), "Failed to acquire lease.");
      69 |         assertFalse(mgr.registerLease(task),"Acquired lease a second time when we shouldn't have been able to.");
      73 |         assertTrue(mgr.unregisterLease(task), "Release of lease failed.");
      79 |         assertTrue( mgr.unregisterLease(task), "Second release failed.");
4. app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAThreadManagerImpl.java:137-186  [méthode JPAThreadManagerImpl.unregisterLease]  score 27.8  (task, lock, lease)
     138 |      * Try to release the lock for a given RollerTask.
     141 |     public boolean unregisterLease(RollerTask task) {
     144 |         TaskLock taskLock;
     146 |             taskLock = this.getTaskLockByName(task.getName());
     148 |             if(taskLock == null) {
     154 |                 LOG.debug("Error getting TaskLock", ex);
5. app/src/main/java/org/apache/roller/weblogger/business/jpa/JPAThreadManagerImpl.java:59-134  [méthode JPAThreadManagerImpl.registerLease]  score 27.5  (task, lock, lease)
      60 |      * Try to aquire a lock for a given RollerTask.
      63 |     public boolean registerLease(RollerTask task) {
      65 |         LOG.debug("Attempting to register lease for task - " + task.getName());
      71 |         TaskLock taskLock;
      73 |             taskLock = getTaskLockByName(task.getName());
      86 |                 Date leaseExpiration = taskLock.getLeaseExpiration();
```

La même question en français : seul le mot « cluster » accroche, la réponse n'est pas dans les 3 premiers.

```
$ python3 configurations/2-rag/rag_search.py "Avec deux serveurs Roller en cluster, comment évite-t-on qu'une tâche planifiée tourne deux fois ?" --k 3 --lignes 2
1. skills/roller-security/assets/SUMMARY.md:56-73  [bloc]  score 12.8  (roller, cluster)
      56 | ## Provenance
      61 | - Dashboard: <https://dash.security.apache.org/project/roller>
2. app/src/main/java/org/apache/roller/weblogger/business/runnable/RollerTask.java:58-65  [méthode RollerTask.getClientId]  score 10.0  (roller, cluster)
      59 |      * Get the unique id representing a specific instance of a task.  This is
      61 |      * lease can be associated with a single cluster member.
3. app/src/main/resources/ApplicationResources_fr.properties:342-358  [bloc]  score 9.6  (serveur)
     342 | #FIXME: add more verbiage to 404 text
     343 | error.text.404=Le document que vous recherchez est introuvable sur ce serveur.
```

## C01 : « Comment Roller construit-il l'ancre d'un nouveau billet ? »

Le découpage par méthode paie : chaque résultat est une méthode entière (`createAnchor` ; `createAnchorBase`, qui fait le travail, arrive juste après, au rang 5 avec `--k 5`), pas un bloc de lignes coupé au milieu.

```
$ python3 configurations/2-rag/rag_search.py "anchor title entry create unique" --k 4
1. app/src/main/java/org/apache/roller/weblogger/business/WeblogEntryManager.java:268-271  [méthode WeblogEntryManager.createAnchor]  score 21.7  (anchor, entry, create, unique)
     269 |      * Create unique anchor for weblog entry.
     271 |     String createAnchor(WeblogEntry data) throws WebloggerException;
2. app/src/main/java/org/apache/roller/weblogger/pojos/WeblogEntry.java:800-803  [méthode WeblogEntry.createAnchor]  score 19.0  (anchor, title, entry, create)
     800 |     /** Create anchor for weblog entry, based on title or text */
     801 |     protected String createAnchor() throws WebloggerException {
     802 |         return WebloggerFactory.getWeblogger().getWeblogEntryManager().createAnchor(this);
3. app/src/test/java/org/apache/roller/weblogger/business/WeblogEntryTest.java:316-347  [méthode WeblogEntryTest.testCreateAnchor]  score 18.2  (anchor, entry, create, unique)
     317 |      * Test that the createAnchor() method actually ensures unique anchors.
     320 |     public void testCreateAnchor() throws Exception {
     330 |         // make sure createAnchor gives us a new anchor value
     332 |         String anchor = mgr.createAnchor(entry1);
     334 |         assertNotSame("entry1", anchor);
     336 |         // make sure we can create a new entry with specified anchor
4. app/src/main/resources/org/apache/roller/weblogger/pojos/WeblogEntryComment.orm.xml:73-122  [bloc]  score 17.6  (anchor, title, entry, unique)
      73 |         </named-query>
      74 |         <named-query name="WeblogEntryComment.getMostCommentedWeblogEntryByWebsite&amp;EndDate&amp;StartDate">
      79 |             <query>SELECT COUNT(c), c.weblogEntry.website.handle, c.weblogEntry.anchor, c.weblogEntry.title FROM WeblogEntryComment c WHERE c.weblogEntry.websit
      86 |                 <column name="name" insertable="true" updatable="true" unique="false"/>
      89 |                 <column name="email" insertable="true" updatable="true" unique="false"/>
      92 |                 <column name="url" insertable="true" updatable="true" unique="false"/>
```

## Ce que ça montre pour le talk

- **Le RAG lexical marche si on lui parle comme au code.** La même question échoue en français et réussit avec 6 mots anglais. Un agent qui reformule sa requête s'en sert bien ; une question d'utilisateur collée telle quelle, non.
- **Il ramène la documentation avec le code** : commentaires XML, guide d'installation. C'est ce qui donne `roller_properties` pour D05.
- **Il ne suit pas d'enchaînement** : il donne des morceaux, pas le chemin d'un appel à l'autre (voir le graphe, configuration 3).
