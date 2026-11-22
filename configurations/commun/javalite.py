"""Analyse légère d'un projet Java legacy, bibliothèque standard seulement.

Partagé par l'index RAG (configurations/2-rag) et le graphe du code (configurations/3-graphe).

Ce n'est PAS un compilateur : pas de résolution de types complète, pas de génériques,
pas de surcharge. On masque commentaires et chaînes, on suit les accolades, et on
reconnaît par expressions régulières les déclarations de types, de méthodes et de champs.
Les limites sont listées dans configurations/3-graphe/README.md.
"""

from __future__ import annotations

import bisect
import os
import re
import xml.parsers.expat
from pathlib import Path

DOSSIERS_IGNORES = {"target", "build", "out", "bin", "node_modules", "dist", "__pycache__"}

MOTS_CLES = {
    "if", "for", "while", "switch", "catch", "synchronized", "return", "new", "else", "try",
    "do", "throw", "case", "assert", "super", "this", "yield", "default", "finally", "instanceof",
}


def fichiers(racine: Path, extensions: set[str], taille_max: int = 1_000_000):
    """Parcourt le projet (ordre stable), sans dossiers cachés ni dossiers de compilation."""
    racine = Path(racine)
    for dossier, sous, noms in os.walk(racine):
        sous[:] = sorted(d for d in sous if d not in DOSSIERS_IGNORES and not d.startswith("."))
        for nom in sorted(noms):
            p = Path(dossier) / nom
            if p.suffix.lower() in extensions:
                try:
                    if p.stat().st_size <= taille_max:
                        yield p
                except OSError:
                    continue


def lire(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# --- Masquage des commentaires et des chaînes ---------------------------------------------

_LITTERAUX = re.compile(
    r'//[^\n]*|/\*.*?(?:\*/|\Z)|"""(?:.|\n)*?(?:"""|\Z)|"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n])*\'?',
    re.S,
)


def _blanc(s: str) -> str:
    return re.sub(r"[^\n]", " ", s)


def masquer(src: str) -> tuple[str, list[tuple[int, str]]]:
    """Remplace commentaires et contenus de chaînes par des espaces (longueurs et lignes conservées).

    Retourne le texte masqué et la liste des chaînes (position, contenu).
    """
    morceaux, chaines, pos = [], [], 0
    for m in _LITTERAUX.finditer(src):
        morceaux.append(src[pos:m.start()])
        t = m.group()
        if t.startswith('"'):
            q = 3 if t.startswith('"""') else 1
            fin = q if t.endswith('"' * q) and len(t) >= 2 * q else 0
            contenu = t[q:len(t) - fin]
            chaines.append((m.start(), contenu))
            morceaux.append(t[:q] + _blanc(contenu) + t[len(t) - fin:])
        elif t.startswith("'"):
            morceaux.append("'" + _blanc(t[1:-1]) + "'" if len(t) > 1 else t)
        else:
            morceaux.append(_blanc(t))
        pos = m.end()
    morceaux.append(src[pos:])
    return "".join(morceaux), chaines


# --- Déclarations ----------------------------------------------------------------------------

_TYPE = re.compile(r"(?:^|[^\w$.@])(class|interface|enum|record|@\s*interface)\s+([A-Za-z_$][\w$]*)")
_METHODE = re.compile(
    r"(?:^|[\s>\],])([A-Za-z_$][\w$]*)\s*\(([^()]*)\)\s*(?:\[\s*\]\s*)*(?:throws\s+[\w.$,\s<>]+)?\s*(?:default\s+[^;]*)?$",
    re.S,
)
_ANNOTATION = re.compile(r"@\s*([A-Za-z_$][\w$.]*)(\s*\((?:[^()]|\([^()]*\))*\))?")
_MODIFS = r"(?:(?:public|private|protected|static|final|transient|volatile|abstract|native|synchronized|default|sealed|non-sealed|strictfp)\s+)*"
_CHAMP = re.compile(r"^" + _MODIFS + r"([\w$.]+(?:\s*<.*>)?(?:\s*\[\s*\])*)\s+([A-Za-z_$][\w$]*)\s*(?:\[\s*\])*$", re.S)
_LOCALE = re.compile(r"\b([A-Z][\w$]*)(?:\s*<[^;{}()]*?>)?(?:\s*\[\s*\])*\s+([a-z_$][\w$]*)\s*(?=[=;:,)])")
_IDENT_APPEL = re.compile(r"([A-Za-z_$][\w$]*)\s*(?:<[^()<>;]*>\s*)?\(")
_NEW = re.compile(r"\bnew\s+([A-Za-z_$][\w$.]*)\s*(?:<[^()]*?>)?\s*[(\[{]")


def sans_generiques(s: str) -> str:
    avant = None
    while avant != s:
        avant, s = s, re.sub(r"<[^<>]*>", "", s)
    return s


def _noms_types(liste: str) -> list[str]:
    liste = sans_generiques(liste)
    return [t.strip().split(".")[-1] for t in liste.split(",") if t.strip()]


def annotations(masque: str, src: str) -> list[dict]:
    """Annotations d'un en-tête : nom et texte des arguments (lu dans le source non masqué)."""
    out = []
    for m in _ANNOTATION.finditer(masque):
        args = src[m.start(2):m.end(2)].strip()[1:-1] if m.group(2) else ""
        out.append({"nom": m.group(1).split(".")[-1], "args": args})
    return out


def valeurs_annotation(args: str, *cles: str) -> list[str]:
    """Chaînes d'un argument d'annotation : @X("a"), @X(value={"a","b"}), @X(path="a")."""
    if not args:
        return []
    for cle in cles:
        m = re.search(r"\b" + cle + r"\s*=\s*(\{[^}]*\}|\"(?:\\.|[^\"])*\")", args)
        if m:
            return re.findall(r'"((?:\\.|[^"])*)"', m.group(1))
    if re.match(r'\s*(\{|")', args):
        m = re.match(r'\s*(\{[^}]*\}|"(?:\\.|[^"])*")', args)
        return re.findall(r'"((?:\\.|[^"])*)"', m.group(1))
    return []


class Lignes:
    def __init__(self, texte: str):
        self.debuts = [0] + [m.end() for m in re.finditer(r"\n", texte)]

    def __call__(self, pos: int) -> int:
        return bisect.bisect_right(self.debuts, pos)


def _premier_non_blanc(texte: str, debut: int, fin: int) -> int:
    m = re.compile(r"\S").search(texte, debut, fin)
    return m.start() if m else fin


def analyser(src: str) -> dict:
    """Analyse un fichier Java : paquetage, imports, types, méthodes, champs, appels, chaînes.

    Lignes numérotées à partir de 1. `ligne_doc` inclut la javadoc et les annotations.
    """
    masque, chaines = masquer(src)
    ligne = Lignes(src)
    paquet = re.search(r"^\s*package\s+([\w.]+)\s*;", masque, re.M)
    imports = [m.group(2) for m in re.finditer(r"^\s*import\s+(static\s+)?([\w.$]+(?:\.\*)?)\s*;", masque, re.M)
               if not m.group(1)]
    imports_statiques = [m.group(1) for m in re.finditer(r"^\s*import\s+static\s+([\w.$]+(?:\.\*)?)\s*;", masque, re.M)]
    types, pile, dernier = [], [], 0

    def type_parent():
        for e in reversed(pile):
            if e["genre"] == "type":
                return e["obj"]
            if e["genre"] == "methode":
                return None
        return None

    for jeton in re.finditer(r"[{};]", masque):
        p, c = jeton.start(), jeton.group()
        parent = pile[-1] if pile else None
        dans_corps = parent is None or parent["genre"] == "type"
        if c == "{":
            entree = {"genre": "bloc", "debut": p}
            if dans_corps:
                entete_m = masque[dernier:p]
                entete_s = src[dernier:p]
                debut_entete = _premier_non_blanc(masque, dernier, p)
                t = _TYPE.search(entete_m)
                if t and not re.search(r"\bnew\s", entete_m):
                    externe = parent["obj"] if parent else None
                    nom = t.group(2)
                    reste = entete_m[t.end():]
                    ext = re.search(r"\bextends\s+(.+?)(?=\bimplements\b|\bpermits\b|$)", reste, re.S)
                    impl = re.search(r"\bimplements\s+(.+?)(?=\bpermits\b|$)", reste, re.S)
                    genre = t.group(1).replace(" ", "")
                    obj = {
                        "nom": nom,
                        "nom_complet": (externe["nom_complet"] + "." + nom) if externe
                        else ((paquet.group(1) + "." + nom) if paquet else nom),
                        "genre": "annotation" if genre.startswith("@") else genre,
                        "etend": _noms_types(ext.group(1)) if ext else [],
                        "implemente": _noms_types(impl.group(1)) if impl else [],
                        "annotations": annotations(entete_m, entete_s),
                        "ligne_doc": ligne(_premier_non_blanc(src, dernier, p)),
                        "ligne_debut": ligne(debut_entete),
                        "ligne_fin": None,
                        "externe": externe["nom_complet"] if externe else None,
                        "champs": {},
                        "methodes": [],
                    }
                    types.append(obj)
                    entree = {"genre": "type", "debut": p, "obj": obj}
                elif parent is not None:
                    nettoye = _ANNOTATION.sub(lambda m: _blanc(m.group()), entete_m)
                    mm = _METHODE.search(nettoye)
                    if mm and "=" not in nettoye and mm.group(1) not in MOTS_CLES:
                        obj = _methode(mm, nettoye, entete_m, entete_s, ligne, src, dernier, debut_entete, p)
                        parent["obj"]["methodes"].append(obj)
                        entree = {"genre": "methode", "debut": p, "obj": obj}
            pile.append(entree)
            dernier = p + 1
        elif c == "}":
            if pile:
                e = pile.pop()
                if e["genre"] in ("type", "methode"):
                    e["obj"]["ligne_fin"] = ligne(p)
                    if e["genre"] == "methode":
                        e["obj"]["corps"] = (e["debut"] + 1, p)
            dernier = p + 1
        else:
            if parent is not None and parent["genre"] == "type":
                entete_m = masque[dernier:p]
                nettoye = _ANNOTATION.sub(lambda m: _blanc(m.group()), entete_m).strip()
                avant_egal = nettoye.split("=")[0].strip()
                mm = _METHODE.search(nettoye) if "=" not in nettoye else None
                if mm and mm.group(1) not in MOTS_CLES:
                    debut_entete = _premier_non_blanc(masque, dernier, p)
                    obj = _methode(mm, nettoye, entete_m, src[dernier:p], ligne, src, dernier, debut_entete, p)
                    obj["abstraite"] = True
                    obj["ligne_fin"] = ligne(p)
                    parent["obj"]["methodes"].append(obj)
                else:
                    ch = _CHAMP.match(avant_egal)
                    if ch:
                        parent["obj"]["champs"][ch.group(2)] = sans_generiques(ch.group(1)).replace("[]", "").strip().split(".")[-1]
            dernier = p + 1

    for t in types:
        if t["ligne_fin"] is None:
            t["ligne_fin"] = ligne(len(src))
        for m in t["methodes"]:
            if m["ligne_fin"] is None:
                m["ligne_fin"] = t["ligne_fin"]
            corps = m.pop("corps", None)
            m["appels"], m["locales"] = (_appels(masque, corps, ligne) if corps else ([], {}))
            m["locales"].update(m.pop("params_types"))

    return {
        "paquet": paquet.group(1) if paquet else "",
        "imports": imports,
        "imports_statiques": imports_statiques,
        "types": types,
        "chaines": [(ligne(pos), s) for pos, s in chaines],
        "masque": masque,
    }


def _methode(mm, nettoye, entete_m, entete_s, ligne, src, dernier, debut_entete, p) -> dict:
    params = mm.group(2)
    params_types = {}
    for morceau in sans_generiques(params).split(","):
        mots = morceau.replace("...", " ").replace("final ", " ").split()
        if len(mots) >= 2:
            params_types[mots[-1]] = mots[-2].replace("[]", "").split(".")[-1]
    return {
        "nom": mm.group(1),
        "retour": (sans_generiques(nettoye[:mm.start(1)]).replace("[]", " ").split() or [""])[-1].split(".")[-1],
        "params": " ".join(params.split()),
        "arite": len([x for x in sans_generiques(params).split(",") if x.strip()]),
        "annotations": annotations(entete_m, entete_s),
        "ligne_doc": ligne(_premier_non_blanc(src, dernier, p)),
        "ligne_debut": ligne(debut_entete),
        "ligne_sig": ligne(dernier + mm.start(1)),
        "ligne_fin": None,
        "abstraite": False,
        "params_types": params_types,
    }


def _appels(masque: str, corps: tuple[int, int], ligne) -> tuple[list[dict], dict]:
    """Appels de méthodes dans un corps : nom, receveur (texte), ligne. Approximation syntaxique."""
    debut, fin = corps
    texte = masque[debut:fin]
    locales = {m.group(2): m.group(1) for m in _LOCALE.finditer(texte)}
    appels = []
    for m in _NEW.finditer(texte):
        appels.append({"nom": "<init>", "recepteur": m.group(1).split(".")[-1], "ligne": ligne(debut + m.start()), "new": True})
    for m in _IDENT_APPEL.finditer(texte):
        nom = m.group(1)
        if nom in MOTS_CLES:
            continue
        i = m.start() - 1
        while i >= 0 and texte[i] in " \t\r\n":
            i -= 1
        recepteur, chaine = None, None
        if i >= 0 and texte[i] == ".":
            j = i - 1
            while j >= 0 and texte[j] in " \t\r\n":
                j -= 1
            if j >= 0 and texte[j] == ")":
                # appel chaîné a.b().c() : on retient l'appel précédent pour typer par son retour
                prof, k = 0, j
                while k >= 0:
                    prof += {")": 1, "(": -1}.get(texte[k], 0)
                    if prof == 0:
                        break
                    k -= 1
                av = re.search(r"([A-Za-z_$][\w$]*)\s*(?:<[^()<>;]*>\s*)?$", texte[max(0, k - 80):k])
                recepteur = "?"
                if av:
                    chaine = k - (len(texte[max(0, k - 80):k]) - av.start(1))
            elif j >= 0 and texte[j] == "]":
                recepteur = "?"
            else:
                k = j
                while k >= 0 and (texte[k].isalnum() or texte[k] in "_$"):
                    k -= 1
                recepteur = texte[k + 1:j + 1] or "?"
                if re.search(r"\bnew\s+[\w$.\s]*$", texte[max(0, k - 100):k + 1]):
                    continue  # new java.util.Date(...) : constructeur qualifié, déjà vu par _NEW
        else:
            if i >= 0 and texte[i] == "@":
                continue  # annotation
            avant = re.search(r"([\w$]+)\s*$", texte[max(0, i - 60):i + 1]) if i >= 0 else None
            if avant and (avant.group(1) == "new" or (avant.group(1) not in MOTS_CLES and not avant.group(1)[0].isdigit())):
                continue  # `new X(` ou déclaration (méthode d'une classe anonyme), pas un appel
        ap = {"nom": nom, "recepteur": recepteur, "ligne": ligne(debut + m.start()), "pos": debut + m.start()}
        if chaine is not None:
            ap["apres"] = debut + chaine
        appels.append(ap)
    appels.sort(key=lambda a: (a["ligne"], a.get("pos", 0)))
    return appels, locales


# --- XML avec numéros de ligne ----------------------------------------------------------------

def lire_xml(chemin: Path) -> dict | None:
    """Arbre XML minimal avec numéros de ligne (expat). Espaces de noms retirés. None si illisible."""
    racine = {"tag": "#doc", "attr": {}, "texte": "", "ligne": 0, "enfants": []}
    pile = [racine]
    parseur = xml.parsers.expat.ParserCreate()

    def local(nom: str) -> str:
        return nom.split("}")[-1].split(":")[-1]

    def debut(nom, attrs):
        e = {"tag": local(nom), "attr": {local(k): v for k, v in attrs.items()}, "texte": "",
             "ligne": parseur.CurrentLineNumber, "enfants": []}
        pile[-1]["enfants"].append(e)
        pile.append(e)

    def fin(nom):
        pile.pop()

    def texte(t):
        pile[-1]["texte"] += t

    parseur.StartElementHandler = debut
    parseur.EndElementHandler = fin
    parseur.CharacterDataHandler = texte
    try:
        parseur.Parse(chemin.read_bytes(), True)
    except (xml.parsers.expat.ExpatError, ValueError, OSError):
        return None
    return racine["enfants"][0] if racine["enfants"] else None


def enfants(e: dict, tag: str) -> list[dict]:
    return [x for x in e["enfants"] if x["tag"] == tag]


def texte_de(e: dict, tag: str) -> str:
    for x in e["enfants"]:
        if x["tag"] == tag:
            return x["texte"].strip()
    return ""


def tous(e: dict, tag: str):
    for x in e["enfants"]:
        if x["tag"] == tag:
            yield x
        yield from tous(x, tag)
