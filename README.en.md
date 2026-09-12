# dbus-rotarex-dime

*[Deutsche Fassung](README.md) · English version*

Reads the fill level of an **Alugas/Rotarex gas bottle with a DIMES WAVE module**
(it shows up as `SRG-1-WAVE` in a BLE scan) and displays it as a real tank in the
**Victron Cerbo GX / VRM** — through Node-RED, without bleak, without gatttool,
straight over BlueZ/D-Bus.

![Tank display on the Cerbo GX: LPG at 61 percent, 13 of 21 litres](docs/cerbo-tanks.png)

As far as I can tell there was no working solution for this before (see the
[Victron Community thread](https://community.victronenergy.com/t/rotarex-dimes-wave-bluetooth-and-cerbo-gx/19384)
and the [Pekaway forum thread](https://forum.pekaway.de/t/rotarex-dimes-srg-gas-level/1069),
which did the essential groundwork on the GATT layout).

→ The full story of how it was worked out (in German):
[cologneone.de/projekte/travelmate-bluetooth](https://cologneone.de/projekte/travelmate-bluetooth)

## What this solves

The Rotarex app asks for a PIN the first time it connects (the PIN is printed on
the type plate of the BLE box). Without that PIN, a direct Bluetooth read of the
level characteristic always returns `ATT error: 0x80`. The protocol behind it was
documented nowhere — it was reconstructed from a Bluetooth HCI snoop log of the
official app:

> **The PIN is written as plain ASCII text to characteristic `05f5d47f`.
> After that, the read on `2b67836b` (fill level) succeeds immediately.**

The key point: `05f5d47f` belongs to a **different service** than the level
characteristic. Writing to the write characteristics of the *advertised* service
gets you nowhere — that was the dead end the search was stuck in for a while.

The complete GATT mapping is documented in
[`scripts/read_gas_level.py`](scripts/read_gas_level.py).

## Requirements

- A Victron Cerbo GX (or another Venus OS device) with Node-RED
- [node-red-contrib-victron](https://github.com/victronenergy/node-red-contrib-victron)
  installed (for the virtual tank display — reading the bottle works without it,
  you just don't get the tank on the GX)
- `dbus_fast` (Python) available on the device
- An Alugas/Rotarex bottle with a DIMES WAVE module in Bluetooth range

`install.sh` checks all of this up front and tells you what is missing — a clear
message beats a Bluetooth error that is really a missing Python module.

## Installation

```bash
git clone https://github.com/cologneone/dbus-rotarex-dime.git
cd dbus-rotarex-dime
bash install.sh
```

The script ends up in
`/data/home/nodered/.node-red/dbus-rotarex-dime/scripts/`. Everything below
`/data/` survives Venus OS firmware updates, and this subfolder additionally
belongs to the user `nodered` — which makes it the only place where Node-RED is
later allowed to create its config and history files.

A different target folder works with `INSTALL_DIR=/your/path bash install.sh` and
takes full effect: the script looks for its configuration **relative to itself**,
one level above `scripts/`, so there is no hard-coded path to maintain. Only the
call in the flow's `exec` node has to be adjusted.

Then:

1. **Find your own bottle** (see below) — note down the MAC address and the PIN
2. Put both into the configuration file the installer created:

   ```bash
   nano /data/home/nodered/.node-red/dbus-rotarex-dime/config
   ```

3. Quick test — the last line must contain `"ok": true`:

   ```bash
   python3 /data/home/nodered/.node-red/dbus-rotarex-dime/scripts/read_gas_level.py
   ```

4. Import `flows/rotarex-gasflasche.json` into Node-RED (menu → Import) and hit
   Deploy. Nothing else needs to be filled in inside the flow.

   The first read runs two seconds after the deploy and often fails with
   `timeout`, because the process before it is still holding the Bluetooth
   connection. That is not a failed installation — the next 15-minute cycle
   delivers.

This is what the flow looks like — timer, read node, parser, MQTT and the virtual
tank:

![Node-RED flow with poll timer, read node, parser and virtual tank](docs/nodered-flow.png)

### Configuration

Everything is a named setting, nothing goes into the code. Values are read from
the configuration file next to the install folder (lines of the form
`NAME=value`, `#` starts a comment). **Environment variables of the same name
take precedence**, so if you prefer to keep everything in the `exec` node, you
still can.

| Name | Required | Meaning |
|---|---|---|
| `ROTAREX_MAC` | yes | MAC address of your bottle, format `AA:BB:CC:DD:EE:FF` |
| `ROTAREX_PIN` | yes | PIN from the type plate of the BLE box |
| `ROTAREX_ADAPTER` | no | Bluetooth adapter, default `hci0` |
| `ROTAREX_HISTORY` | no | Path to a CSV file; if set, every **successful** read is appended to it |
| `ROTAREX_TIMEOUT` | no | Overall budget in seconds until output, default `85` |
| `ROTAREX_CONFIG` | no | Alternative path to the configuration file |

The installer gives the configuration file mode `600`. The reason for keeping it
separate: an exported Node-RED flow quickly ends up in a forum post or on a
screenshot — the PIN should not travel with it.

If the MAC or the PIN is missing, the script aborts immediately with
`{"ok": false, "error": "not_configured"}` instead of running into a Bluetooth
error.

### Error codes

The last line of output is always JSON. `"ok": true` means a fill level was
really read — never just that the script ran to completion.

| `error` | Meaning |
|---|---|
| `not_configured` | MAC or PIN missing |
| `device_not_in_cache` | BlueZ does not know the device — out of range or Bluetooth off |
| `connect_failed` | Connection could not be established |
| `services_not_resolved` | Connected, but the GATT tree never arrived |
| `pin_characteristic_not_found` | PIN characteristic missing — different device? |
| `gas_characteristic_not_found` | Level characteristic missing |
| `pin_write_failed` | PIN could not be written (see `detail`) |
| `gas_read_failed` | Read failed — on `ATT error: 0x80` the PIN did not take |
| `gas_value_empty` | Read went through but returned no byte |
| `timeout` | Overall time exceeded, see below |

The sender's battery level is deliberately optional: if it is missing, the read
still counts as successful, the reason is reported as `battery_error`, and the
fourth field in the history stays empty.

### Runtime and reachability

A normal read takes around 30 seconds. If the device first has to be scanned back
into the BlueZ cache, worst case is about 70 seconds — hence the 90-second `exec`
timeout in the flow.

Worth knowing: **BlueZ calls have no timeout of their own.** If the module is out
of range, or another connection is holding it — it only allows one at a time —
then `Connect()` simply hangs. Without a countermeasure a read can run
indefinitely; eleven minutes have been measured here before the other side let go.

That is why the script aborts itself after `ROTAREX_TIMEOUT` seconds, still tries
to disconnect, and reports `timeout`. That is far better than being killed by
Node-RED: no output would arrive at all, and the flow would show a meaningless
parse error.

The value is deliberately an **overall budget until output**, not a budget for the
work alone. Cleaning up costs time too, and `asyncio.wait_for` waits for the
cancelled task to finish cleaning up. The 85 seconds are therefore split like
this:

| Share | Seconds |
|---|---|
| the read itself | 77 |
| regular disconnect at the end | 3 |
| disconnect attempt after a timeout | 5 |

If the cleanup were added on top instead of being carved out, it would be 93
seconds — and the `exec` node would have cut in at 90, right before the timeout
message is printed.

So a `timeout` is usually **not a software error** but the statement "nobody was
available just now". The next read usually has the value back. Possible blockers:
the vendor app on your phone, a second read started by hand, or simply lack of
range. If it happens permanently: disconnect the app, check range and the two AAA
batteries in the sender box.

### Setting up the tank on the GX

The virtual tank appears as an ordinary device, with Node-RED as its source:

![Device details on the Cerbo: connection Node-RED, product Virtual tank sensor](docs/cerbo-lpg-geraet.png)

Capacity and fluid type come with the flow: the **LPG** node carries them as
`tank_capacity` (0.021 m³ = 21 litres) and `fluid_type` (8 = LPG). Nothing needs
to be set in the GX after importing — this is what it looks like there:

![Tank settings on the Cerbo: capacity 21 litres, fluid type LPG](docs/cerbo-lpg-setup.png)

#### A different bottle size: two places, change both

| # | Exact location | Value for 11 kg |
|---|---|---|
| 1 | node **LPG** → field *Capacity* | `0.021` |
| 2 | function **Parse Ergebnis** → constant `KAPAZITAET_M3` | `0.021` |

Always in **m³**: 5 kg = `0.0105`, 11 kg = `0.021`, 14 kg = `0.0275`.

If the two disagree, the VRM console computes with one number and the GX Touch
display with the other — the percentage stays correct, only the litres drift
apart.

Why two places at all? The `victron-virtual` node creates `/Capacity` and
`/FluidType` at startup from **its own configuration** and ignores both paths in
the payload. Measured on 12 Sep 2026: a `/Capacity` set by hand to `0.025` was
still unchanged after a successful read. From the payload the node takes only
`/Level`, `/Remaining` and `/Status` — and `/Remaining`, the litre value, has to
come from the flow. Change the capacity in only one of the two places and you get
no error, just two different readings.

**Do not remove `/Remaining`.** The VRM console computes the litre value itself
from capacity × level, so it looks right even without it. The physical GX Touch
display does not: it shows the last `/Remaining` value it ever received and
freezes it. That is exactly how it came to show 8 of 21 litres at 99 percent
while VRM next to it showed 21 of 21.

### Writing a history

```bash
ROTAREX_HISTORY=/data/home/nodered/.node-red/dbus-rotarex-dime/history.csv
```

Four columns, no header row, timestamp in UTC per ISO 8601:

```
2026-08-18T21:59:29.695961+00:00,60,60,81
```

That is `timestamp,raw value,percent,sender battery`. Only successful reads are
written — a history in which failed attempts appear as empty values distorts every
later consumption analysis. If only the battery level is missing, the fourth field
stays empty. If writing fails, the reason shows up as `history_error` in the JSON
result and the flow displays it in its status line.

**Careful on Venus OS:** Node-RED runs as the user `nodered` and may not write
directly into `/data/`. Writable is `/data/home/nodered/.node-red/`.

## Finding your own bottle

The MAC address and the PIN are printed on the type plate of the BLE sender box on
the bottle (not on the sensor itself). Alternatively, do a BLE scan (e.g. with
[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile))
and look for a device named `SRG-1-WAVE`.

The GATT UUIDs (`2b67836a...`, `05f5d47e...`) should be identical across all
devices of this model range — only the MAC address and the PIN are
device-specific.

## Calibration

The raw value is a single byte. As things stand it corresponds **directly to the
percentage** — none of the measured points needed an offset or a curve.

Two independent observations back this up: one point outside the upper saturation
zone (raw value 78 with the app showing 78 %) and a near-simultaneous comparison —
app 60 %, Cerbo 61 % two minutes earlier, which matches the 15-minute poll
interval exactly.

<img src="docs/app-trend.png" alt="Rotarex app showing 60 percent and a falling trend chart" width="320">

Two points in the upper middle range are of course no proof for the whole scale.
At the bottom, reference values were simply missing at first because the bottle has
to run empty for that. And at the top end the resolution is poor anyway — the
official app shows nothing but "full" for the entire 94–100 % range. If you have
measurement points of your own, please share them: issues and discussions are
welcome.

## Updating the script

Without checking out again, straight on the device:

```bash
curl -fsSL -o /data/home/nodered/.node-red/dbus-rotarex-dime/scripts/read_gas_level.py \
  https://raw.githubusercontent.com/cologneone/dbus-rotarex-dime/main/scripts/read_gas_level.py
```

## Uninstalling

```bash
bash uninstall.sh
```

Removes the script and the configuration file — the PIN lives in the latter, so it
goes first. The history is deliberately left in place: it is the only thing here
that cannot be recreated. `MIT_HISTORIE=ja bash uninstall.sh` removes that too.
The Node-RED flow and the virtual tank service you have to delete yourself — the
script tells you how.

## Known pitfalls

- **BlueZ loses the device object** between connections when no active scan is
  running → the script therefore does a short scan when needed, before it
  introspects the device.
- **`le-connection-abort-by-local`**: happens when you connect right after
  stopping discovery — add a short pause.
- **`dbus_fast` expects a `bytearray`**, not a Python `list`, for
  `call_write_value()`.
- Node-RED `exec` node output can be multi-line (diagnostic messages before the
  JSON) — when parsing, always treat only the last line as JSON.
- Node-RED runs as the user `nodered`, with no write permission on `/data/`.
- The BLE module allows **only one connection at a time**. While the Rotarex app
  is connected, the read on the Cerbo comes up empty — and vice versa. That is why
  the script always disconnects, including on errors.
- **BlueZ calls block without a timeout of their own** — see the runtime section
  above. Hence the built-in cap, and hence the separate budget for disconnecting
  during cleanup: without it, a hanging `Disconnect()` could eat the cap again.

## Acknowledgements

- The [Pekaway forum](https://forum.pekaway.de/t/rotarex-dimes-srg-gas-level/1069)
  for the first GATT dump and the groundwork
- [victronenergy/node-red-contrib-victron](https://github.com/victronenergy/node-red-contrib-victron)

## Disclaimer

This project is not affiliated with Rotarex, SRG Schulz + Rackow Gastechnik GmbH
or Victron Energy. Use at your own risk. It only **reads** your own hardware for
interoperability purposes — no firmware data is modified or circumvented.

## Licence

MIT — see [LICENSE](LICENSE).
