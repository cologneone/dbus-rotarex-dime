#!/usr/bin/env python3
"""
read_gas_level.py

Liest Füllstand und Batteriestand einer Alugas/Rotarex-Gasflasche mit
DIMES-WAVE-Bluetooth-Modul (im BLE-Scan als SRG-1-WAVE) über BlueZ (D-Bus),
ohne bleak oder gatttool.

Getestet auf Venus OS (Victron Cerbo GX), sollte auf jedem Linux-System mit
BlueZ und dbus_fast funktionieren.

Version: 1.5.0
Historie:
  1.0.0 — Erstveröffentlichung
  1.1.0 — MAC und PIN kommen aus Umgebungsvariablen statt fest aus dem Code;
          optionale CSV-Historie; klare Fehlermeldung bei fehlender
          Konfiguration
  1.2.0 — Historie schreibt vier Spalten ohne Kopfzeile mit UTC-Zeitstempel
          und nur bei erfolgreichem Abruf; Schreibfehler landen als
          history_error im Ergebnis
  1.3.0 — "ok" bedeutet jetzt wirklich, dass ein Füllstand gelesen wurde:
          fehlende Characteristics und fehlgeschlagene Zugriffe haben
          eigene Fehlercodes. Verbindung wird immer getrennt, auch wenn
          unterwegs etwas schiefgeht. Konfiguration wahlweise aus einer
          Datei, damit MAC und PIN nicht im Node-RED-Flow stehen müssen.
  1.4.0 — Die Konfigurationsdatei wird relativ zum Script gesucht, damit ein
          abweichender Installationsort tatsächlich funktioniert. Keine
          Wartezeit mehr nach dem jeweils letzten Versuch — das spart im
          schlechtesten Fall rund 18 Sekunden. Fehlender Batteriestand
          erzeugt in der Historie ein leeres Feld statt "None".
  1.5.0 — Eigene Gesamt-Zeitgrenze. BlueZ kann beim Verbinden beliebig lange
          blockieren, wenn eine andere Verbindung das Modul besetzt haelt —
          ein Abruf lief so nachweislich elf Minuten. Statt sich darauf zu
          verlassen, dass Node-RED den Prozess irgendwann abschiesst, gibt
          das Script jetzt selbst rechtzeitig {"ok": false, "error":
          "timeout"} aus und versucht anschliessend, die Verbindung zu
          loesen.

Gibt ein einzeiliges JSON-Objekt auf stdout aus, z.B.:
    {"ok": true, "gas_raw": 99, "gas_percent": 99, "battery_percent": 86}
oder im Fehlerfall:
    {"ok": false, "error": "connect_failed"}

Mögliche Fehlercodes:
    not_configured                  MAC oder PIN fehlen
    device_not_in_cache             BlueZ kennt das Gerät nicht (ausser Reichweite?)
    connect_failed                  Verbindung kam nicht zustande
    services_not_resolved           verbunden, aber GATT-Baum kam nicht
    pin_characteristic_not_found    PIN-Characteristic fehlt im GATT-Baum
    gas_characteristic_not_found    Füllstand-Characteristic fehlt im GATT-Baum
    pin_write_failed                PIN liess sich nicht schreiben
    gas_read_failed                 Lesen des Füllstands scheiterte (ohne PIN: ATT 0x80)
    gas_value_empty                 Lesen ging durch, lieferte aber kein Byte
    timeout                         Gesamtzeit ueberschritten, siehe ROTAREX_TIMEOUT

Der Batteriestand ist bewusst optional: Fehlt er, ist der Abruf trotzdem
erfolgreich, und der Grund steht als battery_error dabei.

WICHTIG bei der Verarbeitung der Ausgabe: Diagnose-/Retry-Meldungen können
vor dem eigentlichen JSON auf stdout landen. Nur die LETZTE Zeile ist
garantiert valides JSON.

Konfiguration — Umgebungsvariablen haben immer Vorrang, sonst wird eine
Konfigurationsdatei mit Zeilen der Form NAME=Wert gelesen:

    ROTAREX_MAC      MAC-Adresse der eigenen Flasche, z.B. AA:BB:CC:DD:EE:FF
                     (steht auf dem Typenschild der BLE-Box)
    ROTAREX_PIN      PIN vom selben Typenschild, z.B. 1234
    ROTAREX_ADAPTER  Bluetooth-Adapter, Standard: hci0
    ROTAREX_HISTORY  Optional: Pfad zu einer CSV-Datei. Ist er gesetzt,
                     wird jeder erfolgreiche Abruf dort angehängt.
    ROTAREX_TIMEOUT  Sekunden, nach denen der Abruf aufgibt. Standard: 85 —
                     knapp unter dem 90-Sekunden-Timeout des
                     Node-RED-exec-Node, damit das Script sein Ergebnis noch
                     selbst ausgeben kann, statt abgeschossen zu werden.
    ROTAREX_CONFIG   Pfad der Konfigurationsdatei. Ohne Angabe wird sie
                     eine Ebene über diesem Script gesucht, also bei einer
                     Installation nach <ordner>/scripts/read_gas_level.py
                     unter <ordner>/config.

Aufruf zum Beispiel:
    ROTAREX_MAC=AA:BB:CC:DD:EE:FF ROTAREX_PIN=1234 python3 read_gas_level.py
oder, mit ausgefüllter Konfigurationsdatei, schlicht:
    python3 read_gas_level.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dbus_fast.aio import MessageBus
from dbus_fast import BusType

# --- Konfiguration -----------------------------------------------------

# Neben dem Installationsordner, nicht auf einem festen Pfad: Das Script
# liegt in <ordner>/scripts/, die Konfiguration gehört nach <ordner>/config.
# Nur so funktioniert ein abweichendes INSTALL_DIR wirklich.
STANDARD_CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def _konfigurationsdatei_lesen(pfad):
    """
    Liest Zeilen der Form NAME=Wert. Leerzeilen und alles ab '#' wird
    ignoriert, Anführungszeichen um den Wert werden entfernt. Fehlt die
    Datei, ist das kein Fehler — dann zählen eben nur die Umgebungsvariablen.
    """
    werte = {}
    try:
        with open(pfad) as datei:
            for zeile in datei:
                zeile = zeile.split("#", 1)[0].strip()
                if not zeile or "=" not in zeile:
                    continue
                name, _, wert = zeile.partition("=")
                werte[name.strip()] = wert.strip().strip('"').strip("'")
    except OSError:
        pass
    return werte


CONFIG_FILE = os.environ.get("ROTAREX_CONFIG", "").strip() or STANDARD_CONFIG
_aus_datei = _konfigurationsdatei_lesen(CONFIG_FILE)


def einstellung(name, standard=""):
    """Umgebungsvariable schlaegt Konfigurationsdatei schlaegt Standardwert."""
    wert = os.environ.get(name, "").strip()
    if wert:
        return wert
    return _aus_datei.get(name, standard).strip()


MAC = einstellung("ROTAREX_MAC").upper()
PIN = einstellung("ROTAREX_PIN")
ADAPTER = einstellung("ROTAREX_ADAPTER", "hci0")
HISTORY_FILE = einstellung("ROTAREX_HISTORY")

try:
    GESAMT_TIMEOUT = float(einstellung("ROTAREX_TIMEOUT", "85"))
except ValueError:
    GESAMT_TIMEOUT = 85.0

ADAPTER_PATH = f"/org/bluez/{ADAPTER}"
DEVICE_PATH = f"{ADAPTER_PATH}/dev_" + MAC.replace(":", "_")

# Diese UUIDs sind bei allen Geräten dieser Modellreihe gleich.
GAS_UUID = "2b67836b-183d-45da-a1bf-381b05e1bde8"
PIN_UUID = "05f5d47f-183d-45da-a1bf-381b05e1bde8"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"  # Standard BLE Battery Level
# -----------------------------------------------------------------------


def _feld(wert):
    """None wird in der CSV zu einem leeren Feld, nicht zur Zeichenkette None."""
    return "" if wert is None else wert


def ausgeben(result):
    """
    Schreibt das Ergebnis als eine Zeile JSON auf stdout.

    Ist ROTAREX_HISTORY gesetzt und der Abruf war erfolgreich, wird
    zusätzlich eine Zeile an die CSV angehängt — vier Spalten, ohne
    Kopfzeile, Zeitstempel in UTC nach ISO 8601:

        2026-08-18T19:41:03.512844+00:00,78,78,86

    Fehlt der Batteriestand, bleibt das vierte Feld leer.

    Bewusst nur bei Erfolg: Eine Historie, in der Fehlversuche als leere
    Werte stehen, verzerrt jede spätere Verbrauchsauswertung.
    """
    if HISTORY_FILE and result.get("ok"):
        try:
            ordner = os.path.dirname(HISTORY_FILE)
            if ordner:
                os.makedirs(ordner, exist_ok=True)
            zeitstempel = datetime.now(timezone.utc).isoformat()
            with open(HISTORY_FILE, "a") as datei:
                datei.write(
                    "%s,%s,%s,%s\n"
                    % (
                        zeitstempel,
                        _feld(result.get("gas_raw")),
                        _feld(result.get("gas_percent")),
                        _feld(result.get("battery_percent")),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            # Die Historie ist Beiwerk, sie darf den Abruf nie scheitern
            # lassen — der Fehler wandert aber sichtbar ins Ergebnis.
            result["history_error"] = str(exc)

    print(json.dumps(result))


async def get_device(bus, max_tries=6):
    """
    Stellt sicher, dass das Geraet im BlueZ-Objekt-Cache vorhanden ist,
    bevor introspiziert wird. BlueZ wirft das Geraeteobjekt raus, wenn
    laengere Zeit kein aktiver Scan/Verbindung bestand - deshalb hier
    noetigenfalls ein kurzer Discovery-Lauf VOR jedem Introspect-Versuch.
    """
    adapter_introspection = await bus.introspect("org.bluez", ADAPTER_PATH)
    adapter_obj = bus.get_proxy_object("org.bluez", ADAPTER_PATH, adapter_introspection)
    adapter = adapter_obj.get_interface("org.bluez.Adapter1")

    for attempt in range(max_tries):
        try:
            introspection = await bus.introspect("org.bluez", DEVICE_PATH)
            dev_obj = bus.get_proxy_object("org.bluez", DEVICE_PATH, introspection)
            device = dev_obj.get_interface("org.bluez.Device1")
            props_dev = dev_obj.get_interface("org.freedesktop.DBus.Properties")
            return adapter, device, props_dev
        except Exception:
            pass  # Geraet noch nicht im Cache - Discovery starten und erneut versuchen

        # Nach dem letzten Durchgang folgt kein Introspect-Versuch mehr, der
        # von einem weiteren Scan profitieren koennte. Ihn trotzdem laufen zu
        # lassen kostet nur Zeit - und die ist durch den Timeout des
        # Node-RED-exec-Node begrenzt.
        if attempt == max_tries - 1:
            break

        try:
            await adapter.call_start_discovery()
        except Exception:
            pass
        await asyncio.sleep(5)
        try:
            await adapter.call_stop_discovery()
        except Exception:
            pass
        # Kurze Pause nach Stop-Discovery, sonst droht
        # "le-connection-abort-by-local" beim naechsten Connect-Versuch
        await asyncio.sleep(2 + attempt)

    return adapter, None, None


async def connect_with_retry(device, props_dev, max_tries=4):
    for attempt in range(max_tries):
        try:
            connected = (
                await props_dev.call_get("org.bluez.Device1", "Connected")
            ).value
        except Exception:
            connected = False
        if connected:
            return True
        try:
            await device.call_connect()
            return True
        except Exception:
            if attempt == max_tries - 1:
                break  # danach wird ohnehin aufgegeben, die Pause braucht niemand
            await asyncio.sleep(3 + attempt)
    return False


def find_characteristic(objects, uuid):
    for path, ifaces in objects.items():
        if path.startswith(DEVICE_PATH) and "org.bluez.GattCharacteristic1" in ifaces:
            uuid_prop = ifaces["org.bluez.GattCharacteristic1"].get("UUID")
            if uuid_prop and uuid_prop.value.lower() == uuid:
                return path
    return None


async def read_byte(bus, path):
    introspection = await bus.introspect("org.bluez", path)
    obj = bus.get_proxy_object("org.bluez", path, introspection)
    iface = obj.get_interface("org.bluez.GattCharacteristic1")
    value = await iface.call_read_value({})
    values = list(value)
    return values[0] if values else None


async def main():
    result = {"ok": False}
    device = None

    if not MAC or not PIN:
        result["error"] = "not_configured"
        result["hinweis"] = (
            "ROTAREX_MAC und ROTAREX_PIN setzen — als Umgebungsvariablen oder "
            "in %s. Beides steht auf dem Typenschild der BLE-Box. Siehe README."
            % CONFIG_FILE
        )
        ausgeben(result)
        return

    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        adapter, device, props_dev = await get_device(bus)
        if device is None:
            result["error"] = "device_not_in_cache"
            ausgeben(result)
            return

        if not await connect_with_retry(device, props_dev):
            result["error"] = "connect_failed"
            ausgeben(result)
            return

        # Auf ServicesResolved warten, sonst sind die Characteristics
        # noch nicht im Objektbaum vorhanden
        resolved = False
        for _ in range(20):
            resolved = (
                await props_dev.call_get("org.bluez.Device1", "ServicesResolved")
            ).value
            if resolved:
                break
            await asyncio.sleep(0.5)
        if not resolved:
            result["error"] = "services_not_resolved"
            ausgeben(result)
            return

        root_introspection = await bus.introspect("org.bluez", "/")
        root_obj = bus.get_proxy_object("org.bluez", "/", root_introspection)
        object_manager = root_obj.get_interface("org.freedesktop.DBus.ObjectManager")
        objects = await object_manager.call_get_managed_objects()

        pin_path = find_characteristic(objects, PIN_UUID)
        gas_path = find_characteristic(objects, GAS_UUID)
        batt_path = find_characteristic(objects, BATTERY_UUID)

        # PIN und Füllstand sind Pflicht. Fehlt eine der beiden
        # Characteristics, stimmt etwas Grundsätzliches nicht — dann ist
        # das ein Fehler und kein Abruf mit leerem Wert.
        if pin_path is None:
            result["error"] = "pin_characteristic_not_found"
            ausgeben(result)
            return
        if gas_path is None:
            result["error"] = "gas_characteristic_not_found"
            ausgeben(result)
            return

        # Der zentrale Trick: PIN als ASCII-Text auf die
        # "versteckte" Characteristic schreiben, BEVOR der Gaslevel
        # gelesen wird. Ohne diesen Schritt liefert der Read auf
        # GAS_UUID immer "ATT error: 0x80".
        try:
            pin_introspection = await bus.introspect("org.bluez", pin_path)
            pin_obj = bus.get_proxy_object("org.bluez", pin_path, pin_introspection)
            pin_iface = pin_obj.get_interface("org.bluez.GattCharacteristic1")
            await pin_iface.call_write_value(bytearray(PIN.encode("ascii")), {})
        except Exception as exc:  # noqa: BLE001
            result["error"] = "pin_write_failed"
            result["detail"] = str(exc)
            ausgeben(result)
            return
        await asyncio.sleep(0.4)

        try:
            gas_raw = await read_byte(bus, gas_path)
        except Exception as exc:  # noqa: BLE001
            result["error"] = "gas_read_failed"
            result["detail"] = str(exc)
            ausgeben(result)
            return

        if gas_raw is None:
            result["error"] = "gas_value_empty"
            ausgeben(result)
            return

        # Der Batteriestand des Senders ist Beiwerk. Fehlt er, ist der
        # Abruf trotzdem gelungen.
        battery_raw = None
        battery_error = None
        if batt_path is None:
            battery_error = "battery_characteristic_not_found"
        else:
            try:
                battery_raw = await read_byte(bus, batt_path)
            except Exception as exc:  # noqa: BLE001
                battery_error = str(exc)

        result["ok"] = True
        result["gas_raw"] = gas_raw
        result["gas_percent"] = min(gas_raw, 100)
        result["battery_percent"] = battery_raw
        if battery_error:
            result["battery_error"] = battery_error
        ausgeben(result)

    except Exception as exc:  # noqa: BLE001 - bewusst breit, Ergebnis geht immer raus
        result["error"] = str(exc)
        ausgeben(result)

    finally:
        # Immer trennen. Bleibt die Verbindung stehen, kommt beim nächsten
        # Poll weder das Handy noch der Cerbo an die Flasche.
        if device is not None:
            try:
                await device.call_disconnect()
            except Exception:
                pass


async def notfall_trennen():
    """
    Nach einem Timeout wurde die laufende Arbeit abgebrochen, womoeglich
    mitten in einer offenen Verbindung. Da das Modul nur eine Verbindung
    gleichzeitig zulaesst, wird hier ueber eine frische Sitzung noch einmal
    ausdruecklich getrennt. Schlaegt das fehl, ist es auch nicht schlimmer
    als vorher.
    """
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    introspection = await bus.introspect("org.bluez", DEVICE_PATH)
    geraet = bus.get_proxy_object("org.bluez", DEVICE_PATH, introspection)
    await geraet.get_interface("org.bluez.Device1").call_disconnect()


async def mit_zeitgrenze():
    """
    Deckel ueber allem. Einzelne BlueZ-Aufrufe haben keine eigene Zeitgrenze:
    Haelt zum Beispiel die Hersteller-App die Verbindung, bleibt call_connect()
    einfach stehen. Ohne diesen Deckel laeuft ein Abruf von Hand beliebig
    lange weiter, und in Node-RED wird er hart abgeschossen — mit
    abgeschnittener Ausgabe, die dann als Parse-Fehler ankommt.
    """
    try:
        await asyncio.wait_for(main(), timeout=GESAMT_TIMEOUT)
    except asyncio.TimeoutError:
        try:
            await asyncio.wait_for(notfall_trennen(), timeout=5)
        except Exception:  # noqa: BLE001
            pass
        ausgeben(
            {
                "ok": False,
                "error": "timeout",
                "detail": (
                    "kein Ergebnis binnen %.0f Sekunden — meist haelt eine "
                    "andere Verbindung das Modul besetzt, etwa die "
                    "Hersteller-App auf dem Handy" % GESAMT_TIMEOUT
                ),
            }
        )


if __name__ == "__main__":
    asyncio.run(mit_zeitgrenze())
    sys.exit(0)
