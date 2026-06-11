# Hallazgos Técnicos del Repositorio LeptonModule

## Resumen del repositorio

**LeptonModule** (GroupGets/PureEngineering) contiene código de referencia
en C/C++ para la cámara térmica FLIR Lepton sobre Raspberry Pi, BeagleBone
Black, Arduino, STM32, y Windows. **No contiene código Python funcional.**
El proyecto `pylepton` (GroupGets) está obsoleto (README: *"this software no longer works"*).

## 1. Protocolo VoSPI (Video SPI)

### Configuración SPI

| Parámetro | `leptsci.c` (flirpi) | `SPI.cpp` (raspberrypi_video) | `LeptonThread.cpp` (raspberrypi_qt) |
|---|---|---|---|
| Dispositivo | `/dev/spidev0.0` | `/dev/spidev0.0` (CS0) / `0.1` (CS1) | `/dev/spidev0.1` |
| SPI mode | 0 (CPOL=0, CPHA=0) | 3 (CPOL=1, CPHA=1) | 0 |
| Velocidad | 16 MHz | 10 MHz (configurable 20 MHz) | 16 MHz |
| Bits/palabra | 8 | 8 | 8 |

> Ambos modos 0 y 3 funcionan. El modo 0 se alinea con el driver de FLIR
> (`leptsci.c`). La velocidad debe ser ≤ 20 MHz según especificación.

### Estructura del paquete VoSPI

Cada paquete son **164 bytes** = 4 header + 80 píxeles (2 bytes c/u):

```
Byte 0:    [bits 7-4: segmento (solo Lepton 3.x)] [bits 3-0: flags]
             flags=0x0F → cámara no lista, descartar paquete
Byte 1:    Número de fila (0-59 para Lepton 2.x)
Byte 2-3:  CRC (no se verifica en ejemplos del repo)
Byte 4-163:  80 píxeles de 16-bit en big-endian (MSB first)
```

**Frame completo**: 60 paquetes × 164 bytes = **9840 bytes** (Lepton 2.x 80×60)

### Algoritmo de captura (de `leptsci.c` y `LeptonThread.cpp`)

```
while fila < 60:
    leer 164 bytes de SPI
    if (packet[0] & 0x0F) == 0x0F:   # no listo
        esperar 1 ms
        continuar
    if packet[1] != fila:             # fuera de sync
        resetear scan (fila = 0)
        if resets > 750: reboot()
        continuar
    extraer 80 píxeles del packet[4..163]
    fila += 1
```

### Extracción de píxeles

Del `leptsci.c` líneas 98-100:
```c
for (i = 0; i < 80; i++)
    img[row * 80 + i] = (lepacket[2 * i + 4] << 8) | lepacket[2 * i + 5];
```

Cada píxel son 2 bytes en big-endian dentro del paquete:
```
pixel[col] = (packet[4 + 2*col] << 8) | packet[5 + 2*col]
```

En Python:
```python
pixels = np.frombuffer(packet[4:], dtype=np.uint16).newbyteorder('B')
```

### Detección de duplicados

El Lepton envía el mismo frame a ~27 FPS interno, pero la imagen cambia
solo a ~9 FPS. El `LeptonThread.cpp` no detecta duplicados explícitamente;
procesa cada frame recibido. Una estrategia simple es comparar la suma del
frame anterior vs el actual.

## 2. Protocolo CCI (I2C Control)

### Dirección I2C

De `LEPTON_I2C_Reg.h` línea 83:
```c
#define LEP_I2C_DEVICE_ADDRESS  0x2A  // 7-bit address
```
7-bit: `0x2A` — 8-bit write: `0x54`, 8-bit read: `0x55`

### Registros del controlador CCI

| Dirección | Nombre | Descripción |
|---|---|---|
| `0x0000` | `LEP_I2C_POWER_REG` | Encender/apagar módulo |
| `0x0002` | `LEP_I2C_STATUS_REG` | Bit 0: busy (1=ocupado, 0=listo) |
| `0x0004` | `LEP_I2C_COMMAND_REG` | Escribir ID de comando (16-bit) |
| `0x0006` | `LEP_I2C_DATA_LENGTH_REG` | Longitud de datos en bytes |
| `0x0008` | `LEP_I2C_DATA_0_REG` | Primer word de datos |
| `0x000A`..`0x0026` | `LEP_I2C_DATA_1..15_REG` | Datos adicionales |
| `0x0028` | `LEP_I2C_DATA_CRC_REG` | CRC |
| `0xF800` | `LEP_DATA_BUFFER_0` | Buffer grande de datos (1 KB) |
| `0xFC00` | `LEP_DATA_BUFFER_1` | Buffer grande de datos (1 KB) |

### Flujo de comando CCI

```
1. Esperar hasta STATUS_REG bit 0 == 0   (no busy)
2. Si hay datos de entrada:
   - Escribir DATA_LENGTH_REG = numero_de_bytes
   - Escribir datos en DATA_0_REG..DATA_N_REG
   - Sino: DATA_LENGTH_REG = 0
3. Escribir COMMAND_REG con el ID del comando
4. Esperar hasta STATUS_REG bit 0 == 0   (comando completado)
5. Leer DATA_LENGTH_REG para saber cuántos bytes de respuesta
6. Leer DATA_0_REG..DATA_N_REG para la respuesta
```

### IDs de comando (del SDK)

| ID | Macro | Descripción |
|---|---|---|
| `0x0200` | `LEP_CID_SYS_PING` | Ping (dispositivo presente) |
| `0x0204` | `LEP_CID_SYS_CAM_STATUS` | Estado de la cámara |
| `0x0208` | `LEP_CID_SYS_FLIR_SERIAL_NUMBER` | Número serial FLIR |
| `0x020C` | `LEP_CID_SYS_CAM_UPTIME` | Tiempo encendido |
| `0x0210` | `LEP_CID_SYS_AUX_TEMPERATURE_KELVIN` | Temperatura auxiliar |
| `0x0214` | `LEP_CID_SYS_FPA_TEMPERATURE_KELVIN` | Temperatura del FPA (×100 K) |
| `0x0218` | `LEP_CID_SYS_TELEMETRY_ENABLE_STATE` | Activar telemetría en frame |
| `0x022C` | `LEP_CID_SYS_SCENE_STATISTICS` | Estadísticas de la escena |
| `0x023C` | `LEP_CID_SYS_FFC_SHUTTER_MODE_OBJ` | Configurar modo de shutter FFC |
| `0x0242` | `FLR_CID_SYS_RUN_FFC` | **Ejecutar FFC ahora** |
| `0x0804` | `LEP_CID_OEM_REBOOT` | **Reiniciar el módulo** |

### Comandos desde el SDK (`LEPTON_SYS.h`, `LEPTON_OEM.h`)

```c
#define LEP_SYS_MODULE_BASE               0x0200
#define LEP_CID_SYS_PING                  (0x0200)
#define LEP_CID_SYS_FPA_TEMPERATURE_KELVIN (0x0214)
#define FLR_CID_SYS_RUN_FFC               (0x0242)

#define LEP_OEM_MODULE_BASE               0x0800
#define LEP_CID_OEM_REBOOT                (0x0804)
```

## 3. Paletas de Color

Tres paletas definidas en `Palettes.cpp`, cada una con 256 entradas
RGB (3 enteros por entrada = 768 valores):

### `colormap_grayscale`
Gradiente lineal: blanco (entrada 0) → negro (entrada 255).
```
entrada 0:  (255, 255, 255)
entrada 1:  (253, 253, 253)
...
entrada 255: (0, 0, 0)
```
Terminador: `-1`

### `colormap_ironblack` (default)
```
entradas 0-127:   Blanco → Negro (escala de grises descendente)
entradas 128-159: Negro → Rojo oscuro
entradas 160-191: Rojo → Naranja
entradas 192-223: Naranja → Amarillo
entradas 224-255: Amarillo → Amarillo brillante/blanco
```

### `colormap_rainbow`
```
entradas 0-42:    Azul oscuro → Azul
entradas 43-85:   Azul → Cian
entradas 86-128:  Cian → Verde
entradas 129-170: Verde → Amarillo
entradas 171-213: Amarillo → Naranja
entradas 214-255: Naranja → Rojo
```

### Mapeo píxel → color

Del `mainwindow.cpp` líneas 51-57:
```cpp
diff = max_value - min_value + 1;
scaledValue = 256 * (baseValue - minValue) / diff;
color = colormap[scaledValue];  // RGB triplet
```

Se normaliza el rango raw [min, max] a [0, 255] y se indexa la paleta.

## 4. Radiometría (temperatura)

### Especificación Lepton 2.5

| Parámetro | Valor |
|---|---|
| Resolución ADC | 14-bit (en contenedor 16-bit) |
| Frame rate | 8.6 Hz (comercial) / 27 Hz (interna) |
| Precisión radiométrica | ±5°C (high gain @ 25°C ambiente) |
| Rango (high gain) | -10°C a +140°C |
| Rango (low gain) | hasta +400°C |

### TLinear (modo radiométrico)

Cuando **TLinear** está habilitado (default en Lepton 2.5 y 3.5):
- El valor de píxel representa temperatura en centikelvin (K × 100)
- Los valores típicos del código C: `rangeMin=30000` (26.85°C), `rangeMax=32000` (46.85°C)

**Fórmula de conversión:**
```python
T_kelvin = raw_pixel / 100.0
T_celsius = T_kelvin - 273.15
```

### Precisión según temperatura (datasheet)

| Temp. ambiente | Temp. escena 10°C | 50°C | 100°C |
|---|---|---|---|
| 0°C | ±5°C | ±5°C | ±5°C |
| 30°C | ±5°C | ±3°C | ±4°C |
| 60°C | ±6°C | ±3°C | ±3°C |

## 5. Conexión de pines (Raspberry Pi)

Basado en `SPI.cpp`, `LeptonThread.cpp` y `leptsci.c`:

| Señal Lepton | Pin RPi | Conexión |
|---|---|---|
| CS (Chip Select) | GPIO8 (CE0) → `/dev/spidev0.0` | O GPIO7 (CE1) → `0.1` |
| MOSI | GPIO10 (MOSI) | No usado (Lepton es output-only) |
| MISO | GPIO9 (MISO) | **Obligatorio** — datos de video |
| SCLK | GPIO11 (SCLK) | Reloj SPI |
| SDA (I2C) | GPIO2 (SDA) | `/dev/i2c-1` |
| SCL (I2C) | GPIO3 (SCL) | `/dev/i2c-1` |
| VIN | 3.3V o 5V | Breakout regula internamente |
| GND | GND | Masa común |

> **Importante**: Habilitar SPI e I2C con `raspi-config` antes de usar.

## 6. Estado del ecosistema Python existente

### PyLepton (`groupgets/pylepton`)
- **Obsoleto**: README dice explícitamente *"this software no longer works"*
- Solo captura SPI, sin control I2C
- Asume datos de 12-bit (no 14-bit radiométrico)
- Dependencias: `cv2` + `numpy`
- Solo Lepton 2.x (80×60), no maneja los 4 segmentos de la 3.x
- Sin mantenimiento; se rompe en kernels recientes de Raspbian

#### Técnica reutilizable: lectura por lotes con `ioctl` crudo

`pylepton` **no usa el módulo `spidev`**. Habla directo con el kernel: arma a
mano el struct `spi_ioc_transfer` de Linux y lanza el comando `SPI_IOC_MESSAGE`
con `fcntl.ioctl`. Esto le permite leer **varias filas VoSPI en una sola
syscall**, en lugar de una llamada `xfer2()` por paquete.

**Qué es.** El kernel acepta un *array* de descriptores `spi_ioc_transfer` en
una única `ioctl`. Cada descriptor es una transferencia (una fila de 164 bytes).
Enviando N descriptores juntos, las 60 filas de un frame se leen en ~3 syscalls
en vez de 60.

**Por qué importa.** Nuestra implementación (`lepton/spi.py`) hace un
`self._spi.xfer2(tx)` por paquete → **60 syscalls por frame**. A 9 FPS son ~540
syscalls/s. Funciona bien, pero si alguna vez la captura va corta de CPU o
pierde sincronía por latencia entre paquetes, el batching reduce ese overhead.

**El límite de 24.** El `bufsiz` por defecto de spidev es 4096 bytes, y
`4096 / 164 ≈ 24` → solo caben 24 filas por `ioctl`. Por eso `pylepton` parte el
frame en bloques de 24. Se puede subir a 59 filas/ioctl ampliando el buffer:

```bash
sudo chmod 666 /sys/module/spidev/parameters/bufsiz
echo 65536 > /sys/module/spidev/parameters/bufsiz   # 65536/164 = 399 -> tope util 59
```

**Cómo se hace (esqueleto, adaptado de `Lepton.py`):**

```python
import struct, numpy as np
from fcntl import ioctl

SPI_IOC_MAGIC = ord("k")

# struct spi_ioc_transfer = "=QQIIHBBI"
#   tx_buf(u64) rx_buf(u64) len(u32) speed_hz(u32)
#   delay_usecs(u16) bits_per_word(u8) cs_change(u8) pad(u32)
xmit = struct.Struct("=QQIIHBBI")

# 1) Buffers contiguos: uno de TX (ceros) y uno de RX para todo el frame
PACKET = 164          # 4 header + 80 px*2
ROWS   = 60
txbuf  = np.zeros(PACKET, dtype=np.uint8)
rxbuf  = np.zeros((ROWS, PACKET), dtype=np.uint8)

# 2) Un descriptor por fila, todos apuntando al mismo txbuf y a su tramo de rxbuf
msgs = bytearray()
for i in range(ROWS):
    msgs += xmit.pack(
        txbuf.ctypes.data,                 # tx_buf  (mismo buffer de ceros)
        rxbuf.ctypes.data + PACKET * i,    # rx_buf  (fila i)
        PACKET,                            # len
        16000000,                          # speed_hz (<= 20 MHz)
        0, 8, 1, 0)                        # delay, bits, cs_change=1, pad

# 3) Enviar en bloques de COUNT filas (24 con bufsiz por defecto)
COUNT = 24
sent = 0
while sent < ROWS:
    n = min(COUNT, ROWS - sent)
    # nr=0, dir=write; el "size" del ioctl es el tamaño total del bloque
    iow = (1 << 30) | (SPI_IOC_MAGIC << 8) | (xmit.size * n) << 16
    ioctl(handle, iow, msgs[xmit.size*sent : xmit.size*(sent+n)], True)
    sent += n
# rxbuf ya contiene las 60 filas; parsear igual que _parse_frame()
```

(El cálculo de `iow` lo hace de forma legible `ioctl_numbers._IOW(SPI_IOC_MAGIC,
0, size)` en el repo original; aquí va expandido para que se entienda.)

**Cuándo adoptarlo.** Solo si se mide un problema real de rendimiento o de
sincronía con `xfer2` por paquete. Mientras tanto, `spidev` es más simple,
mantenido y portable — esta nota queda solo como referencia.

### Lecciones aprendidas para la implementación Python
1. El **SDK de FLIR no es necesario** — el CCI es implementable con smbus2
2. **SPI mode 0** es el más usado por los drivers de FLIR
3. La detección de paquetes no-listos (0xF en header **byte[0] bits 0-3**)
   es **crítica** para captura robusta
4. Frame rate efectivo: **~9 FPS** (descartando duplicados internos ~27 FPS)
5. Las paletas de color vienen como arrays C de 768 enteros — portables a Python

## 7. Archivos clave del repositorio

| Archivo | Ruta | Líneas útiles |
|---|---|---|
| Driver SPI principal | `software/flirpi/leptsci.c` | 47-104 (captura completa) |
| Captura Qt (sin SDK) | `software/raspberrypi_qt/LeptonThread.cpp` | 13-162 (loop robusto) |
| Captura Qt (con SDK) | `software/raspberrypi_video/LeptonThread.cpp` | 107-274 (soporte 3.x) |
| Paletas de color | `software/raspberrypi_video/Palettes.cpp` | 1-25 (3 paletas) |
| I2C via SDK | `software/raspberrypi_video/Lepton_I2C.cpp` | 1-32 (FFC, reboot) |
| Registros I2C | `software/beagleboneblack_video/leptonSDKEmb32PUB/LEPTON_I2C_Reg.h` | 79-131 (addresses) |
| Framebuffer viewer | `software/flirpi/fblept.c` | 30-104 (colormap + render) |
