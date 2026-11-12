#!/usr/bin/env bash
# Test de référence : recrée un petit projet avec un bug connu et demande à l'IA de le corriger.
# Usage : bash essai.sh            (le serveur doit tourner : ia serveur)
set -e
DOSSIER_IA="$(cd "$(dirname "$0")" && pwd)"
rm -rf ~/test && mkdir -p ~/test/app && cd ~/test
cat > app/Panier.kt << 'KT'
package com.exemple

class Panier {
    private val articles = mutableListOf<Int>()

    fun ajouter(prix: Int) {
        articles.add(prix)
    }

    fun total(): Int {
        var somme = 0
        for (i in 0..articles.size) {
            somme += articles[i]
        }
        return somme
    }
}
KT
git init -q && git add . && git -c user.name=ia -c user.email=ia@local commit -qm "départ"
cd "$DOSSIER_IA"
exec python -m ia corriger ~/test "l'app plante quand on appelle total()" --auto
