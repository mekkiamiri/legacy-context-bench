import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))

import score  # noqa: E402


class TestQuestions(unittest.TestCase):
    def test_le_fichier_de_questions_est_valide(self):
        self.assertEqual(score.verifier(score.charger_questions()), [])

    def test_les_reponses_de_reference_ont_20_sur_20(self):
        data = score.charger_questions()
        reference = {q["id"]: q["reponse"] for q in data["questions"]}
        self.assertEqual(score.noter(data, reference)["total"], 1.0)

    def test_aucune_reponse_donne_zero(self):
        self.assertEqual(score.noter(score.charger_questions(), {})["total"], 0.0)


class TestNotation(unittest.TestCase):
    Q = {"criteres": [["eclipselink"], ["orm.xml", "xml"]]}

    def test_un_critere_sur_deux(self):
        self.assertEqual(score.noter_reponse(self.Q, "Roller utilise EclipseLink"), 0.5)

    def test_casse_ignoree_et_synonymes(self):
        self.assertEqual(score.noter_reponse(self.Q, "ECLIPSELINK, mapping en XML"), 1.0)

    def test_doublon_d_id_detecte(self):
        data = score.charger_questions()
        data["questions"][1]["id"] = data["questions"][0]["id"]
        self.assertIn("ids en double", score.verifier(data))


if __name__ == "__main__":
    unittest.main()
