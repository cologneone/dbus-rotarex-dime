#!/bin/bash
# install.sh - dbus-rotarex-dime
#
# Kopiert das Auslese-Script dorthin, wo Node-RED es lesen und schreiben
# darf, und gibt Hinweise zum Import des Node-RED-Flows.
#
# Version: 1.2.0
# Historie:
#   1.0.0 — Erstveröffentlichung
#   1.1.0 — Konfiguration läuft über Umgebungsvariablen statt über
#           Änderungen im Script
#   1.2.0 — Installation standardmäßig unterhalb des Node-RED-Datenordners.
#           Node-RED läuft auf Venus OS als Benutzer 'nodered' und darf
#           nicht direkt nach /data schreiben — die Historie landete dort
#           sonst nie.
#
# Nutzung (auf dem Cerbo/Venus-OS-Gerät per SSH):
#   bash install.sh
#
# Anderer Zielordner:
#   INSTALL_DIR=/pfad/nach/wunsch bash install.sh

set -e

INSTALL_DIR="${INSTALL_DIR:-/data/home/nodered/.node-red/dbus-rotarex-dime}"

echo "== dbus-rotarex-dime Installer =="
echo

mkdir -p "$INSTALL_DIR/scripts"
cp -v scripts/read_gas_level.py "$INSTALL_DIR/scripts/"
chmod +x "$INSTALL_DIR/scripts/read_gas_level.py"

# Auf Venus OS gehoert der Ordner sonst root, und Node-RED darf die
# Historie nicht anlegen.
if id nodered >/dev/null 2>&1; then
  chown -R nodered:nodered "$INSTALL_DIR" 2>/dev/null || true
fi

echo
echo "Script installiert nach: $INSTALL_DIR/scripts/read_gas_level.py"
echo
echo "WICHTIG - das Script wird über Umgebungsvariablen konfiguriert."
echo "MAC-Adresse und PIN stehen auf dem Typenschild der BLE-Box."
echo
echo "Kurztest auf der Kommandozeile:"
echo "  ROTAREX_MAC=AA:BB:CC:DD:EE:FF ROTAREX_PIN=1234 \\"
echo "  python3 $INSTALL_DIR/scripts/read_gas_level.py"
echo
echo "Erwartete Ausgabe (letzte Zeile):"
echo '  {"ok": true, "gas_raw": 99, "gas_percent": 99, "battery_percent": 86}'
echo
echo "Node-RED-Flow importieren:"
echo "  1. Node-RED-Oberfläche öffnen (i.d.R. https://<Cerbo-IP>:1881)"
echo "  2. Menü -> Import -> Datei auswählen: flows/rotarex-gasflasche.json"
echo "  3. Im 'exec'-Node MAC und PIN eintragen"
echo "  4. Deploy klicken"
echo
echo "Optional: Historie mitschreiben lassen mit"
echo "  ROTAREX_HISTORY=$INSTALL_DIR/history.csv"
echo "  Format: Zeitstempel (UTC),gas_raw,gas_percent,battery_percent"
echo "  Ohne Kopfzeile, eine Zeile je erfolgreichem Abruf."
echo
echo "Späteres Aktualisieren des Scripts ohne erneutes Auschecken:"
echo "  curl -fsSL -o $INSTALL_DIR/scripts/read_gas_level.py \\"
echo "    https://raw.githubusercontent.com/cologneone/dbus-rotarex-dime/main/scripts/read_gas_level.py"
echo
echo "Voraussetzung: node-red-contrib-victron muss installiert sein (für die"
echo "virtuelle Tank-Anzeige). Ohne dieses Paket funktioniert das Auslesen"
echo "trotzdem, nur die GX-Anzeige entfällt dann."
echo
echo "Deinstallieren später mit: bash uninstall.sh"
echo
echo "Fertig."
