"""Configuration : chemins, modèles disponibles, paramètres du serveur."""
import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_MODELES = Path(os.environ.get("IA_MODELES", RACINE / "models"))
DOSSIER_DEPOTS = Path(os.environ.get("IA_DEPOTS", RACINE / "depots"))
DOSSIER_ETAT = Path(os.environ.get("IA_ETAT", RACINE / ".ia"))
FICHIER_MODELES = RACINE / "modeles.json"

URL_SERVEUR = os.environ.get("IA_SERVEUR", "http://127.0.0.1:8080")

# Taille de contexte demandée au serveur (en tokens). 8192 tient dans 8 Go de RAM
# avec un modèle 3B en Q4. Monte à 16384 si tu as 12 Go et un modèle 1.5B.
CONTEXTE = int(os.environ.get("IA_CONTEXTE", "8192"))

# Approximation : 1 token ~ 3,5 caractères de code.
CARACTERES_PAR_TOKEN = 3.5

EXTENSIONS_CODE = {
    ".kt", ".kts", ".java", ".dart", ".xml", ".gradle", ".py", ".js", ".ts",
    ".c", ".cpp", ".h", ".swift", ".go", ".rs",
}
DOSSIERS_IGNORES = {
    ".git", "build", ".gradle", ".idea", "node_modules", ".dart_tool",
    "__pycache__", "generated", ".cxx", "intermediates",
}


def charger_modeles() -> dict:
    with open(FICHIER_MODELES, encoding="utf-8") as f:
        return json.load(f)


def budget_caracteres(reserve_tokens: int = 2500) -> int:
    """Nombre de caractères de code qu'on peut envoyer en laissant de la place à la réponse."""
    return int((CONTEXTE - reserve_tokens) * CARACTERES_PAR_TOKEN)
