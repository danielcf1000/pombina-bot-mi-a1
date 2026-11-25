"""Crea el canal privado #servidor con el token del bot (leído del .env, nunca se imprime)
y guarda su id en CANAL_AVISOS_ID. Uso en el móvil: ~/bot-pombina/venv/bin/python crear-canal-servidor.py"""
import json, re, urllib.request, urllib.error
from pathlib import Path

ENV = Path.home() / "bot-pombina" / ".env"
txt = ENV.read_text()
cfg = dict(re.findall(r"^(\w+)=(.*)$", txt, re.M))
token, guild = cfg["DISCORD_TOKEN"], cfg["SERVIDOR_ID"]
H = {"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": "PombinaBot (servidor, 1.0)"}

def api(method, path, body=None):
    req = urllib.request.Request(f"https://discord.com/api/v10{path}", method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

if cfg.get("CANAL_AVISOS_ID"):
    print("Ya hay CANAL_AVISOS_ID:", cfg["CANAL_AVISOS_ID"]); raise SystemExit

me = api("GET", "/users/@me")
existentes = [c for c in api("GET", f"/guilds/{guild}/channels") if c.get("name") == "servidor" and c["type"] == 0]
if existentes:
    canal = existentes[0]
    print("Canal #servidor ya existía:", canal["id"])
else:
    VIEW, SEND = 1 << 10, 1 << 11
    try:
        canal = api("POST", f"/guilds/{guild}/channels", {
            "name": "servidor", "type": 0,
            "topic": "Avisos automáticos del móvil servidor del bot (batería, corriente)",
            "permission_overwrites": [
                {"id": guild, "type": 0, "deny": str(VIEW)},                 # @everyone no lo ve
                {"id": me["id"], "type": 1, "allow": str(VIEW | SEND)},      # el bot sí
            ]})
        print("Canal #servidor creado:", canal["id"])
    except urllib.error.HTTPError as e:
        print("ERROR", e.code, e.read().decode()[:300]); raise SystemExit(1)

ENV.write_text(re.sub(r"^CANAL_AVISOS_ID=.*$", f"CANAL_AVISOS_ID={canal['id']}", txt, flags=re.M))
api("POST", f"/channels/{canal['id']}/messages",
    {"content": "🔋 Canal de avisos del servidor listo. Aquí avisaré si se va la luz, la batería baja o se calienta."})
print("CANAL_AVISOS_ID guardado y mensaje de prueba enviado.")
