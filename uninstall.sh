#!/bin/bash
# uninstall.sh - dbus-rotarex-dime
#
# Entfernt die Installation wieder vom Venus-OS-Gerät. Der Node-RED-Flow
# und der virtuelle Tank-Service müssen von Hand entfernt werden, das kann
# ein Script nicht zuverlässig übernehmen.
#
# Version: 1.1.0
# Historie:
#   1.0.0 — Erstveröffentlichung
#   1.1.0 — Gleicher Standardpfad wie install.sh; die Historie bleibt
#           stehen, sofern sie nicht ausdrücklich mit entfernt wird
#
# Nutzung (auf dem Cerbo/Venus-OS-Gerät per SSH):
#   bash uninstall.sh
#
# Historie gleich mit löschen:
#   MIT_HISTORIE=ja bash uninstall.sh

set -e

INSTALL_DIR="${INSTALL_DIR:-/data/home/nodered/.node-red/dbus-rotarex-dime}"

echo "== dbus-rotarex-dime deinstallieren =="
echo

if [ -d "$INSTALL_DIR/scripts" ]; then
  echo "Entferne $INSTALL_DIR/scripts ..."
  rm -rf "$INSTALL_DIR/scripts"
else
  echo "Nichts zu tun — $INSTALL_DIR/scripts existiert nicht."
fi

if [ -f "$INSTALL_DIR/history.csv" ]; then
  if [ "$MIT_HISTORIE" = "ja" ]; then
    echo "Entferne $INSTALL_DIR/history.csv ..."
    rm -f "$INSTALL_DIR/history.csv"
  else
    echo
    echo "Die Messhistorie bleibt absichtlich liegen:"
    echo "  $INSTALL_DIR/history.csv"
    echo "Sie ist die einzige Datei hier, die sich nicht wiederherstellen"
    echo "lässt. Wirklich weg soll sie mit: MIT_HISTORIE=ja bash uninstall.sh"
  fi
fi

# Leeren Ordner aufräumen, sofern nichts mehr drin ist
rmdir "$INSTALL_DIR" 2>/dev/null || true

echo
echo "Bitte noch von Hand erledigen:"
echo "  1. Node-RED öffnen und den importierten Flow 'Rotarex Gasflasche' löschen,"
echo "     danach Deploy klicken."
echo "  2. Den virtuellen Tank-Service entfernen: im Flow den victron-virtual-Node"
echo "     löschen und erneut deployen. Danach verschwindet der Tank aus der"
echo "     GX-Oberfläche und aus VRM."
echo
echo "Fertig."
