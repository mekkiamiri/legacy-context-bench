"""Interroge le graphe du code construit par graph_build.py.

Usage :
    python3 configurations/3-graphe/graph_query.py who-calls <méthode>     # qui appelle (Classe.méthode ou méthode)
    python3 configurations/3-graphe/graph_query.py callees <méthode>       # ce qu'elle appelle
    python3 configurations/3-graphe/graph_query.py route <url> [--dispatcher REQUEST]
                                                                            # filtres, servlet, action, contrôleur
    python3 configurations/3-graphe/graph_query.py table <entité|table>    # entité <-> table, CREATE TABLE, SQL
    python3 configurations/3-graphe/graph_query.py neighbors <classe>      # héritage, usages, config, routes
    python3 configurations/3-graphe/graph_query.py find <terme>            # cherche un nom dans le graphe

Graphe par défaut : variable GRAPHE_JSON, sinon .contexte/graphe.json à la racine du banc.
Les appels sont approximatifs : « sûr » = receveur typé par l'analyse, « possible » = même nom
de méthode, receveur inconnu.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
GRAPHE_DEFAUT = ICI.parent.parent / ".contexte" / "graphe.json"


def court(fq: str) -> str:
    """org.a.b.Classe#méthode -> Classe.méthode ; org.a.b.Classe -> Classe."""
    c, _, m = fq.partition("#")
    nom = c.split(".")[-1] if c != "?" else "?"
    return f"{nom}.{m}" if m else nom


class Graphe:
    def __init__(self, g: dict):
        self.g = g
        self.classes = g["classes"]

    # -- recherche de classes et de méthodes ----------------------------------------------------
    def classes_nommees(self, nom: str) -> list[str]:
        nom = nom.strip()
        if nom in self.classes:
            return [nom]
        bas = nom.lower()
        exacts = [c for c in self.classes if c.split(".")[-1] == nom or c.endswith("." + nom)]
        return exacts or [c for c in self.classes if c.split(".")[-1].lower() == bas]

    def methodes_nommees(self, requete: str) -> list[str]:
        requete = requete.replace("#", ".").replace("()", "").strip()
        if "." in requete:
            classe, _, nom = requete.rpartition(".")
            return [f"{c}#{nom}" for c in self.classes_nommees(classe) if f"{c}#{nom}" in self.g["methodes"]]
        return [m for m in self.g["methodes"] if m.endswith("#" + requete)]

    def ancetres(self, c: str) -> list[str]:
        vus, file = [], [c]
        while file:
            x = file.pop(0)
            if x in vus or x not in self.classes:
                continue
            vus.append(x)
            file += self.classes[x]["etend"] + self.classes[x]["implemente"]
        return vus

    def descendants(self, c: str) -> list[str]:
        out = []
        for x, info in self.classes.items():
            if x != c and c in self.ancetres(x):
                out.append(x)
        return out

    def famille(self, mids: list[str]) -> list[str]:
        """Méthode + mêmes noms dans les interfaces / classes mères et dans les implémentations."""
        out = []
        for mid in mids:
            c, _, nom = mid.partition("#")
            for x in [c] + self.ancetres(c)[1:] + self.descendants(c):
                if f"{x}#{nom}" in self.g["methodes"] and f"{x}#{nom}" not in out:
                    out.append(f"{x}#{nom}")
        return out

    def ordre(self, c: str) -> tuple:
        """Code principal avant les tests, puis ordre alphabétique du nom court."""
        f = self.classes.get(c, {}).get("fichier", "")
        return ("/test/" in "/" + f or "/tests/" in "/" + f, court(c))

    def decl(self, mid: str) -> str:
        d = self.g["methodes"].get(mid)
        return f"{d[0]['fichier']}:{d[0]['ligne']}" if d else ""


def cmd_who_calls(G: Graphe, requete: str, maxi: int) -> None:
    mids = G.methodes_nommees(requete)
    if not mids:
        print(f"Méthode introuvable : {requete}. Essayer : find {requete.split('.')[-1]}")
        return
    cibles = G.famille(mids)
    print(f"Cibles ({len(cibles)}, interfaces et implémentations comprises) :")
    for c in cibles[:maxi]:
        abstr = " (abstraite)" if G.g["methodes"][c][0]["abstraite"] else ""
        print(f"  {court(c)}{abstr}  {G.decl(c)}")
    noms = {c.partition("#")[2] for c in cibles}
    surs = [a for a in G.g["appels"] if a[1] in cibles]
    possibles = [a for a in G.g["appels"] if a[4] == "nom" and a[1].partition("#")[2] in noms]
    print(f"\nAppelants sûrs (receveur typé) : {len(surs)}")
    for a in sorted(surs, key=lambda a: (a[2], a[3]))[:maxi]:
        print(f"  {court(a[0])}  {a[2]}:{a[3]}  -> {court(a[1])}")
    if len(surs) > maxi:
        print(f"  ... {len(surs) - maxi} de plus (--max)")
    if possibles:
        print(f"\nAppelants possibles (même nom, receveur inconnu) : {len(possibles)}")
        for a in sorted(possibles, key=lambda a: (a[2], a[3]))[:min(maxi, 10)]:
            print(f"  {court(a[0])}  {a[2]}:{a[3]}")


def cmd_callees(G: Graphe, requete: str, maxi: int) -> None:
    mids = G.methodes_nommees(requete)
    if not mids:
        print(f"Méthode introuvable : {requete}. Essayer : find {requete.split('.')[-1]}")
        return
    for mid in mids[:5]:
        print(f"{court(mid)}  {G.decl(mid)}")
        vus, n = set(), 0
        for a in sorted((a for a in G.g["appels"] if a[0] == mid), key=lambda a: a[3]):
            if a[1] in vus:
                continue
            vus.add(a[1])
            n += 1
            if n > maxi:
                print(f"  ... (--max)")
                break
            marque = "" if a[4] == "type" else "  (receveur inconnu)"
            decl = G.decl(a[1])
            print(f"  ligne {a[3]:>5}  -> {court(a[1])}{'  ' + decl if decl else ''}{marque}")
        if not vus:
            print("  (aucun appel vers le code du projet)")
        print()


def _motif_servlet(motif: str, chemin: str) -> tuple[int, int] | None:
    """Correspondance d'url-pattern (spécification servlet). Retourne (priorité, longueur) ou None."""
    if motif == chemin:
        return (4, len(motif))
    if motif.endswith("/*"):
        base = motif[:-2]
        if chemin == base or chemin.startswith(base + "/") or base == "":
            return (3, len(base))
    if motif.startswith("*.") and chemin.rsplit("/", 1)[-1].endswith(motif[1:]):
        return (2, len(motif))
    if motif == "/":
        return (1, 0)
    return None


def _motif_route(motif: str, chemin: str) -> bool:
    rx = re.escape(motif.rstrip("/") or "/")
    rx = rx.replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    rx = re.sub(r"\\\{[^}]*\\\}", "[^/]+", rx)
    return re.fullmatch(rx, chemin.rstrip("/") or "/") is not None or (
        motif.count("/") >= 2 and re.search(rx + "$", chemin.rstrip("/")) is not None)


def cmd_route(G: Graphe, url: str, dispatcher: str, maxi: int) -> None:
    chemin = "/" + url.split("?")[0].split("#")[0].lstrip("/")
    routes = G.g["routes"]
    print(f"{chemin}  (dispatcher {dispatcher})")
    servlets = [(m, r) for r in routes if r["genre"] == "servlet" for m in [_motif_servlet(r["url"], chemin)] if m]
    servlets.sort(key=lambda x: x[0], reverse=True)
    servlet = servlets[0][1] if servlets else None
    filtres = [f for f in G.g["ordre_filtres"] if dispatcher in f["dispatchers"] and (
        any(_motif_servlet(u, chemin) for u in f["urls"]) or (servlet and servlet["nom"] in f["servlets"]))]
    print(f"\nFiltres appliqués, dans l'ordre de déclaration ({len(filtres)}) :")
    for i, f in enumerate(filtres, 1):
        quoi = ", ".join(f["urls"] + [f"servlet {s}" for s in f["servlets"]])
        print(f"  {i:>2}. {f['filtre']}  {f['classe']}  [{quoi}]  {f['fichier']}:{f['ligne']}")
    autres = [f for f in G.g["ordre_filtres"] if f not in filtres and (
        any(_motif_servlet(u, chemin) for u in f["urls"]) or (servlet and servlet["nom"] in f["servlets"]))]
    for f in autres:
        print(f"      (pas en {dispatcher} : {f['filtre']} seulement {'/'.join(f['dispatchers'])}, {f['fichier']}:{f['ligne']})")
    if servlet:
        print(f"\nServlet : {servlet['nom']}  {servlet['cible']}  [{servlet['url']}]  {servlet['fichier']}:{servlet['ligne']}")
    exts = G.g.get("extensions_struts") or ["action", ""]
    sans_ext = chemin
    for e in exts:
        if e and chemin.endswith("." + e):
            sans_ext = chemin[: -len(e) - 1]
    ns, _, nom = sans_ext.rpartition("/")
    actions = [r for r in routes if r["genre"] == "action" and r["url"].rpartition("/")[0] == ns
               and re.fullmatch(re.escape(r["nom"]).replace(r"\*", "[^/]*"), nom)]
    if not actions:
        actions = [r for r in routes if r["genre"] == "action" and r["url"].rpartition("/")[0] == ""
                   and r["nom"] == nom]
    for r in actions:
        res = f"  vues : {', '.join(r['resultats'])}" if r.get("resultats") else ""
        print(f"\nAction ({r['source']}) : {r['url']} -> {r['cible']}#{r['methode']}  {r['fichier']}:{r['ligne']}{res}")
    annot = [r for r in routes if r["genre"] in ("annotation",) and _motif_route(r["url"], chemin)]
    for r in annot[:maxi]:
        print(f"\nContrôleur ({r['source']}) : {r['url']} -> {court(r['cible'] + '#' + r['methode'])}  {r['fichier']}:{r['ligne']}")
    if not servlet and not actions and not annot:
        print("\nAucune servlet, action ni contrôleur déclaré pour ce chemin.")
    if (not servlet or servlet["url"] in ("/", "/*")) and not actions and not annot:
        print("Si l'URL est traitée quand même, la réécriture est faite par du code (souvent un filtre ci-dessus) :"
              " le graphe ne la voit pas. Regarder les filtres sur /*.")


def cmd_table(G: Graphe, requete: str, maxi: int) -> None:
    bas = requete.lower()
    entites = [e for e in G.g["entites"] if e["table"].lower() == bas or e["classe"] == requete
               or e["classe"].split(".")[-1].lower() == bas]
    tables = {e["table"].lower() for e in entites} | ({bas} if bas in G.g["tables"] else set())
    if not entites and not tables:
        proches = sorted(t for t in G.g["tables"] if bas in t) + sorted(
            e["classe"] for e in G.g["entites"] if bas in e["classe"].lower())
        print(f"Ni entité ni table « {requete} ». Proches : {', '.join(proches[:15]) or 'aucune'}")
        return
    for e in entites:
        print(f"Entité {e['classe']} -> table {e['table']}  ({e['source']}, {e['fichier']}:{e['ligne']})")
        for u in G.g["unites_persistance"]:
            if e["classe"] in u["classes"] or any(e["fichier"].endswith(f) for f in u["fichiers_mapping"]):
                print(f"  unité de persistance « {u['nom']} »  {u['fichier']}:{u['ligne']}"
                      + (f"  fournisseur {u['fournisseur']}" if u["fournisseur"] else ""))
    racine = Path(G.g["racine"])
    for t in sorted(tables):
        if not any(e["table"].lower() == t for e in entites):
            print(f"Table {t} : aucune entité JPA/Hibernate trouvée pour elle")
        for d in G.g["tables"].get(t, [])[:maxi]:
            print(f"\nCREATE TABLE {t}  {d['fichier']}:{d['ligne']}")
            try:
                lignes = (racine / d["fichier"]).read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError:
                continue
            for i in range(d["ligne"] - 1, min(len(lignes), d["ligne"] + 14)):
                print(f"   {i + 1:>5} | {lignes[i].rstrip()[:140]}")
                if ";" in lignes[i] or (i > d["ligne"] - 1 and lignes[i].strip().startswith(")")):
                    break
        sql = {}
        for s in G.g["sql_java"]:
            if s[1] == t:
                sql.setdefault((s[0], s[2]), []).append(s[3])
        if sql:
            print(f"\nSQL écrit à la main citant {t} ({len(sql)} classes) :")
            for (c, f), lignes in sorted(sql.items(), key=lambda x: x[0][1])[:maxi]:
                print(f"  {court(c)}  {f}:{lignes[0]}" + (f"  (+{len(lignes) - 1} autres lignes)" if len(lignes) > 1 else ""))
    for e in entites:
        utilisateurs = sorted((c for c, u in G.g["utilise"].items() if e["classe"] in u), key=G.ordre)
        if utilisateurs:
            print(f"\nClasses qui utilisent {court(e['classe'])} ({len(utilisateurs)}) : "
                  + ", ".join(court(c) for c in utilisateurs[:maxi]) + (" ..." if len(utilisateurs) > maxi else ""))
            charges = [r for r in G.g["ressources"] if r[0] in utilisateurs and r[2]]
            if charges:
                print("Fichiers de configuration chargés par ces classes :")
                for r in charges[:maxi]:
                    print(f"  {court(r[0])} charge {r[1]}  ({r[3]}:{r[4]})")


def cmd_neighbors(G: Graphe, requete: str, maxi: int) -> None:
    cs = G.classes_nommees(requete)
    if not cs:
        print(f"Classe introuvable : {requete}. Essayer : find {requete}")
        return
    if len(cs) > 1:
        print(f"{len(cs)} classes portent ce nom : {', '.join(cs)}\n")
    for c in cs[:3]:
        info = G.classes[c]
        print(f"{info['genre']} {c}  {info['fichier']}:{info['lignes'][0]}-{info['lignes'][1]}")
        if info["annotations"]:
            print(f"  annotations : {', '.join('@' + a for a in info['annotations'])}")
        if info["etend"]:
            print(f"  étend : {', '.join(info['etend'])}")
        if info["implemente"]:
            print(f"  implémente : {', '.join(info['implemente'])}")
        fils = [x for x, i in G.classes.items() if c in i["etend"] + i["implemente"]]
        if fils:
            print(f"  sous-types directs : {', '.join(court(x) for x in fils[:maxi])}")
        utilise = G.g["utilise"].get(c, [])
        if utilise:
            print(f"  utilise ({len(utilise)}) : {', '.join(court(x) for x in utilise[:maxi])}" + (" ..." if len(utilise) > maxi else ""))
        par = sorted((x for x, u in G.g["utilise"].items() if c in u), key=G.ordre)
        if par:
            print(f"  utilisée par ({len(par)}) : {', '.join(court(x) for x in par[:maxi])}" + (" ..." if len(par) > maxi else ""))
        appelants = {}
        for a in G.g["appels"]:
            if a[1].partition("#")[0] == c and a[0].partition("#")[0] != c:
                appelants[a[0].partition("#")[0]] = appelants.get(a[0].partition("#")[0], 0) + 1
        if appelants:
            top = sorted(appelants.items(), key=lambda x: -x[1])[:maxi]
            print(f"  appelée depuis ({len(appelants)} classes) : {', '.join(f'{court(x)} ({n})' for x, n in top)}")
        for r in G.g["refs_config"]:
            if r[3] == c:
                print(f"  citée en configuration : {r[0]}:{r[1]}  {r[2]}" + ("  (EN COMMENTAIRE, inactive)" if r[4] else ""))
        for r in G.g["routes"]:
            if r.get("cible") == c:
                print(f"  route : {r['genre']} {r['url']}  {r['fichier']}:{r['ligne']}")
        for f in G.g["ordre_filtres"]:
            if f["classe"] == c:
                print(f"  filtre web.xml : {f['filtre']} sur {', '.join(f['urls'] + f['servlets'])} ({'/'.join(f['dispatchers'])})  {f['fichier']}:{f['ligne']}")
        for e in G.g["entites"]:
            if e["classe"] == c:
                print(f"  entité -> table {e['table']}  ({e['source']}, {e['fichier']}:{e['ligne']})")
        for s in G.g["sql_java"]:
            if s[0] == c:
                print(f"  SQL dans une chaîne -> table {s[1]}  {s[2]}:{s[3]}")
        for r in G.g["ressources"]:
            if r[0] == c:
                print(f"  charge la ressource {r[1]}  ({r[3]}:{r[4]})" + (f" -> {', '.join(r[2][:3])}" if r[2] else ""))
        for b in G.g["beans"]:
            if b["classe"] == c:
                print(f"  bean Spring « {b['id']} »  {b['fichier']}:{b['ligne']}")
        print()


def cmd_find(G: Graphe, terme: str, maxi: int) -> None:
    bas = terme.lower()
    groupes = [
        ("Classes", [f"{c}  {i['fichier']}:{i['lignes'][0]}" for c, i in G.classes.items() if bas in c.split(".")[-1].lower()]),
        ("Méthodes", [f"{court(m)}  {G.decl(m)}" for m in G.g["methodes"] if bas in m.partition("#")[2].lower()]),
        ("Tables", [f"{t}  {d[0]['fichier']}:{d[0]['ligne']}" for t, d in G.g["tables"].items() if bas in t]),
        ("Entités", [f"{e['classe']} -> {e['table']}" for e in G.g["entites"] if bas in e["classe"].lower() or bas in e["table"].lower()]),
        ("Routes", [f"{r['genre']} {r['url']} -> {r.get('cible', '')}" for r in G.g["routes"] if bas in r["url"].lower() or bas in r.get("nom", "").lower()]),
        ("Configuration", [f"{r[0]}:{r[1]}  {r[2]} -> {court(r[3])}" + ("  (EN COMMENTAIRE, inactive)" if r[4] else "")
                           for r in G.g["refs_config"] if bas in r[2].lower() or bas in r[3].lower()]),
        ("Ressources chargées", [f"{court(r[0])} charge {r[1]}  {r[3]}:{r[4]}" for r in G.g["ressources"] if bas in r[1].lower()]),
    ]
    rien = True
    for titre, lignes in groupes:
        if lignes:
            rien = False
            print(f"{titre} ({len(lignes)}) :")
            for l in lignes[:maxi]:
                print(f"  {l}")
            if len(lignes) > maxi:
                print(f"  ... {len(lignes) - maxi} de plus")
    if rien:
        print(f"Rien dans le graphe pour « {terme} » (le graphe ne contient que des noms : classes, méthodes, tables, routes).")


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("commande", choices=["who-calls", "callees", "route", "table", "neighbors", "find"])
    a.add_argument("cible", nargs="+")
    a.add_argument("--graphe", type=Path, default=Path(os.environ.get("GRAPHE_JSON", GRAPHE_DEFAUT)))
    a.add_argument("--dispatcher", default="REQUEST", help="pour route : REQUEST, FORWARD, INCLUDE, ERROR")
    a.add_argument("--max", type=int, default=20)
    args = a.parse_args(argv)
    if not args.graphe.is_file():
        print(f"Graphe introuvable : {args.graphe}. Le construire avec graph_build.py <projet> <sortie>.", file=sys.stderr)
        return 2
    G = Graphe(json.loads(args.graphe.read_text(encoding="utf-8")))
    cible = " ".join(args.cible)
    if args.commande == "who-calls":
        cmd_who_calls(G, cible, args.max)
    elif args.commande == "callees":
        cmd_callees(G, cible, args.max)
    elif args.commande == "route":
        cmd_route(G, cible, args.dispatcher.upper(), args.max)
    elif args.commande == "table":
        cmd_table(G, cible, args.max)
    elif args.commande == "neighbors":
        cmd_neighbors(G, cible, args.max)
    else:
        cmd_find(G, cible, args.max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
