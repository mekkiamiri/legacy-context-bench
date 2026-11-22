"""Index lexical BM25 sur le code d'un projet Java legacy (bibliothèque standard seulement).

Découpage :
- Java : un morceau par méthode (javadoc et annotations comprises) ; ce qui reste d'une classe
  (en-tête, champs, constantes) forme des morceaux « corps de classe ». Méthodes longues
  coupées en fenêtres.
- Autres fichiers (JSP, XML, SQL, properties, templates, docs) : blocs de lignes, coupés de
  préférence sur une frontière naturelle (balise de premier niveau, CREATE, ligne vide).

Tokenisation : identifiants découpés (camelCase, snake_case, points), minuscules, accents
retirés ; on garde aussi l'identifiant entier (« roller_properties » donne roller_properties,
roller, properties). Le chemin du fichier et le nom du symbole sont indexés avec le contenu.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "commun"))
import javalite  # noqa: E402

EXTENSIONS = {
    ".java", ".jsp", ".jspf", ".tag", ".tld", ".xml", ".sql", ".ddl", ".properties", ".vm", ".ftl",
    ".gradle", ".kts", ".yml", ".yaml", ".md", ".adoc", ".txt", ".html", ".xhtml", ".js",
}
K1, B = 1.2, 0.75
MAX_METHODE, FENETRE, RECOUVREMENT = 120, 80, 10
BLOC_MIN, BLOC_MAX = 12, 50

MOTS_VIDES = set("""
a an and are as at be by for from has have if in into is it its of on or that the this to was
were will with not no do does how what where which who why when can get set new null true false
public private protected static final void return import package class
le la les un une des du de d l et ou est sont en dans par pour sur au aux ce cet cette ces qui que
quoi quel quelle quels quelles comment ou se sa son ses leur leurs il elle ils elles on ne pas plus
avec sans est-ce y a
""".split())

_MOTS = re.compile(r"[A-Za-z0-9_$.]+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _racine(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def tokens(texte: str) -> list[str]:
    out = []
    for mot in _MOTS.findall(_sans_accents(texte)):
        mot = mot.strip("._$")
        if not mot:
            continue
        bas = mot.lower()
        parties = []
        for seg in re.split(r"[._$]+", mot):
            parties += [p.lower() for p in _CAMEL.findall(seg)]
        if len(parties) > 1 and len(bas) <= 60:
            out.append(bas)
        for p in parties:
            if len(p) > 1 and p not in MOTS_VIDES:
                out.append(_racine(p))
        if len(parties) == 1 and parties[0] != bas and bas not in MOTS_VIDES:
            out.append(bas)
    return out


# --- Découpage ---------------------------------------------------------------------------------

def _fenetres(debut: int, fin: int, taille: int, recouvrement: int):
    if fin - debut + 1 <= taille + recouvrement:
        yield debut, fin
        return
    d = debut
    while d <= fin:
        f = min(fin, d + taille - 1)
        yield d, f
        if f == fin:
            break
        d = f + 1 - recouvrement


def decouper_java(src: str) -> list[dict]:
    a = javalite.analyser(src)
    n = src.count("\n") + 1
    morceaux, couvert = [], [False] * (n + 2)
    for t in a["types"]:
        for m in t["methodes"]:
            nom = f"{t['nom']}.{m['nom']}"
            for d, f in _fenetres(m["ligne_doc"], m["ligne_fin"], FENETRE if m["ligne_fin"] - m["ligne_doc"] > MAX_METHODE else MAX_METHODE, RECOUVREMENT):
                morceaux.append({"debut": d, "fin": f, "genre": "méthode", "nom": nom, "sig": m["ligne_sig"] if m["ligne_doc"] <= m["ligne_sig"] <= m["ligne_fin"] else m["ligne_debut"]})
            for i in range(m["ligne_doc"], m["ligne_fin"] + 1):
                couvert[i] = True
    # Le reste (en-têtes, champs, classes sans méthode) : morceaux « corps de classe ».
    def type_de(ligne):
        meilleur = None
        for t in a["types"]:
            if t["ligne_doc"] <= ligne <= t["ligne_fin"]:
                if meilleur is None or t["ligne_doc"] >= meilleur["ligne_doc"]:
                    meilleur = t
        return meilleur

    lignes = src.split("\n")
    i = 1
    while i <= n:
        if couvert[i] or not lignes[i - 1].strip():
            i += 1
            continue
        j = i
        while j + 1 <= n and not couvert[j + 1]:
            j += 1
        while j > i and not lignes[j - 1].strip():
            j -= 1
        texte = "\n".join(lignes[i - 1:j])
        if re.search(r"[A-Za-z]", re.sub(r"[{}();\s]", "", texte)) and not re.fullmatch(r"[\s}]*", texte):
            t = type_de(i)
            nom = t["nom"] if t else ""
            for d, f in _fenetres(i, j, BLOC_MAX, RECOUVREMENT):
                morceaux.append({"debut": d, "fin": f, "genre": "classe", "nom": nom, "sig": d})
        i = j + 1
    morceaux.sort(key=lambda m: m["debut"])
    return morceaux


_FRONTIERES = {
    ".xml": re.compile(r"^\s{0,4}<(?!/|!--)"),
    ".sql": re.compile(r"^\s*(create|alter|insert|drop|--)\b", re.I),
    ".vm": re.compile(r"^\s*(create|alter|insert|drop|#macro|#if)\b", re.I),
    ".properties": re.compile(r"^\s*#"),
    ".md": re.compile(r"^#"),
    ".adoc": re.compile(r"^="),
}


def decouper_lignes(src: str, ext: str) -> list[dict]:
    lignes = src.split("\n")
    frontiere = _FRONTIERES.get(ext)
    morceaux, debut = [], 1
    for i in range(1, len(lignes) + 1):
        taille = i - debut
        coupe = taille >= BLOC_MAX or (
            taille >= BLOC_MIN and (
                (frontiere and frontiere.match(lignes[i - 1]) and not lignes[i - 2].strip().startswith(("#", "--")))
                or (not frontiere and not lignes[i - 1].strip())
            )
        )
        if coupe:
            morceaux.append((debut, i - 1))
            debut = i
    morceaux.append((debut, len(lignes)))
    return [{"debut": d, "fin": f, "genre": "bloc", "nom": "", "sig": d}
            for d, f in morceaux if any(l.strip() for l in lignes[d - 1:f])]


def decouper(chemin: Path, src: str) -> list[dict]:
    ext = chemin.suffix.lower()
    if ext == ".java":
        try:
            return decouper_java(src)
        except Exception:  # analyse légère : en cas d'échec, blocs de lignes
            pass
    return decouper_lignes(src, ext)


# --- Index ---------------------------------------------------------------------------------------

def construire(racine: Path) -> dict:
    racine = Path(racine).resolve()
    docs, postings, longueurs = [], {}, []
    for p in javalite.fichiers(racine, EXTENSIONS):
        rel = p.relative_to(racine).as_posix()
        src = javalite.lire(p)
        lignes = src.split("\n")
        for m in decouper(p, src):
            texte = "\n".join(lignes[m["debut"] - 1:m["fin"]])
            toks = tokens(texte) + tokens(rel) + 2 * tokens(m["nom"])
            if not toks:
                continue
            idx = len(docs)
            docs.append([rel, m["debut"], m["fin"], m["genre"], m["nom"], m["sig"]])
            longueurs.append(len(toks))
            for t, tf in Counter(toks).items():
                postings.setdefault(t, []).extend((idx, tf))
    return {
        "version": 1,
        "racine": str(racine),
        "docs": docs,
        "longueurs": longueurs,
        "moyenne": (sum(longueurs) / len(longueurs)) if longueurs else 0.0,
        "postings": postings,
    }


def sauver(index: dict, sortie: Path) -> None:
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(sortie, "wt", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))


def charger(chemin: Path) -> dict:
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        return json.load(f)


def chercher(index: dict, question: str, k: int = 8) -> list[tuple[float, int, list[str]]]:
    """Retourne [(score, numéro de morceau, termes trouvés)] triés par score décroissant."""
    n = len(index["docs"])
    if not n:
        return []
    termes = list(dict.fromkeys(tokens(question)))
    scores, trouves = {}, {}
    for t in termes:
        liste = index["postings"].get(t)
        if not liste:
            continue
        df = len(liste) // 2
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for i in range(0, len(liste), 2):
            d, tf = liste[i], liste[i + 1]
            dl = index["longueurs"][d]
            s = idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / index["moyenne"]))
            scores[d] = scores.get(d, 0.0) + s
            trouves.setdefault(d, []).append(t)
    meilleurs = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:k]
    return [(s, d, trouves[d]) for d, s in meilleurs]


def extrait(racine: Path, doc: list, termes: list[str], nb_lignes: int = 6) -> list[tuple[int, str]]:
    """Lignes les plus parlantes du morceau (signature + lignes contenant le plus de termes)."""
    rel, debut, fin, _genre, _nom, sig = doc
    try:
        lignes = javalite.lire(Path(racine) / rel).split("\n")[debut - 1:fin]
    except OSError:
        return []
    voulus = set(termes)
    notes = []
    for i, l in enumerate(lignes):
        n = len(voulus.intersection(tokens(l)))
        if n:
            notes.append((-n, i))
    choisies = {sig - debut} if 0 <= sig - debut < len(lignes) else set()
    for _n, i in sorted(notes):
        if len(choisies) >= nb_lignes:
            break
        choisies.add(i)
    if not choisies:
        choisies = set(range(min(nb_lignes, len(lignes))))
    return [(debut + i, lignes[i].rstrip()) for i in sorted(choisies)]
