# dbus-rotarex-dime

Liest den Füllstand einer **Alugas/Rotarex-Gasflasche mit DIME/SRG-1-WAVE
Bluetooth-Modul** aus und zeigt sie als echten Tank im **Victron Cerbo GX /
VRM** an – über Node-RED, ohne bleak, ohne gatttool, direkt per BlueZ/D-Bus.

![Tankanzeige im Cerbo GX: LPG bei 61 Prozent, 13 von 21 Litern](docs/cerbo-tanks.png)

Soweit bekannt, gab es dafür bisher keine funktionierende Lösung (siehe
[Victron Community](https://community.victronenergy.com/t/rotarex-dimes-wave-bluetooth-and-cerbo-gx/19384)
und den [Pekaway-Forum-Thread](https://forum.pekaway.de/t/rotarex-dimes-srg-gas-level/1069),
der die entscheidende Vorarbeit zum GATT-Protokoll geleistet hat).

→ Ausführliche Beschreibung des Wegs dorthin:
[cologneone.de/projekte/travelmate-bluetooth](https://cologneone.de/projekte/travelmate-bluetooth)

## Was das hier löst

Die Rotarex-App verlangt beim ersten Verbinden einen PIN (steht auf dem
Typenschild der BLE-Box). Ohne diesen PIN liefert ein direkter Bluetooth-Read
auf die Füllstand-Characteristic immer `ATT error: 0x80`. Das eigentliche
Protokoll dahinter war nirgends dokumentiert – wir haben es durch einen
Bluetooth-HCI-Snoop-Mitschnitt der offiziellen App rekonstruiert:

> **Der PIN wird als reiner ASCII-Text auf Characteristic `05f5d47f`
> geschrieben. Danach ist der Read auf `2b67836b` (Füllstand) sofort
> erfolgreich.**

Entscheidend ist: `05f5d47f` gehört zu einer **anderen Service** als die
Füllstand-Characteristic. Schreibversuche auf die Write-Characteristics der
beworbenen Service führen zu nichts — das war die Sackgasse, in der die Suche
länger festhing.

Details zum vollständigen GATT-Mapping stehen in
[`scripts/read_gas_level.py`](scripts/read_gas_level.py).

## Voraussetzungen

- Victron Cerbo GX (oder anderes Venus-OS-Gerät) mit Node-RED
- [node-red-contrib-victron](https://github.com/victronenergy/node-red-contrib-victron)
  installiert (für die virtuelle Tank-Anzeige — ohne dieses Paket funktioniert
  das Auslesen trotzdem, nur ohne GX-Anzeige)
- `dbus_fast` (Python) muss auf dem Gerät verfügbar sein
- Eine Alugas/Rotarex-Flasche mit DIME/SRG-1-WAVE-Modul in Bluetooth-Reichweite

`install.sh` prüft das alles vorab und sagt, was fehlt — lieber eine klare
Meldung als später ein Bluetooth-Fehler, der in Wahrheit ein fehlendes
Python-Modul ist.

## Installation

```bash
git clone https://github.com/cologneone/dbus-rotarex-dime.git
cd dbus-rotarex-dime
bash install.sh
```

Das Script landet in
`/data/home/nodered/.node-red/dbus-rotarex-dime/scripts/`. Alles unterhalb von
`/data/` überlebt Venus-OS-Firmware-Updates; dieser Unterordner gehört
zusätzlich dem Benutzer `nodered` und ist damit der einzige Ort, an dem
Node-RED später auch Konfiguration und Historie anlegen darf. Ein anderer
Zielordner geht mit `INSTALL_DIR=/pfad/nach/wunsch bash install.sh`.

Danach:

1. **Eigene Flasche finden** (siehe unten) — MAC-Adresse und PIN notieren
2. Beides in die angelegte Konfigurationsdatei eintragen:

   ```bash
   nano /data/home/nodered/.node-red/dbus-rotarex-dime/config
   ```

3. Kurztest — die letzte Zeile muss `"ok": true` enthalten:

   ```bash
   python3 /data/home/nodered/.node-red/dbus-rotarex-dime/scripts/read_gas_level.py
   ```

4. `flows/rotarex-gasflasche.json` in Node-RED importieren (Menü → Import),
   Deploy klicken. Im Flow ist nichts mehr einzutragen.

So sieht der Flow danach aus — Timer, Auslese-Node, Parser, MQTT und der
virtuelle Tank:

![Node-RED-Flow mit Poll-Timer, Auslese-Node, Parser und virtuellem Tank](docs/nodered-flow.png)

### Konfiguration

Alles über benannte Einstellungen, nichts wird im Code eingetragen. Gelesen
wird aus der Konfigurationsdatei
`/data/home/nodered/.node-red/dbus-rotarex-dime/config` (Zeilen der Form
`NAME=Wert`, `#` leitet einen Kommentar ein). **Umgebungsvariablen gleichen
Namens haben Vorrang**, wer also lieber alles im `exec`-Node stehen hat, kann
das weiterhin tun.

| Name | Pflicht | Bedeutung |
|---|---|---|
| `ROTAREX_MAC` | ja | MAC-Adresse der eigenen Flasche, Format `AA:BB:CC:DD:EE:FF` |
| `ROTAREX_PIN` | ja | PIN vom Typenschild der BLE-Box |
| `ROTAREX_ADAPTER` | nein | Bluetooth-Adapter, Standard `hci0` |
| `ROTAREX_HISTORY` | nein | Pfad zu einer CSV-Datei; ist er gesetzt, wird jeder **erfolgreiche** Abruf dort angehängt |
| `ROTAREX_CONFIG` | nein | Abweichender Pfad der Konfigurationsdatei |

Die Konfigurationsdatei bekommt vom Installer die Rechte `600`. Der Grund für
die Trennung: Ein exportierter Node-RED-Flow wandert schnell mal in ein Forum
oder auf einen Screenshot — der PIN sollte da nicht mitfahren.

Fehlen MAC oder PIN, bricht das Script sofort mit `{"ok": false, "error":
"not_configured"}` ab, statt in einen Bluetooth-Fehler zu laufen.

### Fehlercodes

Die letzte Ausgabezeile ist immer JSON. `"ok": true` bedeutet, dass wirklich
ein Füllstand gelesen wurde — nie einfach nur, dass das Script durchgelaufen
ist.

| `error` | Bedeutung |
|---|---|
| `not_configured` | MAC oder PIN fehlen |
| `device_not_in_cache` | BlueZ kennt das Gerät nicht — außer Reichweite oder Bluetooth aus |
| `connect_failed` | Verbindung kam nicht zustande |
| `services_not_resolved` | verbunden, aber der GATT-Baum kam nicht |
| `pin_characteristic_not_found` | PIN-Characteristic fehlt — anderes Gerät? |
| `gas_characteristic_not_found` | Füllstand-Characteristic fehlt |
| `pin_write_failed` | PIN ließ sich nicht schreiben (Details in `detail`) |
| `gas_read_failed` | Lesen scheiterte — bei `ATT error: 0x80` hat der PIN nicht gegriffen |
| `gas_value_empty` | Lesen ging durch, lieferte aber kein Byte |

Der Batteriestand des Senders ist bewusst optional: Fehlt er, gilt der Abruf
trotzdem als erfolgreich, und der Grund steht als `battery_error` dabei.

### Tank im GX einrichten

Der virtuelle Tank taucht als ganz normales Gerät auf, mit Node-RED als Quelle:

![Gerätedetails im Cerbo: Verbindung Node-RED, Produkt Virtual tank sensor](docs/cerbo-lpg-geraet.png)

Unter *Setup* noch Kapazität und Flüssigkeitstyp setzen — für eine 11-kg-Flasche
sind das 21 Liter und LPG. Den Rest rechnet die Oberfläche selbst:

![Tank-Einstellungen im Cerbo: Kapazität 21 Liter, Flüssigkeitstyp LPG](docs/cerbo-lpg-setup.png)

**Zu beachten:** Der Funktionsknoten im Flow schickt `/Capacity` und
`/FluidType` bei *jedem* Abruf mit. Eine abweichende Einstellung in der
GX-Oberfläche ist damit spätestens nach 15 Minuten wieder überschrieben. Wer
seine Kapazität lieber dort pflegt, nimmt die beiden Felder im Knoten heraus —
wer eine andere Flaschengröße hat, trägt sie dort ein (Angabe in m³, `0.021`
sind 21 Liter).

### Historie mitschreiben

```bash
ROTAREX_HISTORY=/data/home/nodered/.node-red/dbus-rotarex-dime/history.csv
```

Vier Spalten, keine Kopfzeile, Zeitstempel in UTC nach ISO 8601:

```
2026-08-18T21:59:29.695961+00:00,60,60,81
```

Also `Zeitstempel,Rohwert,Prozent,Sender-Batterie`. Geschrieben wird nur bei
erfolgreichem Abruf — eine Historie, in der Fehlversuche als leere Werte
stehen, verzerrt jede spätere Verbrauchsauswertung. Scheitert das Schreiben,
steht der Grund als `history_error` im JSON-Ergebnis, und der Flow zeigt ihn in
der Statuszeile an.

**Achtung bei Venus OS:** Node-RED läuft als Benutzer `nodered` und darf
nicht direkt nach `/data/` schreiben. Beschreibbar ist
`/data/home/nodered/.node-red/`.

## Eigene Flasche finden

MAC-Adresse und PIN findest du auf dem Typenschild der BLE-Sende-Box direkt
an der Flasche (nicht am Sensor selbst). Alternativ per BLE-Scan (z. B.
[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile))
nach einem Gerät namens `SRG-1-WAVE` suchen.

Die GATT-UUIDs (`2b67836a...`, `05f5d47e...`) sollten bei allen Geräten
dieser Modell-Reihe identisch sein — nur MAC-Adresse und PIN sind
geräteindividuell.

## Kalibrierung

Der Rohwert ist ein einzelnes Byte. Nach bisherigem Stand entspricht er
**direkt dem Prozent-Füllstand** — in den vorliegenden Messpunkten war kein
Offset und keine Kurve nötig.

Belegt ist das durch zwei unabhängige Beobachtungen: einen Messpunkt außerhalb
der oberen Sättigung (Rohwert 78 bei App-Anzeige 78 %) und einen zeitnahen
Vergleich — App 60 %, Cerbo zwei Minuten zuvor 61 %, was genau dem
15-Minuten-Takt entspricht.

<img src="docs/app-trend.png" alt="Rotarex-App mit 60 Prozent und fallendem Trenddiagramm" width="320">

Zwei Punkte im oberen Mittelfeld sind aber kein Beweis für den ganzen Bereich.
Unten fehlen bislang Referenzwerte schlicht deshalb, weil die Flasche dazu erst
leer werden muss. Und am oberen Ende ist die Auflösung ohnehin gering — die
offizielle App zeigt für den gesamten Bereich 94–100 % nur „voll“ an. Wer
eigene Messpunkte hat, gerne her damit: Beiträge und Issues sind willkommen.

## Script aktualisieren

Ohne erneutes Auschecken, direkt auf dem Gerät:

```bash
curl -fsSL -o /data/home/nodered/.node-red/dbus-rotarex-dime/scripts/read_gas_level.py \
  https://raw.githubusercontent.com/cologneone/dbus-rotarex-dime/main/scripts/read_gas_level.py
```

## Deinstallation

```bash
bash uninstall.sh
```

Entfernt Script und Konfigurationsdatei — in der steht der PIN, die geht als
Erstes. Die Historie bleibt absichtlich liegen: Sie ist das Einzige hier, was
sich nicht wiederherstellen lässt; mit `MIT_HISTORIE=ja bash uninstall.sh`
verschwindet auch sie. Den Node-RED-Flow und den virtuellen Tank-Service musst
du selbst löschen — das Script sagt dir, wie.

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
- Node-RED läuft als Benutzer `nodered` ohne Schreibrecht auf `/data/`.
- Das BLE-Modul lässt **nur eine Verbindung gleichzeitig** zu. Solange die
  Rotarex-App verbunden ist, läuft der Abruf auf dem Cerbo ins Leere — und
  umgekehrt. Deshalb trennt das Script am Ende immer, auch im Fehlerfall.
- Ein Abruf kann im schlechtesten Fall (Gerät nicht im Cache, mehrere
  Discovery- und Connect-Durchgänge) knapp anderthalb Minuten dauern. Der
  Timeout des `exec`-Node steht deshalb auf 90 Sekunden — wer ihn kleiner
  setzt, bekommt gelegentlich abgeschnittene Läufe.

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
