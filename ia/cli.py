"""Ligne de commande : python -m ia <commande> ..."""
import argparse
import sys

from . import agent, config, llm, serveur


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ia", description="IA locale d'analyse et de correction de code.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("modeles", help="Liste les modèles disponibles")

    s = sub.add_parser("telecharger", help="Télécharge un modèle (seule étape en ligne)")
    s.add_argument("modele", nargs="?")

    s = sub.add_parser("serveur", help="Démarre le moteur IA avec un modèle")
    s.add_argument("modele", nargs="?")
    s.add_argument("--premier-plan", action="store_true")

    sub.add_parser("arret", help="Arrête le moteur IA")

    def commun(s):
        s.add_argument("depot", help="utilisateur/depot, URL GitHub ou dossier local")
        s.add_argument("demande", nargs="?", default="", help="Ce que tu veux (entre guillemets)")
        s.add_argument("-f", "--fichier", action="append", help="Forcer un fichier (répétable)")

    s = sub.add_parser("analyser", help="Liste les problèmes du code, sans rien modifier")
    commun(s)

    s = sub.add_parser("corriger", help="Corrige, vérifie, puis committe sur une branche ia/...")
    commun(s)
    s.add_argument("--auto", action="store_true", help="Ne pas demander confirmation")
    s.add_argument("--compiler", action="store_true", help="Vérifier aussi en compilant (lent)")
    s.add_argument("--pousser", action="store_true", help="Pousser la branche sur GitHub")
    s.add_argument("--essais", type=int, default=3)

    s = sub.add_parser("instructions", help="Rédige des instructions pour une autre IA")
    commun(s)

    s = sub.add_parser("discuter", help="Discussion libre (optionnel : sur un dépôt)")
    s.add_argument("depot", nargs="?")

    a = p.parse_args(argv)
    defaut = config.charger_modeles()["defaut"]
    try:
        if a.cmd == "modeles":
            for nom, m in config.charger_modeles()["modeles"].items():
                present = "✓" if serveur.chemin_modele(nom).exists() else " "
                print(f"[{present}] {nom:12} {m['taille']:8} {m['note']}")
        elif a.cmd == "telecharger":
            serveur.telecharger(a.modele or defaut)
        elif a.cmd == "serveur":
            serveur.demarrer(a.modele or defaut, arriere_plan=not a.premier_plan)
        elif a.cmd == "arret":
            serveur.arreter()
        elif a.cmd == "analyser":
            agent.analyser(a.depot, a.demande, a.fichier)
        elif a.cmd == "corriger":
            ok = agent.corriger(a.depot, a.demande, a.fichier, auto=a.auto,
                                compiler=a.compiler, pousser=a.pousser, essais=a.essais)
            return 0 if ok else 1
        elif a.cmd == "instructions":
            if not a.demande:
                p.error("instructions : précise l'objectif entre guillemets")
            print(agent.instructions(a.depot, a.demande, a.fichier))
        elif a.cmd == "discuter":
            agent.discussion(a.depot)
    except (llm.ErreurLLM, RuntimeError) as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 130
    return 0
