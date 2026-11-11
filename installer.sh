#!/data/data/com.termux/files/usr/bin/bash
# Installation dans Termux (Android). À lancer une seule fois, avec Internet :
#   bash installer.sh            -> installation de base + modèle 1.5B
#   bash installer.sh --complet  -> + Java/Kotlin pour vérifier en compilant (~500 Mo de plus)
set -e
cd "$(dirname "$0")"

echo "== 1/4 Paquets Termux =="
pkg update -y
pkg install -y git python

echo "== 2/4 Moteur IA (llama.cpp) =="
if ! command -v llama-server >/dev/null; then
  # Paquet précompilé Termux s'il existe, sinon compilation (~10-20 min sur téléphone).
  if ! pkg install -y llama-cpp 2>/dev/null || ! command -v llama-server >/dev/null; then
    pkg install -y clang cmake
    [ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp
    cmake -S llama.cpp -B llama.cpp/build -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
    cmake --build llama.cpp/build --target llama-server -j 4
  fi
fi

if [ "$1" = "--complet" ]; then
  echo "== Option : Java + Kotlin pour --compiler =="
  pkg install -y openjdk-17 kotlin || echo "(kotlin indisponible : seule la vérification légère sera faite)"
fi

echo "== 3/4 Modèle (le seul téléchargement lourd) =="
python -m ia telecharger coder-1.5b

echo "== 4/4 Raccourci 'ia' =="
cat > "$PREFIX/bin/ia" <<EOS
#!/data/data/com.termux/files/usr/bin/bash
cd "$(pwd)" && exec python -m ia "\$@"
EOS
chmod +x "$PREFIX/bin/ia"

echo
echo "Installé. Ensuite, sans Internet :"
echo "  ia serveur                         # démarre l'IA"
echo "  ia corriger toncompte/tondepot \"l'app plante au clic sur Valider\""
