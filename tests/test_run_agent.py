"""Lanceur : commande construite pour chaque configuration, et passage complet avec un faux agent."""

import io
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "bench"))

import run_agent  # noqa: E402

MINI = Path(__file__).resolve().parent / "fixtures" / "mini-projet"

# Faux agent : lit la commande d'outil annoncée dans --append-system-prompt, l'exécute comme le ferait
# l'agent via Bash (même environnement), et renvoie sa sortie au format JSON de `claude -p`.
FAUX_AGENT = textwrap.dedent('''\
    #!{python}
    import json, re, shlex, subprocess, sys
    args = sys.argv[1:]
    if args == ["--version"]:
        print("faux-agent 1.0"); sys.exit(0)
    sortie = ""
    if "--append-system-prompt" in args:
        consigne = args[args.index("--append-system-prompt") + 1]
        regle = args[args.index("--allowedTools") + 1]
        cmd = re.search(r"(python3 \\S+\\.py)", consigne).group(1)
        assert regle == "Bash(" + cmd + ":*)", (regle, cmd)
        requete = ["authenticate", "--k", "2"] if "rag_search" in cmd else ["who-calls", "UserServiceImpl.authenticate"]
        p = subprocess.run([sys.executable] + shlex.split(cmd)[1:] + requete, capture_output=True, text=True)
        sortie = p.stdout + p.stderr
    print(json.dumps({{"result": sortie or "pas d'outil", "is_error": False, "num_turns": 1, "total_cost_usd": 0,
                      "usage": {{"input_tokens": 1, "output_tokens": 1}}, "outils": args[args.index("--tools") + 1]}}))
''')


class TestCommande(unittest.TestCase):
    def test_agent_seul_inchange(self):
        cmd = run_agent.commande("1-agent-seul", "Q ?", "m")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")
        self.assertNotIn("--allowedTools", cmd)
        self.assertNotIn("--append-system-prompt", cmd)

    def test_rag_et_graphe_ajoutent_une_seule_commande_bash(self):
        for config, script in (("2-rag", run_agent.RAG_SEARCH), ("3-graphe", run_agent.GRAPH_QUERY)):
            cmd = run_agent.commande(config, "Q ?", None)
            self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob,Bash")
            self.assertEqual(cmd[cmd.index("--allowedTools") + 1], f"Bash(python3 {script}:*)")
            self.assertIn(f"python3 {script} ", cmd[cmd.index("--append-system-prompt") + 1])
            self.assertTrue(script.is_file())
            self.assertTrue(cmd[2].endswith("Question : Q ?"))  # consigne commune inchangée


class TestFauxAgent(unittest.TestCase):
    def test_passage_complet_2_rag_et_3_graphe(self):
        tmp = Path(tempfile.mkdtemp())
        projet = tmp / "projet"
        shutil.copytree(MINI, projet)
        git = ["git", "-C", str(projet), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "x"], check=True)
        commit = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        questions = tmp / "q.json"
        questions.write_text(json.dumps({"cible": {"commit": commit}, "questions": [
            {"id": "X01", "question": "Qui vérifie le mot de passe ?"}]}), encoding="utf-8")
        agent = tmp / "faux-agent"
        agent.write_text(FAUX_AGENT.format(python=sys.executable), encoding="utf-8")
        agent.chmod(agent.stat().st_mode | stat.S_IEXEC)
        for config, attendu in (("2-rag", "UserServiceImpl.java:9-14"), ("3-graphe", "LoginAction.execute")):
            with redirect_stdout(io.StringIO()):
                code = run_agent.main(["--roller", str(projet), "--config", config, "--passes", "1",
                                       "--questions", str(questions), "--agent", str(agent),
                                       "--resultats", str(tmp / "results"), "--contexte", str(tmp / "ctx")])
            self.assertEqual(code, 0)
            reponses = json.loads((tmp / "results" / config / "answers.json").read_text(encoding="utf-8"))
            self.assertIn(attendu, reponses["X01"])
            self.assertEqual(reponses["_meta"]["cli"], "faux-agent 1.0")
            self.assertGreaterEqual(reponses["_meta"]["preparation"]["duree_s"], 0)
            self.assertTrue(any((tmp / "ctx").iterdir()))


if __name__ == "__main__":
    unittest.main()
