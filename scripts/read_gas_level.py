#!/usr/bin/env python3
"""
read_gas_level.py

Liest Fuellstand und Batteriestand einer Alugas/Rotarex-Gasflasche mit
DIME/SRG-1-WAVE Bluetooth-Modul ueber BlueZ (D-Bus), ohne bleak oder gatttool.

Getestet auf Venus OS (Victron Cerbo GX), sollte auf jedem Linux-System mit
BlueZ und dbus_fast funktionieren.

Gibt ein einzeiliges JSON-Objekt auf stdout aus, z.B.:
    {"ok": true, "gas_raw": 99, "gas_percent": 99, "battery_percent": 86}
    oder im Fehlerfall:
        {"ok": false, "error": "connect_failed"}

        WICHTIG bei der Verarbeitung der Ausgabe: Diagnose-/Retry-Meldungen koennen
        vor dem eigentlichen JSON auf stdout landen. Nur die LETZTE Zeile ist
        garantiert valides JSON.

        Konfiguration (bitte an das eigene Geraet anpassen):
            DEVICE_PATH  - BlueZ-Objektpfad, enthaelt die MAC-Adresse der eigenen
                               Flasche (siehe README fuer den Scan-Vorgang)
                                   PIN_BYTES    - der 4-stellige PIN vom Typenschild der BLE-Box, als
                                                      ASCII-Text
                                                      """

import asyncio
import json
import sys

from dbus_fast.aio import MessageBus
from dbus_fast import BusType

# --- Konfiguration: An die eigene Flasche anpassen ---------------------
DEVICE_PATH = "/org/bluez/hci0/dev_84_BA_20_FF_B3_51"  # MAC mit "_" statt ":"
GAS_UUID = "2b67836b-183d-45da-a1bf-381b05e1bde8"
PIN_UUID = "05f5d47f-183d-45da-a1bf-381b05e1bde8"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
PIN_BYTES = list(b"5907")
# -------------------------------------------------------------------------


async def get_device(bus, max_tries=6):
      adapter_introspection = await bus.introspect("org.bluez", "/org/bluez/hci0")
      adapter_obj = bus.get_proxy_object(
          "org.bluez", "/org/bluez/hci0", adapter_introspection
      )
      adapter = adapter_obj.get_interface("org.bluez.Adapter1")

    for attempt in range(max_tries):
              try:
                            introspection = await bus.introspect("org.bluez", DEVICE_PATH)
                            dev_obj = bus.get_proxy_object("org.bluez", DEVICE_PATH, introspection)
                            device = dev_obj.get_interface("org.bluez.Device1")
                            props_dev = dev_obj.get_interface("org.freedesktop.DBus.Properties")
                            return adapter, device, props_dev
except Exception:
            pass

        try:
                      await adapter.call_start_discovery()
except Exception:
              pass
          await asyncio.sleep(5)
        try:
                      await adapter.call_stop_discovery()
except Exception:
              pass
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
      try:
                bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

          adapter, device, props_dev = await get_device(bus)
        if device is None:
                      result["error"] = "device_not_in_cache"
                      print(json.dumps(result))
                      return

        if not await connect_with_retry(device, props_dev):
                      result["error"] = "connect_failed"
                      print(json.dumps(result))
                      return

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
            print(json.dumps(result))
            return

        root_introspection = await bus.introspect("org.bluez", "/")
        root_obj = bus.get_proxy_object("org.bluez", "/", root_introspection)
        object_manager = root_obj.get_interface(
                      "org.freedesktop.DBus.ObjectManager"
        )
        objects = await object_manager.call_get_managed_objects()

        pin_path = find_characteristic(objects, PIN_UUID)
        gas_path = find_characteristic(objects, GAS_UUID)
        batt_path = find_characteristic(objects, BATTERY_UUID)

        if pin_path:
                      pin_introspection = await bus.introspect("org.bluez", pin_path)
            pin_obj = bus.get_proxy_object("org.bluez", pin_path, pin_introspection)
            pin_iface = pin_obj.get_interface("org.bluez.GattCharacteristic1")
            await pin_iface.call_write_value(bytearray(PIN_BYTES), {})
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
        print(json.dumps(result))

except Exception as exc:
        result["error"] = str(exc)
        print(json.dumps(result))


if __name__ == "__main__":
      asyncio.run(main())
    sys.exit(0)
