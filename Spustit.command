#!/bin/bash
# Spustí štítkovou appku. Před startem stáhne nové verze tiskových skriptů
# (vzhled štítků, dovozci, scan mód) – takže změny pushnuté z MacBooku se
# na iMac dostanou samy při příštím spuštění. Bez internetu se stahování
# jen přeskočí a appka startuje se stávající verzí.
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$DIR/AktualizovatStitky.command" ]; then
  # < /dev/null: updater pak nečeká na Enter a appka naskočí hned
  bash "$DIR/AktualizovatStitky.command" < /dev/null
fi

exec "$DIR/CteckaStitkySW"
