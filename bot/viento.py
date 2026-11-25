"""
Lógica del viento en la pista de A Pombiña.

Mismos criterios que la app "Viento en la pista" de la web
(aeromodelismonaron.com/viento), más la lluvia.
Este módulo no sabe nada de Discord: recibe la previsión de Open-Meteo
y devuelve datos y "embeds" (diccionarios) listos para enviar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

import asyncio
import aiohttp

# ── Ajustes de la pista ────────────────────────────────────────────────
LAT, LON = 43.53066, -8.10051
RUMBO = 68            # pista 07/25
L_VIENTO = 20         # km/h, viento medio
L_RACHA = 30          # km/h
L_CRUZADO = 12        # km/h
L_RACHEO = 12         # km/h (racha − medio)
MARGEN = 0.50         # +50 % sobre el límite → "no recomendable"

# "De maravilla": volable, sin lluvia y muy por debajo de los límites
TOP_VIENTO = L_VIENTO * 0.6      # 12
TOP_RACHA = L_RACHA * 0.67       # 20
TOP_CRUZADO = L_CRUZADO * 0.6    # 7.2
TOP_RACHEO = L_RACHEO * 0.75     # 9

URL_WEB = "https://aeromodelismonaron.com/viento/"
COLORES = {0: 0x4FC1C6, 1: 0xF7E463, 2: 0xE8452C}
EMOJI = {0: "🟢", 1: "🟡", 2: "🔴"}
PUNTOS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
          "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# ── Previsión ──────────────────────────────────────────────────────────
async def pedir_prevision(session: aiohttp.ClientSession, dias: int = 2) -> dict:
    v = "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
    params = {
        "latitude": LAT, "longitude": LON,
        "current": v,
        "hourly": f"{v},precipitation_probability,precipitation",
        "daily": "sunrise,sunset",
        "wind_speed_unit": "kmh", "timezone": "Europe/Madrid",
        "forecast_days": dias,
    }
    # Open-Meteo a veces responde 503/429 un momento: reintentar antes de rendirse
    for intento in range(4):
        try:
            async with session.get("https://api.open-meteo.com/v1/forecast", params=params,
                                   timeout=aiohttp.ClientTimeout(total=20)) as r:
                r.raise_for_status()
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if intento == 3:
                raise
            await asyncio.sleep(2 * (intento + 1))


# ── Cálculo ────────────────────────────────────────────────────────────
def r(x: float) -> int:
    """Redondeo normal (14,5 → 15), igual que en la web."""
    return int(math.floor(x + 0.5))


def norm(d: float) -> float:
    return d % 360


def pista(h: float) -> str:
    n = r(norm(h) / 10)
    return f"{n or 36:02d}"


def punto(d: float) -> str:
    return PUNTOS[r(norm(d) / 22.5) % 16]


@dataclass
class Hora:
    hora: int
    viento: float
    racha: float
    dir: float
    prob: int
    mm: float
    nivel: int = 0          # 0 volable, 1 precaución, 2 no recomendable
    top: bool = False       # de maravilla
    pista: str = ""
    cruzado: float = 0.0
    lluvia: str = ""

    @property
    def icono(self) -> str:
        return "⭐" if self.top else EMOJI[self.nivel]


def valorar(viento, racha, dir_, prob=0, mm=0.0, hora=0) -> Hora:
    h = Hora(hora, viento, racha, dir_, int(prob or 0), float(mm or 0))
    # Cabecera con más viento de cara
    mejor = None
    for cab in (norm(RUMBO), norm(RUMBO + 180)):
        a = math.radians(dir_ - cab)
        cara, cruz = viento * math.cos(a), abs(viento * math.sin(a))
        if mejor is None or cara > mejor[1]:
            mejor = (cab, cara, cruz)
    h.pista, h.cruzado = pista(mejor[0]), mejor[2]
    racheo = racha - viento
    pruebas = [(viento, L_VIENTO), (racha, L_RACHA), (h.cruzado, L_CRUZADO), (racheo, L_RACHEO)]
    # Deriva hacia la zona de pilotos y la carretera
    hacia = viento * math.cos(math.radians(dir_ + 180 - norm(RUMBO + 90)))
    if hacia < 0:
        pruebas.append((-hacia, L_CRUZADO * 0.75))
    for valor, limite in pruebas:
        if valor > limite * (1 + MARGEN):
            h.nivel = 2
        elif valor > limite:
            h.nivel = max(h.nivel, 1)
    # Lluvia
    if h.mm >= 0.5:
        h.nivel, h.lluvia = 2, "lluvia"
    elif h.prob >= 50:
        h.nivel, h.lluvia = max(h.nivel, 1), "posible lluvia"
    h.top = (h.nivel == 0 and h.prob < 30 and h.mm < 0.1 and viento <= TOP_VIENTO
             and racha <= TOP_RACHA and h.cruzado <= TOP_CRUZADO and racheo <= TOP_RACHEO)
    return h


def _hm(iso: str) -> float:
    return int(iso[11:13]) + int(iso[14:16]) / 60


def horas_del_dia(prev: dict, dia: date, desde_hora: int | None = None) -> tuple[list[Hora], str, str]:
    """Horas con luz de `dia` (opcionalmente solo desde `desde_hora`)."""
    d = dia.isoformat()
    di = prev["daily"]["time"].index(d)
    amanece, anochece = prev["daily"]["sunrise"][di], prev["daily"]["sunset"][di]
    primera = r(_hm(amanece))            # 08:38 → 9
    ultima = math.floor(_hm(anochece) - 0.5)  # 18:00 → 17 (franja 17–18)
    if desde_hora is not None:
        primera = max(primera, desde_hora)
    H = prev["hourly"]
    out = []
    for i, t in enumerate(H["time"]):
        if t[:10] != d:
            continue
        hr = int(t[11:13])
        if primera <= hr <= ultima:
            out.append(valorar(H["wind_speed_10m"][i], H["wind_gusts_10m"][i], H["wind_direction_10m"][i],
                               H["precipitation_probability"][i], H["precipitation"][i], hr))
    return out, amanece[11:], anochece[11:]


def tramos(horas: list[Hora], top: bool) -> list[tuple[int, int]]:
    """Rachas de horas seguidas buenas (índices), la más larga primero."""
    out, cur = [], None
    for k, h in enumerate(horas):
        ok = h.top if top else h.nivel == 0
        if ok:
            cur = (cur[0], k) if cur else (k, k)
        elif cur:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    out.sort(key=lambda r: (-(r[1] - r[0]), r[0]))
    return out


def rango(a: int, b: int) -> str:
    return f"a las {a} h" if a == b else f"de {a} a {b + 1} h"


def detalle_tramo(horas: list[Hora], t: tuple[int, int]) -> tuple[str, str]:
    sl = horas[t[0]:t[1] + 1]
    vmin, vmax = r(min(h.viento for h in sl)), r(max(h.viento for h in sl))
    rmax = r(max(h.racha for h in sl))
    pistas = [h.pista for h in sl]
    p = max(set(pistas), key=pistas.count)
    v = f"{vmin}" if vmin == vmax else f"{vmin}–{vmax}"
    return rango(sl[0].hora, sl[-1].hora), f"{v} km/h, rachas de hasta {rmax}, despegue por la {p}"


def resumen(horas: list[Hora]) -> tuple[list[str], int]:
    """Líneas de cabecera del parte y color."""
    n = len(horas)
    buenas = sum(h.nivel == 0 for h in horas)
    if buenas >= 0.6 * n:
        dia, nivel = "Buen día para volar", 0
    elif buenas > 0:
        dia, nivel = "Día regular", 1
    else:
        dia, nivel = "Hoy no es día de volar", 2
    ico = EMOJI[nivel]
    tops, oks = tramos(horas, True), tramos(horas, False)
    if tops:
        cuando, det = detalle_tramo(horas, tops[0])
        largo = tops[0][1] - tops[0][0] >= 2
        une = ", y" if nivel == 0 else ", pero"
        frase = "está **de maravilla**" if largo else "hay un momento que **vale de maravilla**"
        return [f"{ico} **{dia}**{une} **{cuando}** {frase} ⭐", f"> {det}"], nivel
    if oks:
        cuando, det = detalle_tramo(horas, oks[0])
        return [f"{ico} **{dia}**. Mejor momento: **{cuando}**", f"> {det}"], nivel
    return [f"{ico} **{dia}**: no hay ningún hueco dentro de los límites."], nivel


def linea_hora(h: Hora) -> str:
    s = f"`{h.hora:02d}h` {h.icono} {r(h.viento)} km/h · rachas {r(h.racha)} · {punto(h.dir)}"
    if h.lluvia:
        s += f" · 🌧️ {h.lluvia} ({h.prob}%)"
    return s


def fecha_bonita(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month]}"


LEYENDA = (f"-# ⭐ de maravilla · 🟢 volable · 🟡 precaución · 🔴 no recomendable — "
           f"límites: medio {L_VIENTO}, rachas {L_RACHA}, cruzado {L_CRUZADO} km/h")
PIE = {"text": "Pista A Pombiña 07/25 · Previsión Open-Meteo · Más detalle: aeromodelismonaron.com/viento"}


# ── Mensajes ───────────────────────────────────────────────────────────
def embed_parte(prev: dict, dia: date, desde_hora: int | None = None, titulo: str = "Parte de viento") -> dict | None:
    horas, amanece, anochece = horas_del_dia(prev, dia, desde_hora)
    if not horas:
        return None
    cab, nivel = resumen(horas)
    lineas = cab + ["", f"**Hora a hora** (luz de {amanece} a {anochece})"]
    lineas += [linea_hora(h) for h in horas] + ["", LEYENDA]
    return {
        "title": f"🌬️ {titulo} · {fecha_bonita(dia)}",
        "url": URL_WEB,
        "description": "\n".join(lineas),
        "color": COLORES[nivel],
        "footer": PIE,
    }


def embed_ahora(prev: dict, ahora: datetime) -> dict:
    """Respuesta a /viento: condiciones actuales + resto del día (o mañana si ya es de noche)."""
    c = prev["current"]
    h = valorar(c["wind_speed_10m"], c["wind_gusts_10m"], c["wind_direction_10m"])
    estado = ["Volable", "Precaución", "No recomendable"][h.nivel]
    lineas = [
        f"**Ahora ({c['time'][11:16]})**: {EMOJI[h.nivel]} **{estado}**",
        f"{r(h.viento)} km/h de {punto(h.dir)} · rachas {r(h.racha)} · "
        f"cruzado {r(h.cruzado)} · despegue por la {h.pista}",
        "",
    ]
    hoy = ahora.date()
    resto, _, _ = horas_del_dia(prev, hoy, ahora.hour + 1)
    if resto:
        cab, nivel = resumen(resto)
        cab[0] = cab[0].replace("Hoy no es día de volar", "El resto del día no es para volar") \
                       .replace("Buen día para volar", "Buena tarde para volar") \
                       .replace("Día regular", "El resto del día, regular")
        lineas += cab + ["", "**Próximas horas**"] + [linea_hora(x) for x in resto]
        titulo = f"🌬️ Viento en la pista · {fecha_bonita(hoy)}"
    else:
        manana = sorted(prev["daily"]["time"])[1]
        md = date.fromisoformat(manana)
        horas, amanece, anochece = horas_del_dia(prev, md)
        cab, nivel = resumen(horas)
        lineas += [f"**Mañana, {fecha_bonita(md)}** (luz de {amanece} a {anochece})"] + cab + [""] \
                  + [linea_hora(x) for x in horas]
        titulo = "🌬️ Viento en la pista"
    lineas += ["", LEYENDA]
    return {"title": titulo, "url": URL_WEB, "description": "\n".join(lineas),
            "color": COLORES[h.nivel], "footer": PIE}


def ventanas_top(prev: dict, dia: date, desde_hora: int) -> list[tuple[int, int, str]]:
    """Ratos 'de maravilla' de hoy que empiezan a partir de `desde_hora`.
    Devuelve (hora_inicio, hora_fin_incluida, detalle)."""
    horas, _, _ = horas_del_dia(prev, dia, desde_hora)
    out = []
    for t in sorted(tramos(horas, True)):
        cuando, det = detalle_tramo(horas, t)
        out.append((horas[t[0]].hora, horas[t[1]].hora, det))
    return out


def embed_aviso(dia: date, ini: int, fin: int, det: str) -> dict:
    return {
        "title": "⭐ ¡Se abre un buen rato para volar!",
        "url": URL_WEB,
        "description": f"Hoy, {fecha_bonita(dia)}, **{rango(ini, fin)}** la previsión está **de maravilla** en la pista.\n> {det}",
        "color": COLORES[0],
        "footer": PIE,
    }
