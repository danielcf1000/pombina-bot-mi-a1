# Surf Galicia en el Mi A1 (Tailscale Funnel)

La app **Surf Galicia** (`Documents\surf-galicia-app`) es una web estática: `index.html` + service worker + iconos. Los datos (olas, viento, marea) los pide el navegador directamente a Open-Meteo, así que el Mi A1 solo tiene que **servir los archivos**.

Para poder instalarla en el móvil como app y que funcione sin cobertura, el navegador exige **HTTPS**. Se usa **Tailscale Funnel**: el propio Tailscale del Mi A1 publica la carpeta `/srv/surf-galicia` en `https://a1.<tu-red>.ts.net` con un certificado válido. No hace falta abrir puertos en el router, comprar un dominio ni instalar nginx.

> ⚠️ Con Funnel la URL es **pública**: la puede abrir cualquiera que tenga el enlace. Solo se publica esa carpeta. SSH y el resto del móvil quedan igual que antes.

## 1. Subir la app al móvil (desde el PC)

En PowerShell, desde la carpeta del repo:

```powershell
.\herramientas\subir-surf.ps1
```

El script copia los archivos por `scp` a `/tmp` y luego, con `sudo`, los deja en `/srv/surf-galicia`. Esa carpeta está fuera de `/home/user` y es legible para todos. Si estás conectado por cable: `.\herramientas\subir-surf.ps1 -Servidor a1-usb`.

## 2. Instalar Tailscale (en el móvil, `ssh a1`)

```sh
sudo apk add tailscale                  # en Nura/postmarketOS con systemd se instala también tailscale-systemd
sudo systemctl start systemd-resolved   # ver la nota de abajo
sudo systemctl enable --now tailscaled  # arranca ahora y en cada reinicio (también tras el reinicio de las 04:00)
sudo tailscale up --hostname=a1 --accept-dns=false   # muestra un enlace: ábrelo en el PC e inicia sesión (o crea cuenta gratis)
```

> **Nota sobre el DNS**: al instalar `tailscale`, Alpine habilita también `systemd-resolved` y convierte `/etc/resolv.conf` en un enlace a `/run/systemd/resolve/stub-resolv.conf`. Hasta que no arranca el servicio, ese archivo no existe. Arrancarlo al momento (en vez de esperar al próximo reinicio) permite comprobar enseguida que el DNS funciona: `getent hosts discord.com api.open-meteo.com`. NetworkManager le pasa los DNS de la WiFi sin tocar nada más.
> Con `--accept-dns=false`, Tailscale no cambia el DNS del móvil; Funnel no lo necesita.

## 3. Publicar la carpeta con Funnel

```sh
sudo tailscale funnel --bg /srv/surf-galicia
```

- La **primera vez** dirá *"Funnel is not enabled on your tailnet"* y saldrá un enlace para activarlo (junto con HTTPS) en tu red de Tailscale. Ábrelo y acepta: el comando, que se queda esperando, continúa solo. Si lo habías cortado, vuelve a lanzarlo.
- `--bg` hace que quede guardado y se mantenga tras reiniciar.
- Hace falta `sudo` porque Tailscale solo sirve carpetas como root.
- Al terminar muestra la URL, del tipo `https://a1.xxxx-yyyy.ts.net`. La primera vez el DNS puede tardar unos minutos en funcionar.

Comprobar: `tailscale funnel status`.

## 4. Instalarla en el móvil

Abre la URL en Chrome → menú ⋮ → **Instalar app** (o *Añadir a pantalla de inicio*). A partir de ahí se abre como una app y guarda el último parte para cuando no haya cobertura.

## Actualizar la app

Tras cambiar algo en `surf-galicia-app`, vuelve a ejecutar `.\herramientas\subir-surf.ps1`. El service worker carga primero lo que tiene guardado y descarga la versión nueva en segundo plano, así que los cambios se ven **al abrir la app por segunda vez**. Si cambias muchos archivos, sube también la versión de caché en `sw.js` (`sg-app-v1` → `sg-app-v2`).

## Quitarla

```sh
sudo tailscale funnel --bg /srv/surf-galicia off   # deja de publicarla
sudo tailscale funnel reset                        # borra toda la configuración de Funnel
```
