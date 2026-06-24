# Waveshare Relay — Custom HACS Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/mrwolfjunior/ha-waveshare)](https://github.com/mrwolfjunior/ha-waveshare/releases)

Control **Waveshare Modbus RTU Relay** boards and read digital inputs from **N4DIH32** boards over an Ethernet/RS485 bridge — natively from Home Assistant, with proper `light` and `cover` entities.

## Why this integration?

The native HA Modbus integration requires two separate commands to simulate a button press (turn on → wait → turn off), which is unreliable. This integration uses the **Waveshare "Flash ON" hardware command** — a single Modbus frame that tells the board to pulse the relay for a precise duration, with no Python timers involved.

| Feature | Native Modbus YAML | This integration |
|---|---|---|
| Pulse reliability | ⚠️ Two commands + timer | ✅ Single hardware command |
| Entity types | `switch` | `light`, `cover`, `binary_sensor` |
| Configuration | Long YAML | UI config flow |
| Group commands | ❌ Unreliable | ✅ FC 0x0F bulk write |
| Per-device pulse timing | ❌ | ✅ |

## Supported Hardware

| Device | Role |
|---|---|
| Waveshare Modbus RTU Relay 32CH | Relay commands (slave 1) |
| N4DIH32 32-CH Digital Input RS485 | State reading (slave 2) |

Connected via any Ethernet→RS485 bridge (RTU over TCP).

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/mrwolfjunior/ha-waveshare` as type **Integration**
3. Search for **Waveshare Relay** and install
4. Restart Home Assistant

### Manual

Copy the `custom_components/waveshare_relay/` folder into your HA `config/custom_components/` directory and restart.

## Configuration

### 1. Add the integration

**Settings → Devices & Services → + Add Integration → Waveshare Relay**

Fill in:

| Field | Example | Description |
|---|---|---|
| Host | `10.1.1.14` | IP of the Ethernet bridge |
| Port | `26` | TCP port |
| Relay board slave ID | `1` | Modbus slave of the relay board |
| Input board slave ID | `2` | Modbus slave of the N4DIH32 |
| Polling interval | `5` | Seconds between state reads |

### 2. Add devices

After setup, click **Configure** on the integration card to open the device manager.

**Add a Light:**
- Relay index `0–31` → which relay to pulse
- Slave + register → where to read the current state (N4DIH32)
- Pulse duration (ms) → default 400 ms

**Add a Cover (blind/shutter):**
- Open relay + Close relay → two separate relay indices
- Pulse duration (ms) → default 400 ms (open/close impulse)
- Tilt duration (ms) → default 4000 ms (slat fully open/close)

## Relay pulse address mapping (Waveshare protocol)

| Command | Modbus address | Value |
|---|---|---|
| Flash ON relay N | `0x0200 + N` | `duration × 100ms` |
| Flash OFF relay N | `0x0400 + N` | `duration × 100ms` |
| Read all relay states | FC01, addr 0, qty 32 | — |
| Read input registers | FC03, addr 128+, qty N | — |

## Versioning & Updates

Releases follow [Semantic Versioning](https://semver.org/). Push a tag `vX.Y.Z` to trigger an automatic GitHub release — HACS will detect the new version and offer the update.

```bash
git tag v1.0.1
git push origin v1.0.1
```

## License

MIT
