<img width="1295" alt="image" src="https://github.com/trollsoft7/waterkotte-resuemat-nodered/assets/51830290/323fe60a-1a9b-4855-8921-15712c234661">


# Waterkotte Resümat CD4

This repository contains a native Home Assistant integration for a
Waterkotte Resümat CD4 heat-pump controller over a USB serial adapter. It sends
the controller wake-up and memory-read requests needed to retrieve
measurements, and supports writing only the heating target temperature. It
does not change other settings or operating modes.
The original Node-RED flows (`flows.json` and `flows-4.json`) are kept as
protocol references.

## Installation

### HACS

Add this repository as a custom repository in HACS and select the **Integration**
category. Install **Waterkotte Resümat CD4**, then restart Home Assistant.

### Manual

Copy `custom_components/waterkotte_resuemat` into the Home Assistant
configuration directory's `custom_components` folder, then restart Home
Assistant.

## Configuration

In Home Assistant, open **Settings → Devices & services → Add integration** and
select **Waterkotte Resümat CD4**. Choose the USB-to-serial adapter from the
detected serial-port list. The device must be connected and available to the
Home Assistant host/container during setup.

The integration uses 9600 baud, 8 data bits, no parity, and 1 stop bit. Its
default polling interval is 120 seconds; change it in the integration options
(30–3600 seconds).

Once per serial connection, the integration sends the captured 1068-byte
controller unlock sequence: `AT `, three opaque protocol frames, and 1024
zero bytes. It does not wait for an acknowledgement; regular reads start
immediately afterward. The integration reads address ranges `0x0000–0x00F2`
and `0x00F3–0x0138`, with at least 30 seconds between read requests.

## Entities

The integration creates temperature and operating-hour sensors, a slider for
the heating target, binary sensors for heating/hot-water enablement and
operation, and a diagnostic serial communication sensor. The diagnostic
sensor reports states such as connecting, waking, sending a read or write,
waiting for a response or confirmation, receiving, parsing, idle, and error.
Its attributes show the selected serial port and the latest communication
error. Compressor, heating, and hot-water operating hours are grouped under
Home Assistant's diagnostic entities.
Heating and hot-water operating states display localized active/off labels;
their enablement sensors report active when the controller's disable flag is
clear.

The current heating target is exposed as a temperature sensor. The slider lets
you set it from 18 °C to 30 °C in 0.5 °C steps. The integration uses the
controller's `0x0113` command with a little-endian float and CRC-16/BUYPASS.
It only reports a successful write after a valid, status-zero `0x0011` ACK
with a correct CRC. Afterward it polls the controller again so the sensor
reflects the target actually stored by the heat pump.

For detailed protocol diagnostics, enable debug logging for
`custom_components.waterkotte_resuemat` in Home Assistant's logger. The log
includes communication-state changes and transmitted/received serial bytes.
If a response times out before a valid frame is decoded, the error includes
the decoder's remaining bytes and a preview of the received data.
Controller responses use the `FF 10 02` start marker (distinct from the
read-request framing). Response blocks are recognized by their Node-RED
unescaped lengths (253 bytes for the first block and 80 for the second),
including a 5-byte header and 5-byte trailer; doubled DLE bytes are unescaped
before extracting the requested memory range.

## Notes

The serial protocol and memory addresses are based on the included Node-RED
flows and the [FHEM Waterkotte Resümat CD4 driver](https://github.com/mwllgr/fhem-waterkotte-resuemat-cd4).
This integration has not been tested against every controller revision or
serial adapter. Use it at your own risk.
