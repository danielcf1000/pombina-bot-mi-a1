# Convertir un Xiaomi Mi A1 en servidor Linux

Guía de lo que hicimos de verdad (noviembre de 2026), con los problemas que salieron por el camino. PC con **Windows 11** y [platform-tools](https://developer.android.com/tools/releases/platform-tools) de Google (`adb`, `fastboot`).

> ⚠️ Desbloquear el bootloader **borra todo el móvil**. Nunca vuelvas a bloquearlo (`fastboot flashing lock` / `oem lock`) con un sistema no oficial instalado: puede quedar inservible.

## 1. Preparar el móvil y el PC

1. En Android: *Ajustes → Información del teléfono* → pulsa 7 veces en *Número de compilación*. En *Opciones de desarrollador* activa **Desbloqueo OEM** y **Depuración USB**.
2. `adb devices` → acepta el aviso en el móvil.
3. `adb reboot bootloader` → `fastboot devices`.

**Problema: `fastboot devices` sale vacío.** En el Administrador de dispositivos aparece "Android" con error (`USB\VID_18D1&PID_D00D`). Falta el [Google USB Driver](https://developer.android.com/studio/run/win-usb), y además **la búsqueda automática no lo encuentra** porque el `.inf` no incluye ese PID. Hay que forzarlo: *Actualizar controlador → Buscar en mi equipo → Elegir en una lista → Usar disco →* `usb_driver\android_winusb.inf` → **Android Bootloader Interface**.

Truco: al cambiar de modo (Android ↔ fastboot ↔ lk2nd) a veces Windows no ve el móvil hasta **desenchufar y volver a enchufar el cable**.

## 2. Desbloquear el bootloader

```
fastboot oem unlock
```

El móvil se reinicia y borra los datos (llega al asistente de Android). Para volver a fastboot: apagar y mantener **Volumen − + Encendido**. Comprobar: `fastboot getvar unlocked` → `yes`.

## 3. Descargar lk2nd y el sistema

postmarketOS no tiene paquete propio para el Mi A1: usa la imagen genérica **`qcom-msm8953`**, que arranca a través de [lk2nd](https://github.com/msm8916-mainline/lk2nd) (el Mi A1 está en su lista de dispositivos soportados).

Las imágenes precompiladas están en `https://images.nura.eco/bpo/<versión>/qcom-msm8953/` (antes images.postmarketos.org). **No hay imagen `console`** (solo con interfaz gráfica), así que usamos la más ligera, **Sxmo**, y le quitamos la suspensión después. Cada build trae dos archivos:

- `...-qcom-msm8953-lk2nd.img.xz` → lk2nd empaquetado (va a la partición `boot`)
- `...-qcom-msm8953.img.xz` → el sistema (va a `userdata`)

Comprueba los `.sha256` y descomprime (`xz -dk`).

## 4. Grabar lk2nd

El Mi A1 tiene particiones A/B. Mira cuál está activa con `fastboot getvar current-slot` (en el nuestro, `b`):

```
fastboot flash boot_b ...-lk2nd.img
```

**Problema: al reiniciar vuelve a Android.** El bootloader de Xiaomi marcó la ranura `b` como *unbootable* (`fastboot getvar slot-unbootable:b` → `Yes`) y saltó a la `a`. Solución: `fastboot set_active b` desde el fastboot de Xiaomi. Una vez instalado el sistema, el servicio `qbootctl` de postmarketOS marca la ranura como buena en cada arranque y ya no se pierde. La ranura `a` conserva Android como plan B.

## 5. Grabar el sistema

Desde el **fastboot de lk2nd** (menú de texto con *Reboot / Continue / Recovery / Bootloader / EDL / Shutdown*; si hace falta, `fastboot boot ...-lk2nd.img` lo carga en RAM sin grabar nada).

**Problema 1:** en lk2nd el móvil aparece con **otro número de serie**, así que Windows pide el driver otra vez (mismo método manual).

**Problema 2:** `fastboot flash userdata sistema.img` (2,1 GB) peta en Windows con `std::bad_alloc` (fastboot 37.0.3). Solución: convertir antes la imagen a **formato sparse** con [`herramientas/img2simg.py`](../herramientas/img2simg.py):

```
python img2simg.py sistema.img sistema.simg
fastboot flash userdata sistema.simg
fastboot reboot
```

## 6. Primer arranque, red USB y SSH

Usuario y contraseña de serie de las imágenes precompiladas: `user` / `147147` (**cámbiala** con `passwd`).

**Problema: Windows no ve la red USB.** El móvil en postmarketOS se presenta como `USB\VID_18D1&PID_D001`, y el driver de Google de antes **se lo queda como "Android Composite ADB Interface"**, lo que tapa la red. Cambiarle el driver a mano a **Dispositivo compuesto USB** → aparece *UsbNcm Host Device*. El PC recibe `172.16.42.2` y el móvil es `172.16.42.1`.

El SSH viene apagado. En el terminal del móvil (Sxmo → menú → Apps → *foot*):

```
sudo systemctl enable --now sshd
```

(Esta versión usa **systemd**, no OpenRC: `rc-update` no existe.) Luego, desde el PC, copia tu llave pública a `~/.ssh/authorized_keys` del móvil.

## 7. El misterio de los reinicios

El móvil se reiniciaba cada ~3 minutos. En el registro (`journalctl -b -1`), cada arranque terminaba en `rtcwake -m mem`: **Sxmo lo suspende y el kernel se reinicia al suspender**. Para un servidor la suspensión sobra:

- [`servidor/servidor-sin-reposo.service`](../servidor/servidor-sin-reposo.service): *wakelock* permanente al arrancar.
- `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`

Desde entonces, estable.

## 8. WiFi, hora y batería

- WiFi: Sxmo → menú → *Networks*, o `sudo nmcli --ask device wifi connect "MI_WIFI"`. Reserva su IP en el router.
- Hora: el Mi A1 no guarda la hora real (arranca en una fecha antigua); con WiFi la sincroniza `systemd-timesyncd`. Zona: `sudo timedatectl set-timezone Europe/Madrid`.
- Batería: el driver `qcom-smbchg` solo expone `online` (escribir `0` pausa la carga y el móvil tira de batería) y `constant_charge_current`. Con eso funciona [`servidor/bateria-servidor.sh`](../servidor/bateria-servidor.sh) (80 % / 60 %).
