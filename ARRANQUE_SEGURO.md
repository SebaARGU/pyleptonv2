# Guía de Arranque Seguro — FLIR Lepton 2.x en Raspberry Pi

Guía paso a paso para conectar y poner en marcha la cámara térmica FLIR
Lepton (80×60, Dev Kit V2) sobre Raspberry Pi **sin riesgo de dañar el
sensor**. Sigue los pasos en orden.

> **Resumen de seguridad**
> - El software (captura SPI + comandos I2C usados) **no puede dañar** la
>   cámara: la captura es de solo lectura y los comandos I2C son inocuos.
> - El único riesgo real es **eléctrico/cableado**: el Lepton es de **3.3 V**.
> - Conecta y desconecta siempre con la **Raspberry Pi apagada**.

---

## 1. Antes de empezar — qué puede y qué no puede dañar la cámara

| Acción | ¿Riesgo? | Motivo |
|---|---|---|
| Captura por SPI | ❌ Ninguno | Solo lectura; MOSI envía ceros que el Lepton ignora |
| Comandos I2C usados (ping, temperatura, FFC) | ❌ Ninguno | Documentados por FLIR; FFC solo mueve el shutter interno |
| Velocidad SPI ≤ 20 MHz | ❌ Ninguno | Dentro de especificación (el código limita a 20 MHz) |
| Aplicar 5 V a líneas de datos | ✅ **Daña** | El Lepton es de 3.3 V |
| Hot-plug (conectar con la Pi encendida) | ✅ Riesgo | Picos de corriente / latch-up |
| Descarga electrostática (ESD) | ✅ Riesgo | Manipular sin descargarse |
| Apuntar al sol / fuente muy caliente | ✅ Riesgo físico | Puede dañar el microbolómetro |

**Comandos que el código evita a propósito:** escrituras a la memoria flash
no volátil (OEM). No se usan, por lo que la configuración de fábrica del
sensor nunca se altera.

---

## 2. Cableado (Pi APAGADA)

Apaga completamente la Raspberry Pi y desconéctala de la corriente antes de
cablear.

| Lepton (breakout) | Pin físico RPi | Función |
|---|---|---|
| GND | 6 | Masa común |
| VIN (3.3V) | 1 | Alimentación 3.3 V |
| SDA | 3 | I2C datos (GPIO2) |
| SCL | 5 | I2C reloj (GPIO3) |
| CS | 24 | Chip Select → `/dev/spidev0.0` (GPIO8/CE0) |
| MOSI | 19 | GPIO10 (el Lepton lo ignora) |
| MISO | 21 | **Datos de vídeo** (GPIO9) — obligatorio |
| CLK | 23 | Reloj SPI (GPIO11/SCLK) |

```
        Raspberry Pi (cabecera de 40 pines, vista superior)
   3V3  (1) (2)  5V        <-- NO usar el 5V para el Lepton
   SDA  (3) (4)  5V
   SCL  (5) (6)  GND
        (7) (8)
   GND  (9) (10)
        ...
  MOSI (19) (20) GND
  MISO (21) (22)
   CLK (23) (24) CS (CE0)
```

> ⚠️ **Verifica dos veces** antes de alimentar: que VIN va al pin **1 (3.3V)**
> y no al pin 2/4 (5V). Un error aquí es la única forma realista de quemar el
> módulo.

---

## 3. Configurar la Raspberry Pi (software)

Enciende la Pi ya cableada y abre una terminal.

### 3.1 Habilitar SPI e I2C

```bash
sudo raspi-config
# Interface Options -> SPI  -> Enable
# Interface Options -> I2C  -> Enable
# Finish -> reiniciar
sudo reboot
```

Tras reiniciar, comprueba que existen los dispositivos:

```bash
ls -l /dev/spidev0.*     # debe aparecer /dev/spidev0.0
ls -l /dev/i2c-1         # debe aparecer /dev/i2c-1
```

### 3.2 Confirmar que la cámara responde por I2C

```bash
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
```

Debe aparecer la dirección **`2a`** en la cuadrícula. Si aparece → cableado
I2C correcto y la cámara está viva. Si **no** aparece, **apaga** y revisa
SDA/SCL/GND/VIN antes de seguir.

### 3.3 Instalar dependencias Python

```bash
cd ~/LeptonModule/python
pip install -r requirements.txt
# Si usas un entorno gestionado (PEP 668), crea un venv:
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
```

---

## 4. Primer arranque (progresivo)

Arranca **despacio** la primera vez para minimizar frames corruptos. La
velocidad no afecta a la integridad de la cámara, solo a la calidad de la
captura.

### 4.1 Captura de un solo frame (prueba mínima)

```bash
python3 lepton_viewer.py --capture primera_prueba --spi-speed 10000000
```

- Guarda `primera_prueba_FECHA.raw` y `.jpg`.
- Imprime Min/Max/Avg de temperatura.
- Si genera el `.jpg` con una imagen reconocible → **captura OK**.

### 4.2 Vista en vivo

```bash
python3 lepton_viewer.py --spi-speed 10000000
```

Si la imagen es estable, sube a la velocidad nominal:

```bash
python3 lepton_viewer.py --spi-speed 16000000
```

**Controles en la ventana de vídeo:**

| Tecla | Acción |
|---|---|
| `s` | Guardar snapshot (`.raw` + `.jpg`) |
| `f` | Ejecutar FFC (recalibración del shutter) |
| `c` | Cambiar paleta (gris → ironblack → rainbow) |
| `t` | Mostrar/ocultar temperatura |
| `r` | Reiniciar auto-rango |
| `q` / `Esc` | Salir |

---

## 5. Resolución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Can't open device /dev/spidev0.0` | SPI no habilitado o CS en otro pin | `raspi-config` → SPI; probar `-d /dev/spidev0.1` |
| `i2cdetect` no muestra `2a` | Cableado I2C / VIN | Apagar y revisar SDA/SCL/VIN/GND |
| Imagen con franjas o "rota" | Velocidad SPI alta o desincronía | Bajar `--spi-speed` a 10 MHz |
| Imagen "lavada" tras un rato | Falta FFC | Pulsar `f` o esperar FFC automático |
| Temperaturas absurdas (°C) | Sensor no radiométrico (sin TLinear) | La imagen sirve; ignorar °C absoluto |
| `Lepton not responding on I2C` | Dirección/bus I2C | Confirmar bus 1 y dirección `0x2a` |

---

## 6. Buenas prácticas

- Conecta/desconecta siempre con la **Pi apagada**.
- Tócate una superficie metálica conectada a tierra antes de manipular el
  módulo (evitar ESD).
- No apuntes la cámara a fuentes de calor extremas ni al sol.
- Deja que la cámara haga **FFC** periódicamente (automático, o tecla `f`)
  para mantener la calidad de imagen.
- La velocidad SPID está limitada por software a 20 MHz; no la fuerces más
  allá editando el código.

---

## 7. Referencias

- `PLAN.md` — arquitectura del módulo Python y estado de implementación.
- `FINDINGS.md` — detalles técnicos del protocolo VoSPI/CCI extraídos del
  código C del repositorio.
- Datasheet FLIR Lepton 2.5 (SPI ≤ 20 MHz, I2C addr `0x2A`).
