#!/bin/bash
# Stub – neměnit. Stáhne aktuální skripty a předá řízení Scripts/start.sh,
# který si sám hlídá i nové verze appky (binárky) včetně zálohy a rollbacku.
DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$DIR/AktualizovatStitky.command" ] && bash "$DIR/AktualizovatStitky.command" < /dev/null
[ -f "$DIR/Scripts/start.sh" ] && exec bash "$DIR/Scripts/start.sh"
exec "$DIR/CteckaStitkySW"
