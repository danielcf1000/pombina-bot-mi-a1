#!/bin/sh
# Pide el token del bot sin mostrarlo, lo guarda en .env y arranca el bot.
cd "$(dirname "$0")"
printf 'Pega el token del bot y pulsa Intro (no se verá): '
stty -echo; read -r T; stty echo; echo
T=$(printf '%s' "$T" | tr -d '[:space:]')
[ -n "$T" ] || { echo "Token vacío, no cambio nada."; exit 1; }
grep -v '^DISCORD_TOKEN=' .env > .env.tmp && { echo "DISCORD_TOKEN=$T"; cat .env.tmp; } > .env && rm .env.tmp && chmod 600 .env
echo "Token guardado. Arrancando el bot..."
sudo systemctl restart pombina-bot; sleep 10
journalctl -u pombina-bot -n 5 --no-pager -o cat
