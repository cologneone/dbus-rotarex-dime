#!/bin/bash
# uninstall.sh - dbus-rotarex-dime
#
# Entfernt die Installation wieder vom Venus-OS-Gerät. Der Node-RED-Flow
# und der virtuelle Tank-Service müssen von Hand entfernt werden, das kann
# ein Script nicht zuverlässig übernehmen.
#
# Version: 1.0.0
#
# Nutzung (auf dem Cerbo/Venus-OS-Gerät per SSH):
#   bash uninstall.sh

set -e

INSTALL_DIR="/data/dbus-rotarex-dime"

echo "== dbus-rotarex-dime deinstallieren =="
echo

if [ -d "$INSTALL_DIR" ]; then
  echo "Entferne $INSTALL_DIR ..."
  rm -rf "$INSTALL_DIR"
  echo "Erledigt."
else
  echo "Nichts zu tun — $INSTALL_DIR existiert nicht."
fi

echo
echo "Bitte noch von Hand erledigen:"
echo "  1. Node-RED öffnen und den importierten Flow 'Rotarex Gasflasche' löschen,"
echo "     danach Deploy klicken."
echo "  2. Den virtuellen Tank-Service entfernen: im Flow den victron-virtual-Node"
echo "     löschen und erneut deployen. Danach verschwindet der Tank aus der"
echo "     GX-Oberfläche und aus VRM."
echo "  3. Falls eine Historien-CSV angelegt wurde (ROTAREX_HISTORY), diese bei"
echo "     Bedarf sichern oder löschen."
echo
echo "Fertig."
