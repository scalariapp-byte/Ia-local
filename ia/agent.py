"""Le cerveau : enchaîne lecture du dépôt -> analyse -> correction -> vérification -> commit."""
from pathlib import Path

from . import config, depot, llm, modifs, verif

SYSTEME = (
    "Tu es un expert en développement Android (Kotlin, Java) et en correction de bugs. "
    "Tu réponds en français, de façon brève et précise. Tu ne modifies que ce qui est "
    "nécessaire. Tu n'inventes jamais de fichier ni de fonction qui n'existe pas dans le code fourni."
)

ORDRE = (
    "Traite les problèmes dans cet ordre logique : "
    "1) erreurs de compilation/syntaxe, 2) plantages (null, index, cycle de vie Android, threads), "
    "3) bugs de logique, 4) failles de sécurité, 5) performances, 6) lisibilité."
)

FORMAT_CORRECTION = """Pour CHAQUE modification, utilise EXACTEMENT ce format :

FICHIER: chemin/relatif/du/fichier.kt
<<<<<<< AVANT
(lignes copiées à l'identique depuis le fichier, 2 à 10 lignes, suffisantes pour être uniques)
=======
(lignes corrigées)
>>>>>>> APRES

Règles : copie le bloc AVANT caractère pour caractère. Un bloc par endroit modifié.
Avant les blocs, écris en 1 à 3 phrases la cause du bug."""


def _contexte(dossier: Path, demande: str, fichiers_imposes: list[str] | None):
    tous = depot.lister_fichiers(dossier)
    if not tous:
        raise RuntimeError(f"Aucun fichier de code trouvé dans {dossier}")
    budget = config.budget_caracteres()
    if fichiers_imposes:
        choisis = [(dossier / f).resolve() for f in fichiers_imposes]
        manquants = [str(f) for f in choisis if not f.exists()]
        if manquants:
            raise RuntimeError("Fichiers introuvables : " + ", ".join(manquants))
    else:
        choisis = depot.selectionner(dossier, tous, demande, budget)
    plan = depot.arborescence(dossier, tous)
    budget -= len(plan)
    blocs, envoyes, total = [], [], 0
    for f in choisis:
        texte = f.read_text(encoding="utf-8", errors="replace")
        if total + len(texte) > budget:
            if not blocs:  # fichier unique trop gros : on tronque plutôt que rien
                texte = texte[:budget] + "\n// ... (tronqué : fichier trop long pour le modèle)"
            else:
                continue
        total += len(texte)
        rel = f.relative_to(dossier.resolve())
        envoyes.append(rel)
        blocs.append(f"### FICHIER: {rel}\n```\n{texte}\n```")
    print(f"Fichiers envoyés au modèle ({total} caractères) :")
    for rel in envoyes:
        print("  -", rel)
    return f"Structure du projet :\n{plan}\n\n" + "\n\n".join(blocs)


def analyser(cible: str, demande: str = "", fichiers=None) -> str:
    dossier = depot.recuperer(cible)
    ctx = _contexte(dossier, demande, fichiers)
    question = demande or "Analyse ce code et liste les bugs et problèmes."
    msg = (
        f"{ctx}\n\n{question}\n\n{ORDRE}\n"
        "Pour chaque problème : fichier, ligne approximative, gravité (critique/moyen/faible), "
        "explication en une phrase, correction proposée en une phrase. Ne réécris pas le code."
    )
    return llm.discuter([{"role": "system", "content": SYSTEME}, {"role": "user", "content": msg}])


def corriger(cible: str, demande: str = "", fichiers=None, auto=False, compiler=False,
             pousser=False, essais=3, demander=input) -> bool:
    """Boucle de correction autonome : le modèle propose, l'outil vérifie, et si la
    vérification échoue, l'erreur est renvoyée au modèle pour qu'il se corrige."""
    dossier = depot.recuperer(cible)
    ctx = _contexte(dossier, demande, fichiers)
    tache = demande or "Trouve le bug le plus important et corrige-le."
    messages = [
        {"role": "system", "content": SYSTEME},
        {"role": "user", "content": f"{ctx}\n\nTâche : {tache}\n\n{ORDRE}\n\n{FORMAT_CORRECTION}"},
    ]
    nouveaux = {}
    for essai in range(1, essais + 1):
        print(f"\n=== Essai {essai}/{essais} ===")
        reponse = llm.discuter(messages, temperature=0.1 if essai == 1 else 0.4)
        messages.append({"role": "assistant", "content": reponse})
        blocs = modifs.extraire_blocs(reponse)
        if not blocs:
            probleme = "Aucun bloc de modification trouvé. Respecte strictement le format FICHIER/AVANT/APRES."
            erreurs = [probleme]
        else:
            nouveaux, erreurs = modifs.appliquer(dossier, blocs)
            if not erreurs and not nouveaux:
                erreurs = ["Les blocs ne modifient rien."]
            if not erreurs:
                erreurs = verif.verifier(nouveaux, compiler=compiler)
        if not erreurs:
            break
        print("\n[Vérification échouée]\n" + "\n".join(erreurs))
        messages.append({"role": "user", "content":
                         "Ta correction est refusée :\n" + "\n".join(erreurs) +
                         "\nRecommence en corrigeant ces problèmes, même format."})
    else:
        print("\nÉchec : aucune correction valide après", essais, "essais. Rien n'a été modifié.")
        return False

    print("\n=== Correction proposée ===\n" + modifs.diff(dossier, nouveaux))
    if not auto:
        if demander("Appliquer et committer ? [o/N] ").strip().lower() not in {"o", "oui", "y"}:
            print("Annulé, rien n'a été modifié.")
            return False
    branche = depot.creer_branche(dossier, tache)
    modifs.ecrire(nouveaux)
    resume = tache.splitlines()[0][:60]
    depot.commit(dossier, list(nouveaux), f"IA locale : {resume}")
    print(f"Commit créé sur la branche {branche} dans {dossier}")
    if pousser:
        try:
            depot.pousser(dossier)
            print("Branche poussée sur GitHub.")
        except RuntimeError as e:
            print(f"Push impossible (hors ligne ?), réessaie plus tard avec : git push. {e}")
    return True


def instructions(cible: str, objectif: str, fichiers=None) -> str:
    """Rédige des instructions précises pour une autre IA (Claude, ChatGPT, une autre IA locale...).
    Seul le texte produit est destiné à être envoyé : tu choisis ce que tu partages."""
    dossier = depot.recuperer(cible)
    ctx = _contexte(dossier, objectif, fichiers)
    msg = (
        f"{ctx}\n\nObjectif : {objectif}\n\n"
        "Rédige des instructions pour une AUTRE IA de programmation qui devra réaliser cet objectif. "
        "Structure obligatoire :\n"
        "## Contexte (projet, technologies, fichiers concernés)\n"
        "## Tâche (précise, vérifiable)\n"
        "## Contraintes (ce qu'il ne faut pas casser ou modifier)\n"
        "## Étapes (numérotées)\n"
        "## Critères de réussite (comment vérifier que c'est fait)\n"
        "Ne recopie pas de grands blocs de code : cite les noms de fichiers, classes et fonctions."
    )
    texte = llm.discuter([{"role": "system", "content": SYSTEME}, {"role": "user", "content": msg}])
    config.DOSSIER_ETAT.mkdir(parents=True, exist_ok=True)
    sortie = config.DOSSIER_ETAT / "instructions.md"
    sortie.write_text(texte, encoding="utf-8")
    print(f"\nInstructions enregistrées dans {sortie}")
    return texte


def discussion(cible: str | None = None) -> None:
    messages = [{"role": "system", "content": SYSTEME}]
    if cible:
        dossier = depot.recuperer(cible)
        tous = depot.lister_fichiers(dossier)
        messages.append({"role": "user", "content":
                         "Structure du projet sur lequel on travaille :\n" + depot.arborescence(dossier, tous)})
        messages.append({"role": "assistant", "content": "Compris, j'ai la structure du projet."})
    print("Discussion (ligne vide ou 'fin' pour quitter).")
    while True:
        try:
            q = input("\nToi > ").strip()
        except EOFError:
            break
        if q in {"", "fin", "quit", "exit"}:
            break
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": llm.discuter(messages)})
        # Garde la conversation dans le contexte : on oublie les vieux échanges.
        while sum(len(m["content"]) for m in messages) > config.budget_caracteres() and len(messages) > 4:
            del messages[1:3]
