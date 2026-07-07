# Changelog

## 1.5.0

- Support multiple modems in services via `config_entry_id` or `device_id`.
- Configurable AT and SMS timeouts in integration options.
- Prune processed SMS indexes after inbox changes.
- Notify platform for sending SMS from automations.
- Jinja reply templates for STATUS, BALANCE and HELP commands.
- Sensors for SMS command handling state and reply errors.
- Optional persistent notification for unauthorized SMS.
- Merge multipart SMS (UDH and `(1/2)` text parts).
- UCS2 SMS encoding for Polish and other non-GSM characters.
- `gsm_modem.enter_pin` service for SIM PIN entry.
- Auto-discover AT ports during setup.
- Improve STATUS SMS replies with health line and safer template handling.
- Normalize phone numbers in `gsm_modem.send_sms`.
- Document automation flows and SMS command replies in README.

## 1.4.0

- Increase SMS send timeout for older USB modems.
- Make AT response parsing more tolerant of different line endings.
- Reconnect and retry once after a failed SMS send.
- Prevent failed automatic SMS replies from breaking the update cycle.
