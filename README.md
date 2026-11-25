# 🛩️ Pombiña Bot en un Xiaomi Mi A1

Bot de Discord para un club de aeromodelismo que **da el parte de viento de la pista**, funcionando 24/7 en un **móvil viejo (Xiaomi Mi A1, 2017) reconvertido en servidor Linux** con [postmarketOS / Nura](https://nura.eco).

Sin Raspberry Pi, sin VPS, sin cuotas: un móvil del cajón, enchufado y conectado por WiFi.

```
┌──────────────────────────┐        WiFi         ┌───────────────┐
│ Xiaomi Mi A1             │ ──────────────────▶ │  Discord      │
│  lk2nd → postmarketOS    │                     │  #parte-de-   │
│  systemd                 │ ◀── Open-Meteo ──── │   viento      │
│  ├─ pombina-bot (Python) │                     │  #servidor    │
│  ├─ bateria-servidor     │                     └───────────────┘
│  ├─ servidor-sin-reposo  │
│  └─ reinicio-nocturno    │
└──────────────────────────┘
```

## Qué hace el bot

| | |
|---|---|
| 🌅 **Parte diario** | Cada mañana (07:30) publica el viento hora a hora en la pista, solo en horas de luz, con un resumen que destaca el mejor rato para volar. |
| ⭐ **Aviso de buen rato** | Cada hora revisa la previsión; si aparece un rato "de maravilla" que no estaba en el parte, lo avisa. |
| `/viento` | Viento ahora y en las próximas horas. |
| `/parte [día]` | Parte completo de hoy, mañana o cualquier día de la semana (hasta 7 días). |
| `/finde` | Parte del sábado y del domingo juntos. |

Los criterios son los de la pista (orientación 07/25, límites de viento medio, rachas, viento cruzado, racheo y lluvia) y se ajustan al principio de [`bot/viento.py`](bot/viento.py). La previsión viene de [Open-Meteo](https://open-meteo.com) (gratis, sin clave), con reintentos si el servicio falla un momento.

## Qué hace el servidor

- **Nunca duerme**: el móvil se reiniciaba cada vez que la interfaz intentaba suspenderlo. Un servicio mantiene un *wakelock* permanente y la suspensión de systemd está bloqueada ([`servidor/servidor-sin-reposo.service`](servidor/servidor-sin-reposo.service)).
- **Cuida la batería** (siempre enchufado = riesgo de que se hinche): el driver de carga no deja fijar voltaje ni umbral, así que un script **corta la carga al 80 % y la reanuda al 60 %**, con corriente de carga reducida a 700 mA ([`servidor/bateria-servidor.sh`](servidor/bateria-servidor.sh), cada 2 min con un *timer* de systemd).
- **Avisa por Discord** en un canal privado `#servidor` si se va la luz o se desenchufa, si la batería baja del 30 % o si pasa de 45 °C.
- **Se reinicia cada noche** a las 04:00 (hora de Madrid) para mantenerse fresco; tarda ~1 minuto y todo vuelve solo ([`servidor/reinicio-nocturno.timer`](servidor/reinicio-nocturno.timer)). Solo lo hace si lleva más de 1 h encendido, para evitar bucles si el reloj va mal.
- **SSH solo con llave** (sin contraseñas ni root).
- **Arranca solo**: si se reinicia, el bot vuelve a estar en línea sin tocar nada.

## Hardware y software

| | |
|---|---|
| Móvil | Xiaomi Mi A1 (`tissot`), Snapdragon 625 (MSM8953), 4 GB RAM |
| Cargador de arranque | [lk2nd](https://github.com/msm8916-mainline/lk2nd) (en la partición `boot_b`) |
| Sistema | postmarketOS v26.06 (ahora llamado Nura), imagen genérica `qcom-msm8953`, kernel mainline 7.0, systemd |
| Bot | Python 3.14 + [discord.py](https://discordpy.readthedocs.io/) 2.7 |
| Consumo | ~350 MB de RAM en total, CPU casi a cero |

## Estructura

```
bot/          El bot de Discord (bot.py, viento.py) y su servicio systemd
servidor/     Servicios del móvil: sin reposo, cuidado de batería, SSH solo con llave
herramientas/ img2simg.py (convertir imágenes a formato sparse, ver la guía)
docs/         Guía completa para convertir el Mi A1 en servidor
```

## Instalación

1. **Convertir el móvil en servidor** → [docs/instalacion-mi-a1.md](docs/instalacion-mi-a1.md) (desbloqueo, lk2nd, postmarketOS, red, SSH, y todos los tropiezos de Windows que hubo por el camino).
2. **Crear el bot en Discord**: [discord.com/developers/applications](https://discord.com/developers/applications) → New Application → *Bot* → *Reset Token*. En *OAuth2 → URL Generator*: scopes `bot` + `applications.commands`; permisos `View Channels`, `Send Messages`, `Embed Links` (y `Manage Channels` si quieres que cree `#servidor`).
3. **Instalar el bot en el móvil** (por SSH):

   ```bash
   scp -r bot usuario@movil:~/bot-pombina
   ssh usuario@movil
   cd ~/bot-pombina
   sudo apk add python3 py3-pip py3-virtualenv
   python3 -m venv venv && venv/bin/pip install -r requirements.txt
   cp .env.example .env && chmod 600 .env     # rellena SERVIDOR_ID y CANAL_PARTE_ID
   sed "s/USUARIO/$(whoami)/g" pombina-bot.service | sudo tee /etc/systemd/system/pombina-bot.service
   sudo systemctl daemon-reload && sudo systemctl enable pombina-bot
   ./poner-token.sh                           # pide el token sin mostrarlo y arranca el bot
   venv/bin/python crear-canal-servidor.py    # opcional: canal privado de avisos
   ```

4. **Servicios del servidor**:

   ```bash
   sudo install -m 755 servidor/bateria-servidor.sh /usr/local/bin/
   sudo cp servidor/*.service servidor/*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now servidor-sin-reposo.service bateria-servidor.timer reinicio-nocturno.timer
   sudo systemctl mask sleep.target suspend.target
   sudo cp servidor/10-solo-llave.conf /etc/ssh/sshd_config.d/   # ¡antes, comprueba que entras con llave!
   ```

Comandos útiles: `systemctl status pombina-bot`, `journalctl -u pombina-bot -f`, `journalctl -t bateria-servidor`.

## Seguridad

El token del bot solo vive en `.env` dentro del móvil (`chmod 600`, ignorado por git). `poner-token.sh` lo pide sin mostrarlo en pantalla, y los scripts lo leen de ahí sin imprimirlo.

## Licencia

[MIT](LICENSE)
