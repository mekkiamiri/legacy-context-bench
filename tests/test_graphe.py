import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "configurations" / "3-graphe"))
sys.path.insert(0, str(RACINE / "configurations" / "commun"))

import graph_build  # noqa: E402
import graph_query  # noqa: E402
import javalite  # noqa: E402

MINI = Path(__file__).resolve().parent / "fixtures" / "mini-projet"
P = "com.ex."


class TestJavalite(unittest.TestCase):
    def test_masquage_conserve_les_lignes(self):
        src = 'a = "x { y"; // }\n/* {\n */ b = \'}\';'
        masque, chaines = javalite.masquer(src)
        self.assertEqual(len(masque), len(src))
        self.assertEqual(masque.count("\n"), 2)
        self.assertNotIn("{", masque)
        self.assertEqual(chaines, [(4, "x { y")])

    def test_types_methodes_appels(self):
        a = javalite.analyser((MINI / "src/main/java/com/ex/web/LoginAction.java").read_text(encoding="utf-8"))
        t = a["types"][0]
        self.assertEqual((t["nom_complet"], t["etend"]), (P + "web.LoginAction", ["BaseAction"]))
        self.assertEqual(t["champs"]["userService"], "UserService")
        appels = {(x["nom"], x["recepteur"]) for x in t["methodes"][0]["appels"]}
        self.assertTrue({("authenticate", "userService"), ("addError", None), ("execute", "super")} <= appels)


class TestGraphe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = graph_build.construire(MINI)
        cls.G = graph_query.Graphe(json.loads(json.dumps(cls.g)))

    def q(self, *args):
        f = Path(tempfile.mkdtemp()) / "g.json"
        f.write_text(json.dumps(self.g), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            graph_query.main(list(args) + ["--graphe", str(f)])
        return out.getvalue()

    def test_heritage(self):
        c = self.g["classes"]
        self.assertEqual(c[P + "web.LoginAction"]["etend"], [P + "web.BaseAction"])
        self.assertEqual(c[P + "service.UserServiceImpl"]["implemente"], [P + "service.UserService"])

    def test_appels_types(self):
        appels = {(a[0], a[1]) for a in self.g["appels"] if a[4] == "type"}
        self.assertIn((P + "web.LoginAction#execute", P + "service.UserService#authenticate"), appels)
        self.assertIn((P + "web.LoginAction#execute", P + "web.BaseAction#addError"), appels)
        self.assertIn((P + "service.UserServiceImpl#authenticate", P + "model.User#getPasswordHash"), appels)
        self.assertIn((P + "service.UserServiceImpl#findUser", P + "model.User#User"), appels)
        self.assertFalse(any(a[1].endswith("#toHexString") for a in self.g["appels"]))  # JDK ignoré

    def test_who_calls_passe_par_l_interface(self):
        out = self.q("who-calls", "UserServiceImpl.authenticate")
        self.assertIn("LoginAction.execute  src/main/java/com/ex/web/LoginAction.java:16", out)

    def test_callees(self):
        out = self.q("callees", "UserServiceImpl.authenticate")
        self.assertIn("UserServiceImpl.findUser", out)
        self.assertIn("UserServiceImpl.hash", out)

    def test_route_struts_et_filtres(self):
        out = self.q("route", "/admin/login.do")
        self.assertIn("com.ex.web.LoginAction#execute", out)
        self.assertIn("1. EncodingFilter", out)
        self.assertIn("2. struts2", out)
        self.assertIn("pas en REQUEST : AuditFilter", out)
        self.assertIn("/WEB-INF/jsp/login.jsp", out)
        self.assertIn("1. EncodingFilter", self.q("route", "/admin/x.jsp"))
        self.assertIn("AuditFilter", self.q("route", "/admin/login.do", "--dispatcher", "FORWARD").split("Servlet")[0])

    def test_route_servlet(self):
        self.assertIn("Servlet : FeedServlet  com.ex.web.FeedServlet", self.q("route", "/feed/rss"))

    def test_table_par_orm_xml_et_annotation(self):
        out = self.q("table", "app_settings")
        self.assertIn("Entité com.ex.model.Setting -> table app_settings  (orm.xml", out)
        self.assertIn("CREATE TABLE app_settings  src/main/resources/sql/schema.sql:7", out)
        out = self.q("table", "User")
        self.assertIn("table app_user  (@Table", out)
        self.assertIn("unité de persistance « ExPU »", out)
        self.assertIn("UserServiceImpl  src/main/java/com/ex/service/UserServiceImpl.java:30", out)  # SQL à la main

    def test_neighbors_config_et_ressources(self):
        out = self.q("neighbors", "LoginAction")
        self.assertIn("citée en configuration : src/main/resources/app.properties:2  startup.actions", out)
        self.assertIn("route : action /admin/login", out)
        out = self.q("neighbors", "UserServiceImpl")
        self.assertIn("charge la ressource /com/ex/defaults.xml", out)
        self.assertIn("sous-types directs : UserServiceImpl", self.q("neighbors", "UserService"))

    def test_configuration_continuations_et_commentaires(self):
        refs = {(r[2], r[3].split(".")[-1], r[4]) for r in self.g["refs_config"]}
        self.assertIn(("plugins.enabled", "BaseAction", False), refs)
        self.assertIn(("plugins.enabled", "UserServiceImpl", False), refs)  # ligne de continuation
        self.assertIn(("plugins.disabled", "Setting", True), refs)  # commentée
        self.assertIn("EN COMMENTAIRE", self.q("neighbors", "Setting"))

    def test_find(self):
        out = self.q("find", "authenticate")
        self.assertIn("UserService.authenticate", out)
        self.assertIn("UserServiceImpl.authenticate", out)


if __name__ == "__main__":
    unittest.main()
