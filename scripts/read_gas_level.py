#!/usr/bin/env python3
"""
read_gas_level.py

Liest Füllstand und Batteriestand einer Alugas/Rotarex-Gasflasche mit
DIME/SRG-1-WAVE Bluetooth-Modul über BlueZ (D-Bus), ohne bleak oder gatttool.

Getestet auf Venus OS (Victron Cerbo GX), sollte auf jedem Linux-System mit
BlueZ und dbus_fast funktionieren.

Version: 1.1.0
Historie:
  1.0.0 — Erstveröffentlichung
  1.1.0 — MAC und PIN kommen aus Umgebungsvariablen statt fest aus dem Code;
          optionale CSV-Historie; klare Fehlermeldung bei fehlender
          Konfiguration

Gibt ein einzeiliges JSON-Objekt auf stdout aus, z.B.:
    {"ok": true, "gas_raw": 99, "gas_percent": 99, "battery_percent": 86}
oder im Fehlerfall:
    {"ok": false, "error": "connect_failed"}

WICHTIG bei der Verarbeitung der Ausgabe: Diagnose-/Retry-Meldungen können
vor dem eigentlichen JSON auf stdout landen. Nur die LETZTE Zeile ist
garantiert valides JSON.

Konfiguration über Umgebungsvariablen:
    ROTAREX_MAC      MAC-Adresse der eigenen Flasche, z.B. AA:BB:CC:DD:EE:FF
                     (steht auf dem Typenschild der BLE-Box)
    ROTAREX_PIN      PIN vom selben Typenschild, z.B. 1234
    ROTAREX_ADAPTER  Bluetooth-Adapter, Standard: hci0
    ROTAREX_HISTORY  Optional: Pfad zu einer CSV-Datei. Ist er gesetzt,
                     wird jeder Abruf dort als Zeile angehängt.

Aufruf zum Beispiel:
    ROTAREX_MAC=AA:BB:CC:DD:EE:FF ROTAREX_PIN=1234 python3 read_gas_level.py
"""

import asyncio
import json
import os
import sys
import time

from dbus_fast.aio import MessageBus
from dbus_fast import BusType

# --- Konfiguration -----------------------------------------------------
MAC = os.environ.get("ROTAREX_MAC", "").strip().upper()
PIN = os.environ.get("ROTAREX_PIN", "").strip()
ADAPTER = os.environ.get("ROTAREX_ADAPTER", "hci0").strip()
HISTORY_FILE = os.environ.get("ROTAREX_HISTORY", "").strip()

ADAPTER_PATH = f"/org/bluez/{ADAPTER}"
DEVICE_PATH = f"{ADAPTER_PATH}/dev_" + MAC.replace(":", "_")

# Diese UUIDs sind bei allen Geräten dieser Modellreihe gleich.
GAS_UUID = "2b67836b-183d-45da-a1bf-381b05e1bde8"
PIN_UUID = "05f5d47f-183d-45da-a1bf-381b05e1bde8"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"  # Standard BLE Battery Level
# -----------------------------------------------------------------------


def ausgeben(result):
    """JSON auf stdout, optional zusätzlich eine Zeile in die Historie."""
    print(json.dumps(result))
    if not HISTORY_FILE:
        return
    try:
        neu = not os.path.exists(HISTORY_FILE)
        ordner = os.path.dirname(HISTORY_FILE)
        if ordner:
            os.makedirs(ordner, exist_ok=True)
        with open(HISTORY_FILE, "a") as datei:
            if neu:
                datei.write("zeitstempel,gas_raw,gas_percent,battery_percent,fehler\n")
            datei.write(
                "%s,%s,%s,%s,%s\n"
                % (
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    result.get("gas_raw", ""),
                    result.get("gas_percent", ""),
                    result.get("battery_percent", ""),
                    result.get("error", ""),
                )
            )
    except Exception:
        pass  # Historie ist Beiwerk, sie darf den Abruf nie scheitern lassen


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

    if not MAC or not PIN:
        result["error"] = "not_configured"
        result["hinweis"] = (
            "ROTAREX_MAC und ROTAREX_PIN setzen — beides steht auf dem "
            "Typenschild der BLE-Box. Siehe README."
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

        # Der zentrale Trick: PIN als ASCII-Text auf die
        # "versteckte" Characteristic schreiben, BEVOR der Gaslevel
        # gelesen wird. Ohne diesen Schritt liefert der Read auf
        # GAS_UUID immer "ATT error: 0x80".
        if pin_path:
            pin_introspection = await bus.introspect("org.bluez", pin_path)
            pin_obj = bus.get_proxy_object("org.bluez", pin_path, pin_introspection)
            pin_iface = pin_obj.get_interface("org.bluez.GattCharacteristic1")
            await pin_iface.call_write_value(bytearray(PIN.encode("ascii")), {})
            await asyncio.sleep(0.4)

        gas_raw = await read_byte(bus, gas_path) if gas_path else None
        battery_raw = await read_byte(bus, batt_path) if batt_path else None

        try:
            await device.call_disconnect()
        except Exception:
            pass

        result["ok"] = True
        result["gas_raw"] = gas_raw
        result["gas_percent"] = min(gas_raw, 100) if gas_raw is not None else None
        result["battery_percent"] = battery_raw
        ausgeben(result)

    except Exception as exc:  # noqa: BLE001 - bewusst breit, Ergebnis geht immer raus
        result["error"] = str(exc)
        ausgeben(result)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
