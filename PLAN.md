# Plan de Implementación: Python para FLIR Lepton Dev Kit V2

> **Estado:** esqueleto implementado y **revisado/corregido** (ver
> [§ Changelog de correcciones](#changelog-de-correcciones)). Guía de puesta
> en marcha en hardware: **`ARRANQUE_SEGURO.md`**.

## Objetivo

Crear un módulo Python modular para la cámara térmica FLIR Lepton 2.5
(Dev Kit V2, SparkFun SFE-KIT-15948) sobre Raspberry Pi con conexión
SPI/I2C directa. El diseño debe permitir su integración futura con una
cámara óptica para captura sincronizada.

## Arquitectura

```
python/
├── requirements.txt          # Dependencias pip
├── setup.py                  # Instalación del paquete
├── lepton_viewer.py          # ▶ CLI principal: vista en vivo + captura
└── lepton/
    ├── __init__.py            # Exporta API pública
    ├── spi.py                 # Captura VoSPI + ensamblado de frame
    ├── i2c.py                 # Control CCI (opcional, para FFC/gain)
    ├── colormaps.py           # Paletas de color (gray/ironbow/rainbow)
    └── radiometry.py          # Conversión 14-bit → °C
```

## Módulos — responsabilidades

### `lepton/spi.py`

- Abre `/dev/spidev0.X` (configurable, default `0.0`) — parsea la ruta a
  `open(bus, dev)` de `py-spidev`
- SPI mode 0, 8 bits, 16 MHz (limitado por software a **≤ 20 MHz**)
- Clase `LeptonSPI` con método `capture_frame() -> (ndarray[uint16], is_duplicate)`
  - Lee 60 paquetes de 164 bytes cada uno (VoSPI)
  - Detecta paquetes no-válidos (header byte[0] & 0x0F == 0x0F)
  - Verifica que packet[1] == número de fila esperado (0..59)
  - Convierte big-endian a uint16: `pixel = (data[4+2*i] << 8) | data[5+2*i]`
  - Retorna array numpy (60, 80) de uint16
  - Detecta frames duplicados por suma del frame

### `lepton/i2c.py`

- Abre `/dev/i2c-1` (configurable), dirección 0x2A (7-bit)
- Implementa el protocolo CCI (Command Control Interface):
  1. Esperar desocupado en `LEP_I2C_STATUS_REG (0x0002)` bit 0
  2. Escribir data length en `LEP_I2C_DATA_LENGTH_REG (0x0006)`
  3. Escribir datos en `LEP_I2C_DATA_BASE (0x0008)`
  4. Escribir comando en `LEP_I2C_COMMAND_REG (0x0004)`
  5. Esperar completado
  6. Leer respuesta
- Funciones expuestas:
  - `run_ffc()` — ejecuta FFC (Flat Field Correction), comando `0x0242`
  - `reboot()` — reinicia el módulo, comando `0x0804`
  - `get_fpa_temperature_celsius()` — temperatura interna del sensor
  - `get_aux_temperature_celsius()` — temperatura auxiliar

### `lepton/colormaps.py`

- Tres paletas de 256 entradas RGB:
  - `COLORMAP_GRAYSCALE` (0): blanco → negro, lineal
  - `COLORMAP_IRONBLACK` (1): blanco→gris→negro→rojo→naranja→amarillo
  - `COLORMAP_RAINBOW` (2): azul→cian→verde→amarillo→rojo
- Función `apply_colormap(frame_8bit, colormap_id) -> ndarray[uint8]` RGB

### `lepton/radiometry.py`

- Convierte raw 14-bit a temperatura Celsius (modo TLinear):
  - `T_K = raw_value / 100.0`
  - `T_C = T_K - 273.15`
- `auto_range(raw, margin) -> (vmin, vmax)` — calcula rango dinámico
- `normalize_frame(raw, vmin, vmax) -> uint8` — normaliza a 0-255
- `get_frame_temperatures(celsius) -> dict` — estadísticas min/max/avg

### `lepton_viewer.py` (CLI principal)

```
uso: lepton_viewer.py [-h] [-d SPI_DEVICE] [--spi-mode {0,3}]
                       [--spi-speed HZ] [-i I2C_BUS] [--no-i2c]
                       [-c [PREFIX]] [--colormap {grayscale,ironblack,rainbow}]
                       [--scale N] [--temp] [-o DIR]

Modos de operación:
  Por defecto:     Vista en vivo con OpenCV (640×480 escalado 8×)
  --capture, -c    Captura un solo frame y guarda snapshot (raw+JPG)

Teclas en vista en vivo:
  s    Guardar snapshot (thermal_TIMESTAMP.raw + thermal_TIMESTAMP.jpg)
  f    Ejecutar FFC (si I2C está disponible)
  c    Cambiar colormap (gray → ironblack → rainbow)
  t    Mostrar/ocultar superposición de temperatura
  r    Reset auto-range
  q    Salir
```

## Dependencias

```bash
pip install spidev numpy opencv-python
# Opcional para control I2C:
pip install smbus2
```

## Roadmap de implementación

| Paso | Archivos | Descripción |
|---|---|---|
| 1 | `spi.py`, `colormaps.py` | Captura SPI + paletas de color |
| 2 | `lepton_viewer.py` | Loop de vista en vivo con OpenCV |
| 3 | `radiometry.py` | Medición de temperatura y normalización |
| 4 | `i2c.py` | Control I2C: FFC, temperatura, reboot |
| 5 | Integración cámara óptica | Futuro, fuera de este plan |

## Referencias del repositorio LeptonModule

| Archivo original | Contenido | Usado en |
|---|---|---|
| `software/flirpi/leptsci.c` | Driver SPI (mode 0, 16 MHz, VoSPI) | `spi.py` |
| `software/raspberrypi_qt/LeptonThread.cpp` | Loop de captura + detección paquetes | `spi.py` |
| `software/raspberrypi_video/Palettes.cpp` | 3 paletas de color RGB | `colormaps.py` |
| `software/raspberrypi_video/Lepton_I2C.cpp` | Comandos I2C vía SDK | `i2c.py` |
| `software/raspberrypi_video/LeptonThread.cpp` | Auto-ranging + mapeo colormap | `radiometry.py`, `lepton_viewer.py` |
| `software/beagleboneblack_video/leptonSDKEmb32PUB/LEPTON_I2C_Reg.h` | Registros del CCI | `i2c.py` |
| `software/flirpi/fblept.c` | Colormap + visualización framebuffer | `colormaps.py` |

## Changelog de correcciones

Revisión del código generado inicialmente, contrastado con el código C de
referencia (`raspberrypi_qt/LeptonThread.cpp`, `flirpi/leptsci.c`) y con la
API real de las librerías `py-spidev` / `smbus2`.

### `spi.py`
- **Apertura del dispositivo:** se reemplazó `open_path("/dev/spidev0.0")`
  (método inexistente en `py-spidev`) por un parseo de la ruta a
  `open(bus, dev)` con dos enteros. *Sin esto el dispositivo no abría.*
- **Seguridad de velocidad:** *clamp* a **20 MHz** (máximo del datasheet);
  cualquier `speed_hz` mayor se recorta con aviso.
- **`xfer2`:** se elimina el argumento `speed_hz=` (no fiable como keyword);
  la velocidad se fija vía `max_speed_hz`.
- **Resincronización:** la máquina de estados de captura ahora replica
  `LeptonThread.cpp`: ante paquete fuera de orden se **descarta el frame
  entero y se reinicia desde la fila 0** (antes solo reintentaba la fila).
- **Rendimiento:** parseo de píxeles **vectorizado con numpy** (antes era un
  doble bucle Python píxel a píxel, demasiado lento para vista en vivo).

### `i2c.py`
- **Protocolo CCI reescrito:** se sustituyó `read/write_i2c_block_data` (cuyo
  *command byte* es de **8 bits** y no puede direccionar los registros de
  **16 bits** del Lepton) por transacciones I2C crudas con
  `smbus2.i2c_msg` / `i2c_rdwr` (repeated-start). *Sin esto, FFC y lectura de
  temperatura no funcionaban.*
- Solo se exponen comandos **seguros** (ping, estado, temperatura FPA/aux,
  FFC, reboot). No se incluye ninguna escritura a flash no volátil.

### Pendiente / notas
- La conversión a °C (`radiometry.py`) asume modo **TLinear** (centikelvin).
  Verificar por I2C si el sensor concreto es radiométrico; si no, la imagen
  es válida pero las temperaturas absolutas no son fiables.
- Posible mejora: modo `--simulate` para validar el pipeline sin cámara.
- Las paletas de `colormaps.py` son aproximaciones algorítmicas; pueden
  portarse las tablas exactas de 256 entradas de `Palettes.cpp` si se desea
  fidelidad de color 1:1.
