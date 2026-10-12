<img width="1295" alt="image" src="https://github.com/trollsoft7/waterkotte-resuemat-nodered/assets/51830290/323fe60a-1a9b-4855-8921-15712c234661">


# Waterkotte Resümat CD4

This repository contains a read-only native Home Assistant integration for a
Waterkotte Resümat CD4 heat-pump controller over a USB serial adapter. It sends
only the controller wake-up and memory-read requests needed to retrieve
measurements; it does not write settings or operating modes to the heat pump.
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

Before each poll, the integration sends the controller wake-up sequence
`AT` followed by carriage return and waits three seconds before requesting
memory data.

## Entities

The integration creates temperature and operating-hour sensors, binary sensors
for heating/hot-water disablement and operation, and a diagnostic serial
communication sensor. The diagnostic sensor reports states such as connecting,
waking, sending a read request, waiting for a response, receiving, parsing,
idle, and error. Its attributes show the selected serial port and the latest
communication error. Setpoints are available as read-only sensors.

For detailed protocol diagnostics, enable debug logging for
`custom_components.waterkotte_resuemat` in Home Assistant's logger. The log
includes communication-state changes and transmitted/received serial bytes.

## Notes

The serial protocol and memory addresses are based on the included Node-RED
flows and the [FHEM Waterkotte Resümat CD4 driver](https://github.com/mwllgr/fhem-waterkotte-resuemat-cd4).
This integration has not been tested against every controller revision or
serial adapter. Use it at your own risk.
