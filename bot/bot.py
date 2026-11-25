"""
Bot de Discord del Club Aeromodelismo A Pombiña.

- Parte de viento cada mañana en #parte-de-viento.
- Aviso cuando a lo largo del día aparece un rato "de maravilla" para volar.
- Comandos: /viento (ahora y próximas horas) y /parte (hoy o mañana).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import viento

AQUI = Path(__file__).resolve().parent
load_dotenv(AQUI / ".env")

TOKEN = os.environ["DISCORD_TOKEN"]
SERVIDOR_ID = int(os.environ["SERVIDOR_ID"])
CANAL_PARTE_ID = int(os.environ["CANAL_PARTE_ID"])
HORA_PARTE = os.environ.get("HORA_PARTE", "07:30")
ROL_AVISO_ID = int(os.environ.get("ROL_AVISO_ID") or 0)   # opcional: rol a mencionar en los avisos
TZ = ZoneInfo("Europe/Madrid")
ESTADO = AQUI / "estado.json"

hh, mm = map(int, HORA_PARTE.split(":"))
T_PARTE = time(hh, mm, tzinfo=TZ)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pombina")


# ── Estado (para no repetir mensajes tras un reinicio) ─────────────────
def leer_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar_estado(e: dict) -> None:
    hoy = datetime.now(TZ).date().isoformat()
    e["avisados"] = {k: v for k, v in e.get("avisados", {}).items() if k >= hoy}  # limpiar días pasados
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def se_solapan(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


# ── Bot ────────────────────────────────────────────────────────────────
class BotPombina(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.http_meteo: aiohttp.ClientSession | None = None
        self.estado = leer_estado()

    async def setup_hook(self) -> None:
        self.http_meteo = aiohttp.ClientSession(headers={"User-Agent": "BotPombina/1.0"})
        guild = discord.Object(id=SERVIDOR_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)          # comandos disponibles al momento en el servidor del club
        self.parte_diario.start()
        self.vigilar.start()

    async def close(self) -> None:
        if self.http_meteo:
            await self.http_meteo.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Conectado como %s", self.user)
        # Si el bot arranca (o se reinicia) por la mañana y aún no ha salido el parte, lo manda ya
        ahora = datetime.now(TZ)
        if T_PARTE.replace(tzinfo=None) <= ahora.time() < time(14) and self.estado.get("parte") != ahora.date().isoformat():
            await self.enviar_parte()

    async def canal(self) -> discord.abc.Messageable:
        return self.get_channel(CANAL_PARTE_ID) or await self.fetch_channel(CANAL_PARTE_ID)

    async def prevision(self, dias: int = 2) -> dict:
        return await viento.pedir_prevision(self.http_meteo, dias)

    # ── Parte de la mañana ──
    async def enviar_parte(self) -> None:
        ahora = datetime.now(TZ)
        hoy = ahora.date()
        if self.estado.get("parte") == hoy.isoformat():
            return
        try:
            prev = await self.prevision()
        except Exception:
            log.exception("No se pudo pedir la previsión para el parte")
            return
        emb = viento.embed_parte(prev, hoy)
        if not emb:
            return
        await (await self.canal()).send(embed=discord.Embed.from_dict(emb))
        # Los ratos buenos que ya salen en el parte no se vuelven a avisar
        avis = [[a, b] for a, b, _ in viento.ventanas_top(prev, hoy, 0)]
        self.estado["parte"] = hoy.isoformat()
        self.estado.setdefault("avisados", {})[hoy.isoformat()] = avis
        guardar_estado(self.estado)
        log.info("Parte enviado (%s)", hoy)

    @tasks.loop(time=T_PARTE)
    async def parte_diario(self) -> None:
        await self.enviar_parte()

    # ── Vigilancia: aviso si aparece un buen rato nuevo ──
    @tasks.loop(minutes=60)
    async def vigilar(self) -> None:
        ahora = datetime.now(TZ)
        hoy = ahora.date()
        if self.estado.get("parte") != hoy.isoformat():
            return                                  # primero el parte de la mañana
        try:
            prev = await self.prevision()
        except Exception:
            log.exception("No se pudo pedir la previsión (vigilancia)")
            return
        # Solo ratos que empiecen al menos dentro de una hora
        ventanas = viento.ventanas_top(prev, hoy, ahora.hour + 1)
        avisados = self.estado.setdefault("avisados", {}).setdefault(hoy.isoformat(), [])
        for ini, fin, det in ventanas:
            if any(se_solapan((ini, fin), tuple(a)) for a in avisados):
                continue
            texto = f"<@&{ROL_AVISO_ID}>" if ROL_AVISO_ID else None
            await (await self.canal()).send(
                content=texto,
                embed=discord.Embed.from_dict(viento.embed_aviso(hoy, ini, fin, det)),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            avisados.append([ini, fin])
            guardar_estado(self.estado)
            log.info("Aviso de buen rato: %s-%s h", ini, fin + 1)

    @parte_diario.before_loop
    @vigilar.before_loop
    async def _esperar(self) -> None:
        await self.wait_until_ready()


bot = BotPombina()


# ── Comandos ───────────────────────────────────────────────────────────
@bot.tree.command(name="viento", description="Viento en la pista ahora y en las próximas horas")
async def cmd_viento(inter: discord.Interaction) -> None:
    await inter.response.defer(thinking=True)
    try:
        prev = await bot.prevision()
    except Exception:
        log.exception("/viento")
        await inter.followup.send("No he podido consultar la previsión ahora mismo. Prueba en un rato. 🙏")
        return
    await inter.followup.send(embed=discord.Embed.from_dict(viento.embed_ahora(prev, datetime.now(TZ))))


DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fecha_de(valor: str) -> date:
    """'hoy', 'manana' o un día de la semana (0=lunes) → la próxima fecha (hoy incluido)."""
    hoy = datetime.now(TZ).date()
    if valor == "hoy":
        return hoy
    if valor == "manana":
        return hoy + timedelta(days=1)
    return hoy + timedelta(days=(int(valor) - hoy.weekday()) % 7)


def titulo_para(d: date) -> str:
    dist = (d - datetime.now(TZ).date()).days
    return "Parte de viento" if dist <= 2 else f"Parte de viento (a {dist} días: puede cambiar)"


async def enviar_partes(inter: discord.Interaction, fechas: list[date], comando: str) -> None:
    await inter.response.defer(thinking=True)
    dias = (max(fechas) - datetime.now(TZ).date()).days + 1
    try:
        prev = await bot.prevision(max(2, dias))
    except Exception:
        log.exception(comando)
        await inter.followup.send("No he podido consultar la previsión ahora mismo. Prueba en un rato. 🙏")
        return
    embeds = [discord.Embed.from_dict(e) for d in fechas if (e := viento.embed_parte(prev, d, titulo=titulo_para(d)))]
    if embeds:
        await inter.followup.send(embeds=embeds)
    else:
        await inter.followup.send("No hay previsión para ese día.")


@bot.tree.command(name="parte", description="Parte de viento completo de un día (hasta una semana)")
@app_commands.describe(dia="¿De qué día?")
@app_commands.choices(dia=[app_commands.Choice(name="hoy", value="hoy"),
                           app_commands.Choice(name="mañana", value="manana")]
                          + [app_commands.Choice(name=n, value=str(i)) for i, n in enumerate(DIAS_SEMANA)])
async def cmd_parte(inter: discord.Interaction, dia: app_commands.Choice[str] | None = None) -> None:
    await enviar_partes(inter, [fecha_de(dia.value if dia else "hoy")], "/parte")


@bot.tree.command(name="finde", description="Parte de viento del sábado y el domingo")
async def cmd_finde(inter: discord.Interaction) -> None:
    hoy = datetime.now(TZ).date()
    fechas = [fecha_de("5"), fecha_de("6")]
    if hoy.weekday() == 6:          # en domingo, solo queda hoy
        fechas = [hoy]
    await enviar_partes(inter, sorted(fechas), "/finde")


if __name__ == "__main__":
    bot.run(TOKEN, log_handler=None)
