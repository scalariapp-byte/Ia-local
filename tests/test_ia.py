"""Tests sans vrai modèle : un faux serveur imite llama-server."""
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ia import agent, config, llm, modifs, verif, depot

KOTLIN_BUG = """package com.exemple

class Panier {
    private val articles = mutableListOf<Int>()

    fun total(): Int {
        var somme = 0
        for (i in 0..articles.size) {
            somme += articles[i]
        }
        return somme
    }
}
"""

MAUVAISE = """Erreur d'indice.

FICHIER: app/Panier.kt
<<<<<<< AVANT
        for (i in 0..articles.size) {
=======
        for (i in 0..articles.size) {{
>>>>>>> APRES
"""

BONNE = """La boucle va jusqu'à size inclus : IndexOutOfBounds.

FICHIER: app/Panier.kt
<<<<<<< AVANT
for (i in 0..articles.size) {
=======
for (i in articles.indices) {
>>>>>>> APRES
"""


class FauxServeur(BaseHTTPRequestHandler):
    reponses: list = []
    recus: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FauxServeur.recus.append(corps)
        texte = FauxServeur.reponses.pop(0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i in range(0, len(texte), 20):
            d = {"choices": [{"delta": {"content": texte[i:i + 20]}}]}
            self.wfile.write(f"data: {json.dumps(d)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def depot_test(tmp: Path) -> Path:
    d = tmp / "projet"
    (d / "app").mkdir(parents=True)
    (d / "app" / "Panier.kt").write_text(KOTLIN_BUG)
    (d / "app" / "Autre.kt").write_text("class Autre { fun x() = 1 }\n")
    for cmd in (["init", "-q"], ["add", "."],
                ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git", *cmd], cwd=d, check=True)
    return d


class TestModifs(unittest.TestCase):
    def test_extraction(self):
        b = modifs.extraire_blocs(BONNE)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].fichier, "app/Panier.kt")

    def test_application_tolere_indentation(self):
        with tempfile.TemporaryDirectory() as t:
            d = depot_test(Path(t))
            nouveaux, err = modifs.appliquer(d, modifs.extraire_blocs(BONNE))
            self.assertEqual(err, [])
            contenu = list(nouveaux.values())[0]
            self.assertIn("        for (i in articles.indices) {", contenu)

    def test_refuse_chemin_hors_depot(self):
        with tempfile.TemporaryDirectory() as t:
            d = depot_test(Path(t))
            b = [modifs.Bloc("../../etc/passwd", "", "x")]
            _, err = modifs.appliquer(d, b)
            self.assertTrue(err)


class TestBouclesModele(unittest.TestCase):
    def test_ignore_blocs_inutiles(self):
        texte = BONNE + "\nFICHIER: app/Panier.kt\n<<<<<<< AVANT\nreturn somme\n=======\nreturn somme\n>>>>>>> APRES\n" + BONNE
        self.assertEqual(len(modifs.extraire_blocs(texte)), 1)

    def test_detecte_repetition(self):
        phrase = "Cause du bug : La boucle for dans la méthode total() utilise i comme index, mais elle doit utiliser articles.size.\n"
        self.assertTrue(llm.tourne_en_rond("Début.\n" + phrase * 3))

    def test_pas_de_faux_positif_avant_apres(self):
        code = "\n".join(f"        val ligne{i} = calcul({i}) + autre({i})" for i in range(8))
        texte = f"CAUSE: x\n\nFICHIER: a.kt\n<<<<<<< AVANT\n{code}\nreturn 1\n=======\n{code}\nreturn 2\n>>>>>>> APRES\n"
        for i in range(1, len(texte) + 1):
            self.assertFalse(llm.tourne_en_rond(texte[:i]))

    def test_fin_detectee(self):
        self.assertTrue(agent._reponse_complete(BONNE + "\nFIN"))
        self.assertFalse(agent._reponse_complete(BONNE))


class TestVerif(unittest.TestCase):
    def test_equilibre(self):
        self.assertIsNone(verif.equilibre(KOTLIN_BUG))
        self.assertIsNotNone(verif.equilibre("fun a() { if (x) {{ }"))
        self.assertIsNone(verif.equilibre('val s = "}" // {\n/* ( */ val t = \'{\''))


class TestSelection(unittest.TestCase):
    def test_choisit_fichier_pertinent(self):
        with tempfile.TemporaryDirectory() as t:
            d = depot_test(Path(t))
            f = depot.selectionner(d, depot.lister_fichiers(d), "bug dans le total du panier", 10_000)
            self.assertEqual(f[0].name, "Panier.kt")


class TestBoucleCorrection(unittest.TestCase):
    def test_reessaie_puis_committe(self):
        serveur = HTTPServer(("127.0.0.1", 0), FauxServeur)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        config.URL_SERVEUR = f"http://127.0.0.1:{serveur.server_port}"
        FauxServeur.reponses = [MAUVAISE, BONNE]
        FauxServeur.recus = []
        try:
            with tempfile.TemporaryDirectory() as t:
                d = depot_test(Path(t))
                subprocess.run(["git", "config", "user.email", "t@t"], cwd=d)
                subprocess.run(["git", "config", "user.name", "t"], cwd=d)
                ok = agent.corriger(str(d), "plantage dans total du panier", demander=lambda _: "o")
                self.assertTrue(ok)
                # Le 2e appel contient l'erreur de vérification du 1er.
                self.assertIn("refusée", FauxServeur.recus[1]["messages"][-1]["content"])
                self.assertIn("articles.indices", (d / "app/Panier.kt").read_text())
                branche = subprocess.run(["git", "branch", "--show-current"], cwd=d,
                                         capture_output=True, text=True).stdout.strip()
                self.assertTrue(branche.startswith("ia/"))
        finally:
            serveur.shutdown()


if __name__ == "__main__":
    unittest.main()
