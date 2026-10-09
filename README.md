<img width="1295" alt="image" src="https://github.com/trollsoft7/waterkotte-resuemat-nodered/assets/51830290/323fe60a-1a9b-4855-8921-15712c234661">


# Waterkotte Resümat CD4

This repository contains a native Home Assistant integration for reading and
controlling a Waterkotte Resümat CD4 heat-pump controller over a USB serial
adapter. The original Node-RED flows (`flows.json` and `flows-4.json`) are kept
as protocol references.

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

## Entities

The integration creates temperature and operating-hour sensors, binary sensors
for heating/hot-water disablement and operation, switches to enable or disable
heating and hot water, and number controls for the heating and hot-water
setpoints. Setpoints are exposed as numbers rather than duplicate read-only
sensors; their displayed values are read back from the controller.

## Notes

The serial protocol and memory addresses are based on the included Node-RED
flows and the [FHEM Waterkotte Resümat CD4 driver](https://github.com/mwllgr/fhem-waterkotte-resuemat-cd4).
This integration has not been tested against every controller revision or
serial adapter. Use it at your own risk, especially when writing setpoints or
changing enablement.
