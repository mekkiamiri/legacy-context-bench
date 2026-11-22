"""Construit le graphe du code d'un projet Java legacy (bibliothèque standard seulement).

Usage :
    python3 configurations/3-graphe/graph_build.py <projet> <sortie.json>

Nœuds : classes (et interfaces, enums), méthodes, tables, URL, beans.
Arêtes : hérite / implémente, appelle (approximatif), utilise (types référencés),
route (URL -> servlet / filtre / action), mappe (entité -> table), SQL dans une chaîne
(classe -> table), référence de configuration (XML / properties -> classe), ressource
(classe -> fichier chargé par son chemin, ex. "/.../defs.xml").
Les limites de l'analyse sont dans README.md (même dossier).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "commun"))
import javalite  # noqa: E402
from javalite import enfants, texte_de, tous  # noqa: E402

CONFIG_EXT = {".xml", ".properties", ".jsp", ".jspf", ".tld", ".vm", ".ftl", ".yml", ".yaml", ".tag"}
SQL_EXT = {".sql", ".ddl", ".vm", ".ftl", ".xml"}
TYPES_EXTERNES_COURANTS = {"String", "Object", "Integer", "Long", "Boolean", "List", "Map", "Set", "Collection",
                           "Date", "Iterator", "StringBuilder", "StringBuffer", "Exception", "Math", "System",
                           "Arrays", "Collections", "Optional", "Thread", "Class", "Character", "Double", "Float"}
_CREATE = re.compile(r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?([A-Za-z_][\w$.]*)", re.I)
_LIQUIBASE = re.compile(r"<createTable\b[^>]*\btableName=\"([\w$.]+)\"")
_SQL_MOT = re.compile(r"\b(select|insert|update|delete|from|into|join|table|where|alter)\b", re.I)
_FQCN = re.compile(r"\b[a-z][\w]*(?:\.[\w$]+){2,}\b")
_ROUTES_ANNOT = {
    "RequestMapping": ("value", "path"), "GetMapping": ("value", "path"), "PostMapping": ("value", "path"),
    "PutMapping": ("value", "path"), "DeleteMapping": ("value", "path"), "PatchMapping": ("value", "path"),
    "Path": ("value",), "WebServlet": ("urlPatterns", "value"), "WebFilter": ("urlPatterns", "value"),
}


class Projet:
    def __init__(self, racine: Path):
        self.racine = Path(racine).resolve()
        self.fichiers_java: dict[str, dict] = {}
        self.classes: dict[str, dict] = {}
        self.par_nom: dict[str, list[str]] = {}
        self.contextes: dict[str, dict] = {}

    def rel(self, p: Path) -> str:
        return p.relative_to(self.racine).as_posix()

    # -- résolution de noms ------------------------------------------------------------------
    def resoudre(self, simple: str, ctx: dict) -> str | None:
        """Nom simple -> nom complet d'une classe du projet, ou None (externe ou ambigu)."""
        if not simple:
            return None
        if "." in simple:
            return simple if simple in self.classes else self.resoudre(simple.split(".")[-1], ctx)
        candidats = self.par_nom.get(simple)
        if not candidats:
            return None
        for t in ctx["types"]:
            if t["nom"] == simple:
                return t["nom_complet"]
        for imp in ctx["imports"]:
            if imp.endswith("." + simple) and imp in self.classes:
                return imp
        if ctx["paquet"] + "." + simple in self.classes:
            return ctx["paquet"] + "." + simple
        for imp in ctx["imports"]:
            if imp.endswith(".*") and imp[:-2] + "." + simple in self.classes:
                return imp[:-2] + "." + simple
        if any(imp.endswith("." + simple) for imp in ctx["imports"]):
            return None  # importé depuis une bibliothèque
        return candidats[0] if len(candidats) == 1 else None

    def ancetres(self, fqcn: str) -> list[str]:
        vus, file = [], [fqcn]
        while file:
            c = file.pop(0)
            if c in vus or c not in self.classes:
                continue
            vus.append(c)
            info = self.classes[c]
            file += [x for x in info["etend"] + info["implemente"] if x in self.classes]
        return vus

    def declarant(self, fqcn: str, nom: str) -> str | None:
        for c in self.ancetres(fqcn):
            if nom in self.classes[c]["noms_methodes"]:
                return c
        return None


def construire(racine: Path) -> dict:
    pr = Projet(racine)
    # 1. Analyse des sources Java.
    for p in javalite.fichiers(pr.racine, {".java"}):
        try:
            a = javalite.analyser(javalite.lire(p))
        except Exception as e:  # noqa: BLE001 - analyse légère, on n'arrête pas tout pour un fichier
            print(f"analyse impossible : {pr.rel(p)} ({e})", file=sys.stderr)
            continue
        rel = pr.rel(p)
        pr.fichiers_java[rel] = a
        pr.contextes[rel] = {"types": a["types"], "imports": a["imports"], "paquet": a["paquet"]}
        for t in a["types"]:
            pr.classes[t["nom_complet"]] = {
                "nom": t["nom"], "genre": t["genre"], "fichier": rel, "lignes": [t["ligne_debut"], t["ligne_fin"]],
                "etend_s": t["etend"], "implemente_s": t["implemente"], "externe": t["externe"],
                "annotations": [x["nom"] for x in t["annotations"]],
                "noms_methodes": {m["nom"]: m["retour"] for m in t["methodes"]},
            }
            pr.par_nom.setdefault(t["nom"], []).append(t["nom_complet"])

    # 2. Héritage résolu.
    for rel, a in pr.fichiers_java.items():
        for t in a["types"]:
            c = pr.classes[t["nom_complet"]]
            c["etend"] = [pr.resoudre(x, a) or x for x in c.pop("etend_s")]
            c["implemente"] = [pr.resoudre(x, a) or x for x in c.pop("implemente_s")]

    # 3. Méthodes, appels, usages, ressources, routes et entités par annotations.
    methodes: dict[str, list[dict]] = {}
    appels, utilise, routes, entites, ressources, chaines_java = [], {}, [], [], [], []
    for rel, a in pr.fichiers_java.items():
        types_par_nom = {t["nom_complet"]: t for t in a["types"]}
        for t in a["types"]:
            fq = t["nom_complet"]
            champs = {}
            externe = t["externe"]
            while externe and externe in types_par_nom:
                champs = {**types_par_nom[externe]["champs"], **champs}
                externe = types_par_nom[externe]["externe"]
            champs.update(t["champs"])
            prefixes = [""]
            for an in t["annotations"]:
                if an["nom"] in _ROUTES_ANNOT:
                    vals = javalite.valeurs_annotation(an["args"], *_ROUTES_ANNOT[an["nom"]])
                    if an["nom"] in ("WebServlet", "WebFilter"):
                        for v in vals:
                            routes.append({"url": v, "genre": "servlet" if an["nom"] == "WebServlet" else "filtre",
                                           "cible": fq, "nom": t["nom"], "fichier": rel, "ligne": t["ligne_debut"],
                                           "source": "@" + an["nom"]})
                    else:
                        prefixes = vals or [""]
                if an["nom"] == "Entity":
                    table = next((javalite.valeurs_annotation(x["args"], "name") for x in t["annotations"] if x["nom"] == "Table"), [])
                    entites.append({"classe": fq, "table": table[0] if table else t["nom"], "fichier": rel,
                                    "ligne": t["ligne_debut"], "source": "@Table" if table else "@Entity (nom par défaut)"})
            for m in t["methodes"]:
                mid = f"{fq}#{m['nom']}"
                methodes.setdefault(mid, []).append({"fichier": rel, "ligne": m["ligne_sig"], "fin": m["ligne_fin"],
                                                     "params": m["params"], "abstraite": m["abstraite"]})
                for an in m["annotations"]:
                    if an["nom"] in _ROUTES_ANNOT and an["nom"] not in ("WebServlet", "WebFilter"):
                        for v in javalite.valeurs_annotation(an["args"], *_ROUTES_ANNOT[an["nom"]]) or [""]:
                            for pre in prefixes:
                                routes.append({"url": "/" + (pre.strip("/") + "/" + v.strip("/")).strip("/"),
                                               "genre": "annotation", "cible": fq, "methode": m["nom"], "nom": t["nom"],
                                               "fichier": rel, "ligne": m["ligne_sig"], "source": "@" + an["nom"]})
                variables = {**champs, **m["locales"]}
                types_par_pos = {}
                for ap in m["appels"]:
                    if ap["recepteur"] == "?" and ap.get("apres") in types_par_pos:
                        if types_par_pos[ap["apres"]] is None:
                            types_par_pos[ap["pos"]] = None  # chaîne sur un objet de bibliothèque
                            continue
                        ap = {**ap, "recepteur_type": types_par_pos[ap["apres"]]}
                    cible, certitude = _cible(pr, a, fq, ap, variables)
                    if cible is None and "pos" in ap:
                        types_par_pos[ap["pos"]] = None
                    if cible and certitude == "type" and "pos" in ap:
                        c, _, n = cible.partition("#")
                        retour = pr.classes.get(c, {}).get("noms_methodes", {}).get(n)
                        if retour:
                            types_par_pos[ap["pos"]] = (retour, c)
                    if cible:
                        appels.append([mid, cible, rel, ap["ligne"], certitude])
        # usages : types du projet cités dans le fichier, attribués aux types de premier niveau
        idents = set(re.findall(r"\b[A-Z][\w$]*\b", a["masque"]))
        cites = {pr.resoudre(i, a) for i in idents} - {None}
        for t in a["types"]:
            if not t["externe"]:
                utilise[t["nom_complet"]] = sorted(cites - {x["nom_complet"] for x in a["types"]})
        haut = next((t["nom_complet"] for t in a["types"] if not t["externe"]), None)
        for ligne, s in a["chaines"]:
            if haut and re.fullmatch(r"[\w./${}-]+\.(xml|properties|vm|ftl|jsp|sql|json|ya?ml)", s.strip()):
                ressources.append([haut, s.strip(), rel, ligne])
            if haut and _SQL_MOT.search(s):
                chaines_java.append((haut, rel, ligne, s))
    del pr.fichiers_java

    # 4. Fichiers de configuration et SQL.
    tables: dict[str, list[dict]] = {}
    refs_config, beans, unites, servlets, filtres, mappings_filtres, actions = [], [], [], {}, {}, [], []
    extensions_struts = []
    fqcns = set(pr.classes)
    noms_fichiers: dict[str, list[str]] = {}
    for p in javalite.fichiers(pr.racine, CONFIG_EXT | SQL_EXT):
        rel = pr.rel(p)
        noms_fichiers.setdefault(p.name, []).append(rel)
        texte = javalite.lire(p)
        ext = p.suffix.lower()
        commentees, cles = _commentaires_et_cles(texte, ext)
        for n, l in enumerate(texte.split("\n"), 1):
            if ext in SQL_EXT:
                for m in list(_CREATE.finditer(l)) + list(_LIQUIBASE.finditer(l)):
                    tables.setdefault(m.group(1).split(".")[-1].lower(), []).append({"fichier": rel, "ligne": n})
            if ext in CONFIG_EXT:
                for m in _FQCN.finditer(l):
                    if m.group() in fqcns:
                        cle = cles.get(n) or l.strip()[:80]
                        refs_config.append([rel, n, cle, m.group(), n in commentees])
            if ext == ".properties" and l.strip().startswith("struts.action.extension"):
                extensions_struts += [e.strip() for e in l.split("=", 1)[-1].split(",")]
        if ext != ".xml":
            continue
        racine_xml = javalite.lire_xml(p)
        if racine_xml is None:
            continue
        tag = racine_xml["tag"]
        if _est_test(rel) and tag in ("web-app", "web-fragment", "struts", "struts-config", "beans"):
            continue  # web.xml / struts.xml de test : ils fausseraient les routes
        if tag in ("web-app", "web-fragment"):
            _web_xml(racine_xml, rel, servlets, filtres, mappings_filtres, routes)
        elif tag == "struts":
            for c in tous(racine_xml, "constant"):
                if c["attr"].get("name") == "struts.action.extension":
                    extensions_struts += [e.strip() for e in c["attr"].get("value", "").split(",")]
            for pk in tous(racine_xml, "package"):
                ns = pk["attr"].get("namespace", "")
                for ac in enfants(pk, "action"):
                    resultats = [r["texte"].strip() for r in enfants(ac, "result") if r["texte"].strip()][:4]
                    actions.append({"namespace": ns, "nom": ac["attr"].get("name", ""),
                                    "classe": ac["attr"].get("class", "com.opensymphony.xwork2.ActionSupport"),
                                    "methode": ac["attr"].get("method", "execute"), "resultats": resultats,
                                    "fichier": rel, "ligne": ac["ligne"], "source": "struts.xml"})
        elif tag == "struts-config":
            for ac in tous(racine_xml, "action"):
                if ac["attr"].get("path"):
                    actions.append({"namespace": "", "nom": ac["attr"]["path"].lstrip("/"),
                                    "classe": ac["attr"].get("type", ""), "methode": ac["attr"].get("parameter", "execute"),
                                    "resultats": [f["attr"].get("path", "") for f in enfants(ac, "forward")][:4],
                                    "fichier": rel, "ligne": ac["ligne"], "source": "struts-config.xml"})
        elif tag == "persistence":
            for u in tous(racine_xml, "persistence-unit"):
                unites.append({"nom": u["attr"].get("name", ""), "fournisseur": texte_de(u, "provider"),
                               "classes": [c["texte"].strip() for c in enfants(u, "class")],
                               "fichiers_mapping": [c["texte"].strip() for c in enfants(u, "mapping-file")],
                               "fichier": rel, "ligne": u["ligne"]})
        elif tag == "entity-mappings":
            paquet = texte_de(racine_xml, "package")
            for e in enfants(racine_xml, "entity"):
                classe = e["attr"].get("class", "")
                if paquet and "." not in classe:
                    classe = paquet + "." + classe
                tb = enfants(e, "table")
                nom_table = tb[0]["attr"].get("name") if tb else None
                entites.append({"classe": classe, "table": nom_table or e["attr"].get("name") or classe.split(".")[-1],
                                "fichier": rel, "ligne": (tb[0] if tb else e)["ligne"],
                                "source": "orm.xml" + ("" if nom_table else " (nom par défaut)"),
                                "metadata_complete": e["attr"].get("metadata-complete") == "true"})
        elif tag == "hibernate-mapping":
            paquet = racine_xml["attr"].get("package", "")
            for genre in ("class", "subclass", "joined-subclass", "union-subclass"):
                for e in tous(racine_xml, genre):
                    classe = e["attr"].get("name", "")
                    if paquet and "." not in classe:
                        classe = paquet + "." + classe
                    entites.append({"classe": classe, "table": e["attr"].get("table") or classe.split(".")[-1],
                                    "fichier": rel, "ligne": e["ligne"], "source": "hbm.xml"})
        elif tag == "beans":
            for b in tous(racine_xml, "bean"):
                if b["attr"].get("class"):
                    beans.append({"id": b["attr"].get("id") or b["attr"].get("name", ""), "classe": b["attr"]["class"],
                                  "fichier": rel, "ligne": b["ligne"],
                                  "refs": [x["attr"]["ref"] for x in tous(b, "property") if x["attr"].get("ref")]})

    for ac in actions:
        routes.append({"url": ("/" + ac["namespace"].strip("/") + "/" + ac["nom"]).replace("//", "/"),
                       "genre": "action", "cible": ac["classe"], "methode": ac["methode"], "nom": ac["nom"],
                       "resultats": ac["resultats"], "fichier": ac["fichier"], "ligne": ac["ligne"], "source": ac["source"]})

    sql_java = []
    for haut, rel, ligne, s in chaines_java:
        for mot in set(re.findall(r"[A-Za-z_][\w$]*", s)):
            if mot.lower() in tables:
                sql_java.append([haut, mot.lower(), rel, ligne])

    for r in ressources:
        nom = r[1].split("/")[-1]
        r.insert(2, noms_fichiers.get(nom, []))

    for c in pr.classes.values():
        c.pop("noms_methodes", None)
    return {
        "version": 1,
        "racine": str(pr.racine),
        "classes": pr.classes,
        "methodes": methodes,
        "appels": appels,
        "utilise": utilise,
        "routes": routes,
        "ordre_filtres": mappings_filtres,
        "servlets": servlets,
        "filtres": filtres,
        "extensions_struts": sorted(set(e for e in extensions_struts if e is not None)),
        "entites": entites,
        "tables": tables,
        "sql_java": sql_java,
        "unites_persistance": unites,
        "refs_config": refs_config,
        "ressources": ressources,
        "beans": beans,
    }


def _commentaires_et_cles(texte: str, ext: str) -> tuple[set[int], dict[int, str]]:
    """Lignes en commentaire (#, <!-- -->, <%-- --%>) et, pour un .properties, clé de chaque ligne
    (y compris les lignes de continuation terminées par une barre oblique inverse)."""
    lignes = texte.split("\n")
    commentees, cles = set(), {}
    if ext == ".properties":
        cle, suite = None, False
        for n, l in enumerate(lignes, 1):
            brut = l.strip()
            if brut.startswith(("#", "!")):
                commentees.add(n)
                m = re.match(r"[#!]\s*([\w.\-]+)\s*[=:]", brut)
                cles[n] = m.group(1) if m else brut[:80]
                suite = False
                continue
            if not suite:
                m = re.match(r"([^=:\s]+)\s*[=:]", brut)
                cle = m.group(1) if m else None
            if cle:
                cles[n] = cle
            suite = brut.endswith("\\")
    else:
        for m in re.finditer(r"<!--.*?(?:-->|\Z)|<%--.*?(?:--%>|\Z)", texte, re.S):
            debut = texte.count("\n", 0, m.start()) + 1
            commentees.update(range(debut, debut + m.group().count("\n") + 1))
    return commentees, cles


def _est_test(rel: str) -> bool:
    return bool(re.search(r"(^|/)(src/test|test|tests|it)/", rel))


def _cible(pr: Projet, ctx: dict, fq: str, ap: dict, variables: dict) -> tuple[str | None, str]:
    """Cible d'un appel : ("Classe#méthode", "type") si le receveur est typé, ("?#méthode", "nom") sinon,
    (None, _) si la cible est hors du projet (bibliothèque, JDK)."""
    nom, rec = ap["nom"], ap["recepteur"]
    if ap.get("new"):
        c = pr.resoudre(rec, ctx)
        if not c:
            return None, ""
        simple = c.split(".")[-1]  # constructeur déclaré : Classe#Classe, sinon constructeur implicite
        return (f"{c}#{simple}" if simple in pr.classes[c]["noms_methodes"] else f"{c}#<init>"), "type"
    if rec in (None, "this", "super"):
        depart = fq
        if rec == "super":
            sup = [x for x in pr.classes[fq]["etend"] if x in pr.classes]
            depart = sup[0] if sup else None
        cour = depart
        while cour:
            d = pr.declarant(cour, nom)
            if d:
                return f"{d}#{nom}", "type"
            cour = pr.classes.get(cour, {}).get("externe") if rec is None else None
        if rec is None:
            for imp in ctx["imports_statiques"]:
                classe = imp.rsplit(".", 1)[0]
                if imp.endswith("." + nom) or imp.endswith(".*"):
                    if classe in pr.classes and (imp.endswith("." + nom) or pr.declarant(classe, nom)):
                        return f"{classe}#{nom}", "type"
                    if classe not in pr.classes:
                        return None, ""  # import statique d'une bibliothèque (assertEquals...)
        return f"?#{nom}", "nom"
    if rec == "?":
        if "recepteur_type" in ap:
            retour, classe_declarante = ap["recepteur_type"]
            fichier = pr.classes[classe_declarante]["fichier"]
            c = pr.resoudre(retour, pr.contextes.get(fichier, ctx))
            if c:
                return f"{pr.declarant(c, nom) or c}#{nom}", "type"
            return None, ""  # retour d'un type de bibliothèque
        return f"?#{nom}", "nom"
    if rec in variables:
        t = variables[rec]
        if t in TYPES_EXTERNES_COURANTS:
            return None, ""
        c = pr.resoudre(t, ctx)
        if not c:
            return None, ""
        return f"{pr.declarant(c, nom) or c}#{nom}", "type"
    if rec[:1].isupper():
        c = pr.resoudre(rec, ctx)
        if c:
            return f"{pr.declarant(c, nom) or c}#{nom}", "type"
        if rec in pr.par_nom or (rec.isupper() and len(rec) > 1):
            return f"?#{nom}", "nom"  # classe du projet ambiguë, ou constante
        return None, ""  # classe d'une bibliothèque
    return f"?#{nom}", "nom"


def _web_xml(r: dict, rel: str, servlets: dict, filtres: dict, mappings_filtres: list, routes: list) -> None:
    for s in enfants(r, "servlet"):
        nom = texte_de(s, "servlet-name")
        servlets[nom] = {"classe": texte_de(s, "servlet-class") or texte_de(s, "jsp-file"), "fichier": rel, "ligne": s["ligne"]}
    for f in enfants(r, "filter"):
        filtres[texte_de(f, "filter-name")] = {"classe": texte_de(f, "filter-class"), "fichier": rel, "ligne": f["ligne"]}
    for m in enfants(r, "servlet-mapping"):
        nom = texte_de(m, "servlet-name")
        for u in enfants(m, "url-pattern"):
            routes.append({"url": u["texte"].strip(), "genre": "servlet", "nom": nom,
                           "cible": servlets.get(nom, {}).get("classe", ""), "fichier": rel, "ligne": u["ligne"],
                           "source": "web.xml"})
    for m in enfants(r, "filter-mapping"):
        nom = texte_de(m, "filter-name")
        mappings_filtres.append({
            "filtre": nom, "classe": filtres.get(nom, {}).get("classe", ""),
            "urls": [u["texte"].strip() for u in enfants(m, "url-pattern")],
            "servlets": [u["texte"].strip() for u in enfants(m, "servlet-name")],
            "dispatchers": [d["texte"].strip() for d in enfants(m, "dispatcher")] or ["REQUEST"],
            "fichier": rel, "ligne": m["ligne"],
        })
    for li in enfants(r, "listener"):
        routes.append({"url": "(démarrage)", "genre": "listener", "nom": texte_de(li, "listener-class").split(".")[-1],
                       "cible": texte_de(li, "listener-class"), "fichier": rel, "ligne": li["ligne"], "source": "web.xml"})


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("projet", type=Path)
    a.add_argument("sortie", type=Path)
    args = a.parse_args(argv)
    if not args.projet.is_dir():
        a.error(f"{args.projet} n'est pas un dossier")
    debut = time.monotonic()
    g = construire(args.projet)
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    duree = time.monotonic() - debut
    certains = sum(1 for x in g["appels"] if x[4] == "type")
    print(f"{len(g['classes'])} types, {len(g['methodes'])} méthodes, {len(g['appels'])} appels "
          f"({certains} typés, {len(g['appels']) - certains} par nom seul), {len(g['routes'])} routes, "
          f"{len(g['entites'])} entités, {len(g['tables'])} tables, {len(g['refs_config'])} références de configuration")
    print(f"construit en {duree:.1f} s, {args.sortie.stat().st_size / 1e6:.1f} Mo -> {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
