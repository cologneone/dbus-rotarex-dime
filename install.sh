#!/bin/bash
# install.sh - dbus-rotarex-dime
#
# Kopiert die Skripte nach /data (uberlebt Venus-OS-Firmware-Updates,
# im Gegensatz zum restlichen Root-Filesystem) und gibt Hinweise zum
# Import des Node-RED-Flows.
#
# Nutzung (auf dem Cerbo/Venus-OS-Geraet per SSH):
#   bash install.sh

set -e

INSTALL_DIR="/data/dbus-rotarex-dime"

echo "== dbus-rotarex-dime Installer =="
echo

mkdir -p "$INSTALL_DIR/scripts"
cp -v scripts/read_gas_level.py "$INSTALL_DIR/scripts/"
chmod +x "$INSTALL_DIR/scripts/read_gas_level.py"

echo
echo "Skript installiert nach: $INSTALL_DIR/scripts/read_gas_level.py"
echo
echo "WICHTIG - vor dem ersten Start unbedingt anpassen:"
echo "  1. DEVICE_PATH in read_gas_level.py auf die MAC-Adresse DEINER Flasche setzen"
echo "     (siehe README.md, Abschnitt 'Eigene Flasche finden')"
echo "  2. PIN_BYTES auf den PIN-Code DEINER BLE-Box setzen (steht auf dem Typenschild)"
echo
echo "Node-RED-Flow importieren:"
echo "  1. Node-RED-Oberflaeche oeffnen (i.d.R. https://<Cerbo-IP>:1881)"
echo "  2. Menu -> Import -> Datei auswaehlen: flows/rotarex-gasflasche.json"
echo "  3. Im 'exec'-Node den Pfad zum Skript pruefen (Standard: $INSTALL_DIR/scripts/read_gas_level.py)"
echo "  4. Deploy klicken"
echo
echo "Voraussetzung: node-red-contrib-victron muss installiert sein (fuer die"
echo "virtuelle Tank-Anzeige). Ohne dieses Paket funktioniert das Auslesen"
echo "trotzdem, nur die GX-Anzeige entfaellt dann."
echo
echo "Fertig."
