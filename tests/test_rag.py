import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "configurations" / "2-rag"))

import bm25  # noqa: E402
import rag_search  # noqa: E402

MINI = Path(__file__).resolve().parent / "fixtures" / "mini-projet"


def corpus(fichiers: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    for nom, texte in fichiers.items():
        (d / nom).parent.mkdir(parents=True, exist_ok=True)
        (d / nom).write_text(texte, encoding="utf-8")
    return d


class TestTokens(unittest.TestCase):
    def test_identifiants_decoupes_et_entiers(self):
        t = bm25.tokens("roller_properties RuntimeConfigProperty")
        for attendu in ("roller_properties", "roller", "property", "runtimeconfigproperty", "runtime", "config"):
            self.assertIn(attendu, t)

    def test_accents_et_mots_vides(self):
        self.assertEqual(bm25.tokens("Où sont les réglages ?"), ["reglage"])


class TestDecoupage(unittest.TestCase):
    def test_une_methode_par_morceau_avec_sa_javadoc(self):
        src = (MINI / "src/main/java/com/ex/service/UserServiceImpl.java").read_text(encoding="utf-8")
        morceaux = bm25.decouper_java(src)
        auth = [m for m in morceaux if m["nom"] == "UserServiceImpl.authenticate"]
        self.assertEqual(len(auth), 1)
        self.assertEqual((auth[0]["debut"], auth[0]["sig"], auth[0]["fin"]), (9, 11, 14))
        self.assertTrue(any(m["genre"] == "classe" for m in morceaux))  # en-tête et constante

    def test_accolades_dans_chaines_et_commentaires(self):
        src = (MINI / "src/main/java/com/ex/web/LoginAction.java").read_text(encoding="utf-8")
        execute = [m for m in bm25.decouper_java(src) if m["nom"] == "LoginAction.execute"]
        self.assertEqual((execute[0]["sig"], execute[0]["fin"]), (15, 22))

    def test_sql_coupe_sur_create(self):
        lignes = ["-- x"] + [f"create table t{i} (" if i % 15 == 0 else "  col int," for i in range(60)]
        morceaux = bm25.decouper_lignes("\n".join(lignes), ".sql")
        self.assertGreater(len(morceaux), 2)
        self.assertTrue(all(m["fin"] - m["debut"] < bm25.BLOC_MAX for m in morceaux))


class TestClassement(unittest.TestCase):
    def test_terme_rare_et_frequent_gagne(self):
        d = corpus({
            "a.properties": "cache.size=10\ncache.ttl=60\n",
            "b.sql": "create table roller_properties (name varchar(255), value text);\n",
            "c.xml": "<config><property name=\"cache\" value=\"roller\"/></config>\n",
        })
        index = bm25.construire(d)
        res = bm25.chercher(index, "roller_properties table", k=3)
        self.assertEqual(index["docs"][res[0][1]][0], "b.sql")
        res = bm25.chercher(index, "cache ttl", k=3)
        self.assertEqual(index["docs"][res[0][1]][0], "a.properties")

    def test_mini_projet(self):
        index = bm25.construire(MINI)
        premier = lambda q: index["docs"][bm25.chercher(index, q, k=1)[0][1]]  # noqa: E731
        self.assertEqual(premier("password hash authenticate")[4], "UserServiceImpl.authenticate")
        self.assertIn(premier("app_settings table")[0], {"src/main/resources/sql/schema.sql", "src/main/resources/META-INF/orm.xml"})
        self.assertEqual(premier("struts action login extension")[0], "src/main/resources/struts.xml")

    def test_aucun_terme_connu(self):
        self.assertEqual(bm25.chercher(bm25.construire(MINI), "zzzinconnu"), [])


class TestCommande(unittest.TestCase):
    def test_sauver_charger_et_chercher(self):
        sortie = Path(tempfile.mkdtemp()) / "index.json.gz"
        bm25.sauver(bm25.construire(MINI), sortie)
        out = io.StringIO()
        with redirect_stdout(out):
            code = rag_search.main(["authenticate password", "--k", "2", "--index", str(sortie)])
        self.assertEqual(code, 0)
        texte = out.getvalue()
        self.assertIn("UserServiceImpl.java:9-14", texte)
        self.assertIn("public boolean authenticate", texte)

    def test_index_absent(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(rag_search.main(["x", "--index", "/nexiste/pas.json.gz"]), 2)


if __name__ == "__main__":
    unittest.main()
