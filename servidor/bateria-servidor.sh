#!/bin/sh
# Cuidado de la batería del Mi A1 usado como servidor (siempre enchufado).
# - Corta la carga al llegar a MAX y la reanuda al bajar a MIN (no hay control de voltaje en este driver).
# - Avisa por Discord (canal CANAL_AVISOS_ID del .env del bot) si se va la corriente o la batería baja.
# Lo ejecuta bateria-servidor.timer cada 2 minutos, como root.

MAX=80          # % al que se deja de cargar
MIN=60          # % al que se vuelve a cargar
AVISO_BAJA=30   # % por debajo del cual avisa (si no está cargando)
CORRIENTE_MA=700  # mA máximos de carga (más suave para la batería)

B=/sys/class/power_supply/qcom-battery
U=/sys/class/power_supply/qcom-smbchg-usb
ENV=/home/user/bot-pombina/.env
ESTADO=/var/lib/bateria-servidor
mkdir -p "$ESTADO"

cap=$(cat $B/capacity)
usb_status=$(cat $U/status)       # Charging / Full / Discharging / Not charging
enchufado=$(cat $U/online)        # 0 si no hay cargador
temp=$(( $(cat $B/temp) / 10 ))

echo $((CORRIENTE_MA * 1000)) > $U/constant_charge_current 2>/dev/null

avisar() {  # $1 = clave (para no repetir), $2 = texto
    [ -f "$ESTADO/$1" ] && return
    touch "$ESTADO/$1"
    logger -t bateria-servidor "AVISO: $2"
    TOKEN=$(sed -n 's/^DISCORD_TOKEN=//p' "$ENV" 2>/dev/null)
    CANAL=$(sed -n 's/^CANAL_AVISOS_ID=//p' "$ENV" 2>/dev/null)
    [ -n "$TOKEN" ] && [ -n "$CANAL" ] || return
    curl -s -o /dev/null -m 20 -X POST "https://discord.com/api/v10/channels/$CANAL/messages" \
        -H "Authorization: Bot $TOKEN" -H "Content-Type: application/json" \
        --data "{\"content\": \"🔋 Servidor del bot: $2\"}"
}
resolver() { rm -f "$ESTADO/$1"; }

# Histéresis de carga (solo si hay cargador)
if [ "$enchufado" = "1" ]; then
    resolver sin_corriente
    if [ "$cap" -ge "$MAX" ] && [ "$usb_status" != "Discharging" ]; then
        echo 0 > $U/online; logger -t bateria-servidor "carga pausada ($cap%)"
    elif [ "$cap" -le "$MIN" ] && [ "$usb_status" = "Discharging" ]; then
        echo 1 > $U/online; logger -t bateria-servidor "carga reanudada ($cap%)"
    fi
else
    avisar sin_corriente "se ha desenchufado o se ha ido la luz (batería al $cap%)."
fi

# Batería baja: por debajo de MIN debería estar cargando; si baja de AVISO_BAJA algo va mal
if [ "$cap" -lt "$AVISO_BAJA" ]; then
    avisar baja "batería baja: $cap% y no está cargando bien. Revisa el cargador."
elif [ "$cap" -ge $((AVISO_BAJA + 10)) ]; then
    resolver baja
fi

# Temperatura alta (riesgo de hinchado)
if [ "$temp" -ge 45 ]; then
    avisar caliente "batería caliente: $temp °C."
elif [ "$temp" -le 40 ]; then
    resolver caliente
fi
