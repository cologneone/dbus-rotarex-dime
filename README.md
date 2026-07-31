# dbus-rotarex-dime

Liest den Füllstand einer **Alugas/Rotarex-Gasflasche mit DIME/SRG-1-WAVE
Bluetooth-Modul** aus und zeigt sie als echten Tank im **Victron Cerbo GX /
VRM** an – über Node-RED, ohne bleak, ohne gatttool, direkt per BlueZ/D-Bus.

Soweit bekannt, gab es dafür bisher keine funktionierende Lösung (siehe
[Victron Community](https://community.victronenergy.com/t/rotarex-dimes-wave-bluetooth-and-cerbo-gx/19384)
und den [Pekaway-Forum-Thread](https://forum.pekaway.de/t/rotarex-dimes-srg-gas-level/1069),
der die entscheidende Vorarbeit zum GATT-Protokoll geleistet hat).

## Was das hier löst

Die Rotarex-App verlangt beim ersten Verbinden einen PIN (steht auf dem
Typenschild der BLE-Box). Ohne diesen PIN liefert ein direkter Bluetooth-Read
auf die Füllstand-Characteristic immer `ATT error: 0x80`. Das eigentliche
Protokoll dahinter war nirgends dokumentiert – wir haben es durch einen
Bluetooth-HCI-Snoop-Mitschnitt der offiziellen App rekonstruiert:

> **Der PIN wird als reiner ASCII-Text auf Characteristic `05f5d47f`
> geschrieben. Danach ist der Read auf `2b67836b` (Füllstand) sofort
> erfolgreich.**

Details zum vollständigen GATT-Mapping stehen in [`scripts/read_gas_level.py`](scripts/read_gas_level.py).

## Voraussetzungen

- Victron Cerbo GX (oder anderes Venus-OS-Gerät) mit Node-RED
- [node-red-contrib-victron](https://github.com/victronenergy/node-red-contrib-victron)
  installiert (für die virtuelle Tank-Anzeige — ohne dieses Paket funktioniert
  das Auslesen trotzdem, nur ohne GX-Anzeige)
- `dbus_fast` (Python) muss auf dem Gerät verfügbar sein
- Eine Alugas/Rotarex-Flasche mit DIME/SRG-1-WAVE-Modul in Bluetooth-Reichweite

## Installation

```bash
git clone https://github.com/<dein-username>/dbus-rotarex-dime.git
cd dbus-rotarex-dime
bash install.sh
```

Das Script kopiert `scripts/read_gas_level.py` nach `/data/dbus-rotarex-dime/`
(überlebt Venus-OS-Firmware-Updates). Danach:

1. **Eigene Flasche finden** (siehe unten)
2. `DEVICE_PATH` und `PIN_BYTES` in `read_gas_level.py` anpassen
3. `flows/rotarex-gasflasche.json` in Node-RED importieren (Menü → Import)
4. Im `exec`-Node den Skriptpfad prüfen
5. Deploy

## Eigene Flasche finden

MAC-Adresse und PIN findest du auf dem Typenschild der BLE-Sende-Box direkt
an der Flasche (nicht am Sensor selbst). Alternativ per BLE-Scan (z. B.
[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile))
nach einem Gerät namens `SRG-1-WAVE` suchen.

Die GATT-UUIDs (`2b67836a...`, `05f5d47e...`) sollten bei allen Geräten
dieser Modell-Reihe identisch sein — nur MAC-Adresse und PIN sind
geräteindividuell.

## Kalibrierung

Der Rohwert ist ein einzelnes Byte, das grob dem Prozent-Füllstand
entspricht (0,5–4,5V @5V ratiometrisch laut Sensor-Typenschild, 0–100%).
Am oberen Ende der Skala ist die Auflösung gering — die offizielle App zeigt
z. B. für den gesamten Bereich 94–100% nur "voll" an, ohne feinere
Abstufung. Für eine echte Kalibrierkurve über den vollen Bereich sind noch
weitere Referenzpunkte nötig — Beiträge/Issues mit euren Beobachtungen sind
willkommen.

## Bekannte Stolperfallen

- **BlueZ verliert das Geräteobjekt** zwischen Verbindungen, wenn kein
  aktiver Scan läuft → das Script scannt deshalb bei Bedarf kurz, bevor es
  das Gerät introspiziert.
- **`le-connection-abort-by-local`**: tritt auf, wenn man direkt nach
  Stop-Discovery verbindet — kurze Pause einbauen.
- **`dbus_fast` erwartet `bytearray`**, kein Python-`list`, für
  `call_write_value()`.
- Node-RED-`exec`-Node-Ausgabe kann mehrzeilig sein (Diagnosemeldungen vor
  dem JSON) — beim Parsen immer nur die letzte Zeile als JSON behandeln.

## Danksagung

- Dem [Pekaway-Forum](https://forum.pekaway.de/t/rotarex-dimes-srg-gas-level/1069)
  für den ersten GATT-Dump und die Vorarbeit
- [victronenergy/node-red-contrib-victron](https://github.com/victronenergy/node-red-contrib-victron)

## Haftungsausschluss

Dieses Projekt steht in keiner Verbindung zu Rotarex, SRG Schulz + Rackow
Gastechnik GmbH oder Victron Energy. Nutzung auf eigene Gefahr. Es handelt
sich um reines Auslesen (Read) der eigenen Hardware zu
Interoperabilitätszwecken — es werden keine Firmware-Daten verändert oder
umgangen.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
