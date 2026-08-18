#!/bin/bash
# install.sh - dbus-rotarex-dime
#
# Prüft die Voraussetzungen, kopiert das Auslese-Script dorthin, wo Node-RED
# es lesen und schreiben darf, und legt eine Konfigurationsdatei an.
#
# Version: 1.3.0
# Historie:
#   1.0.0 — Erstveröffentlichung
#   1.1.0 — Konfiguration läuft über Umgebungsvariablen statt über
#           Änderungen im Script
#   1.2.0 — Installation standardmäßig unterhalb des Node-RED-Datenordners.
#           Node-RED läuft auf Venus OS als Benutzer 'nodered' und darf
#           nicht direkt nach /data schreiben — die Historie landete dort
#           sonst nie.
#   1.3.0 — Vorabprüfung der Voraussetzungen; Konfigurationsdatei für MAC
#           und PIN, damit die Zugangsdaten nicht im Node-RED-Flow stehen
#
# Nutzung (auf dem Cerbo/Venus-OS-Gerät per SSH):
#   bash install.sh
#
# Anderer Zielordner:
#   INSTALL_DIR=/pfad/nach/wunsch bash install.sh

set -e

INSTALL_DIR="${INSTALL_DIR:-/data/home/nodered/.node-red/dbus-rotarex-dime}"
CONFIG_FILE="$INSTALL_DIR/config"

echo "== dbus-rotarex-dime Installer =="
echo

# ---------------------------------------------------------------- Prüfung
# Lieber vorher ehrlich sagen, was fehlt, als später einen Bluetooth-Fehler
# suchen, der in Wahrheit ein fehlendes Python-Modul ist.

fehler=0

pruefe() {
  # $1 = Beschreibung, $2... = Kommando
  local text="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  [ok]     $text"
  else
    echo "  [FEHLT]  $text"
    fehler=$((fehler + 1))
  fi
}

echo "Voraussetzungen:"
pruefe "Python 3" command -v python3
pruefe "Python-Modul dbus_fast" python3 -c "import dbus_fast"
pruefe "Bluetooth-Adapter ${ROTAREX_ADAPTER:-hci0}" test -d "/sys/class/bluetooth/${ROTAREX_ADAPTER:-hci0}"

if [ -d /data/home/nodered/.node-red ]; then
  echo "  [ok]     Node-RED-Datenordner"
else
  echo "  [Hinweis] /data/home/nodered/.node-red nicht gefunden — offenbar"
  echo "            kein Venus OS. Das Script laeuft trotzdem, nur der"
  echo "            Standardpfad passt dann vermutlich nicht (INSTALL_DIR)."
fi

if [ -d /data/home/nodered/.node-red/node_modules/@victronenergy/node-red-contrib-victron ]; then
  echo "  [ok]     node-red-contrib-victron"
else
  echo "  [Hinweis] node-red-contrib-victron nicht gefunden — das Auslesen"
  echo "            funktioniert trotzdem, nur die Tank-Anzeige im GX fehlt."
fi
echo

if [ "$fehler" -gt 0 ]; then
  echo "$fehler Voraussetzung(en) fehlen. Nachrüsten, dann erneut starten:"
  echo "  dbus_fast:  pip3 install dbus_fast"
  echo "  Bluetooth:  in den GX-Einstellungen einschalten"
  echo
  exit 1
fi

# ------------------------------------------------------------ Installation

mkdir -p "$INSTALL_DIR/scripts"
cp -v scripts/read_gas_level.py "$INSTALL_DIR/scripts/"
chmod +x "$INSTALL_DIR/scripts/read_gas_level.py"

if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<'VORLAGE'
# Konfiguration fuer read_gas_level.py
# MAC und PIN stehen auf dem Typenschild der BLE-Box an der Flasche.
ROTAREX_MAC=AA:BB:CC:DD:EE:FF
ROTAREX_PIN=1234

# Optional:
ROTAREX_ADAPTER=hci0
ROTAREX_HISTORY=/data/home/nodered/.node-red/dbus-rotarex-dime/history.csv
VORLAGE
  echo "Konfigurationsvorlage angelegt: $CONFIG_FILE"
else
  echo "Konfiguration bleibt unveraendert: $CONFIG_FILE"
fi

# Der PIN steht in dieser Datei — sie geht niemanden sonst etwas an.
chmod 600 "$CONFIG_FILE"

# Auf Venus OS gehoert der Ordner sonst root, und Node-RED darf weder die
# Konfiguration lesen noch die Historie anlegen.
if id nodered >/dev/null 2>&1; then
  chown -R nodered:nodered "$INSTALL_DIR" 2>/dev/null || true
fi

echo
echo "Script installiert nach: $INSTALL_DIR/scripts/read_gas_level.py"
echo
echo "Jetzt MAC und PIN eintragen:"
echo "  nano $CONFIG_FILE"
echo
echo "Kurztest auf der Kommandozeile:"
echo "  python3 $INSTALL_DIR/scripts/read_gas_level.py"
echo
echo "Erwartete Ausgabe (letzte Zeile):"
echo '  {"ok": true, "gas_raw": 99, "gas_percent": 99, "battery_percent": 86}'
echo
echo "Node-RED-Flow importieren:"
echo "  1. Node-RED-Oberflaeche oeffnen (i.d.R. https://<Cerbo-IP>:1881)"
echo "  2. Menue -> Import -> Datei auswaehlen: flows/rotarex-gasflasche.json"
echo "  3. Im 'exec'-Node nur noch den Pfad pruefen — MAC und PIN stehen"
echo "     in der Konfigurationsdatei und muessen nicht in den Flow"
echo "  4. Deploy klicken"
echo
echo "Historie: $INSTALL_DIR/history.csv"
echo "  Format: Zeitstempel (UTC),gas_raw,gas_percent,battery_percent"
echo "  Ohne Kopfzeile, eine Zeile je erfolgreichem Abruf."
echo
echo "Spaeteres Aktualisieren des Scripts ohne erneutes Auschecken:"
echo "  curl -fsSL -o $INSTALL_DIR/scripts/read_gas_level.py \\"
echo "    https://raw.githubusercontent.com/cologneone/dbus-rotarex-dime/main/scripts/read_gas_level.py"
echo
echo "Deinstallieren spaeter mit: bash uninstall.sh"
echo
echo "Fertig."
