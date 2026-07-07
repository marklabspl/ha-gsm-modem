# GSM Modem

Home Assistant custom integration for USB GSM modems with AT commands.

Send and receive SMS, run USSD codes, read modem state, handle SMS commands from trusted numbers, and trigger automations.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marklabspl&repository=ha-gsm-modem&category=integration)

**Website:** [marklabs.pl](https://marklabs.pl)

Use an old USB modem as a backup SMS channel when mobile data or push notifications are unavailable. Not a full replacement for push apps.

> **Status:** experimental. Tested on **ZTE MF192**. Other modems may work with limits.

---

## Table of contents

1. [Installation](#1-installation)
2. [First-time setup](#2-first-time-setup)
3. [Integration options](#3-integration-options)
4. [Entities](#4-entities)
5. [Device buttons](#5-device-buttons)
6. [Services](#6-services)
7. [Events](#7-events)
8. [SMS commands](#8-sms-commands)
9. [SMS reply templates](#9-sms-reply-templates)
10. [How to send SMS](#10-how-to-send-sms)
11. [How to receive SMS and react](#11-how-to-receive-sms-and-react)
12. [How to return sensor state in an SMS reply](#12-how-to-return-sensor-state-in-an-sms-reply)
13. [USSD and balance](#13-ussd-and-balance)
14. [Automation examples](#14-automation-examples)
15. [Blueprints](#15-blueprints)
16. [Full SMS memory prevention](#16-full-sms-memory-prevention)
17. [Troubleshooting](#17-troubleshooting)
18. [Modem compatibility](#18-modem-compatibility)
19. [Reporting issues](#19-reporting-issues)

---

## 1. Installation

### HACS

1. Click the HACS button at the top of this README **or** add the repository manually:
   - URL: `https://github.com/marklabspl/ha-gsm-modem`
   - Category: **Integration**
2. In HACS, search for **GSM Modem** and install.
3. **Restart Home Assistant.**
4. **Settings → Devices & services → Add integration → GSM Modem**.

### Manual

Copy `custom_components/gsm_modem` to `config/custom_components/` and restart HA.

---

## 2. First-time setup

### Step 1: Hardware

- USB modem on the HA host (or passed through to a VM/Proxmox).
- Active SIM (PIN disabled, or enter PIN with the `enter_pin` service).

### Step 2: Add the integration

1. Select the **modem port** (only responding ports are listed).
2. Keep **baudrate: 115200** unless your modem docs say otherwise.
3. Suggested starting values:

| Option | Value |
| --- | --- |
| Refresh interval | 30 s |
| Modem response timeout | 2.0-3.0 s |
| SMS send timeout | 35-60 s |
| Delete received SMS | `unauthorized` (or `never` while testing) |
| Clear entire inbox after processing | **Enabled** |

4. **Trusted phone numbers** in international format:
   ```
   +48501234567, +48333444555
   ```
5. **Default country code:** `48` (without `+`) for local 9-digit numbers.
6. Enable **SMS commands** and **Send SMS replies**.
7. Set **test SMS number** (`+48...`) and **test SMS message**.
8. Submit.

### Step 3: Verify

On the modem device page:

1. **Refresh modem status** (signal, operator, SIM).
2. **Run connection test** (AT diagnostics).
3. **Send test SMS**.
4. Send SMS from a trusted number to the modem SIM and check `gsm_modem_sms_received`.

### Step 4: Further configuration

**Settings → Devices → GSM Modem → Configure** to change commands, reply templates, and trusted numbers.

---

## 3. Integration options

| Option | Description |
| --- | --- |
| **Refresh interval** | Poll interval for status and new SMS. |
| **Modem response timeout** | AT timeout (USSD, diagnostics). Try 3-4 s on slow modems. |
| **Default country code** | E.g. `48` converts `501234567` to `+48501234567`. |
| **SMS send timeout** | SMS send timeout. Use at least ~35 s on weak signal. |
| **Trusted phone numbers** | Only these numbers can send **SMS commands**. Format: `+48XXXXXXXXX`. |
| **Delete received SMS** | `never` / `authorized` / `unauthorized` / `all`. |
| **Test SMS number** | Target for **Send test SMS**. Format `+48...`. |
| **Test SMS message** | Text for the test button. |
| **Balance check code** | USSD code, e.g. `*101#` (carrier-specific). |
| **Enable SMS commands** | Off: SMS events only, no STATUS/BALANCE/HELP handling. |
| **Send SMS replies** | Auto-reply after a recognized command. |
| **Notify about unknown SMS** | HA notification for SMS from non-trusted numbers. |
| **Clear entire inbox after processing** | Deletes all SMS from the modem each poll (prevents full memory). |
| **Status command word** | Default `STATUS` (exact SMS body). |
| **Balance command word** | Default `BALANCE`. |
| **Help command word** | Default `HELP`. |
| **Custom SMS commands** | E.g. `GATE, GARAGE, ALARM`. Each fires `gsm_modem_command_<command>`. |
| **Reply template for custom commands** | Default Jinja2 template for custom commands. |
| **Per-command reply templates** | Optional: `COMMAND \| body`, one line per command. |
| **Reply template for STATUS** | SMS body after STATUS. |
| **Reply template for BALANCE** | SMS body after BALANCE. |
| **Reply template for HELP** | SMS body after HELP. |

**Only when adding the integration:**

| Option | Description |
| --- | --- |
| **Modem port** | AT serial port, e.g. `/dev/ttyACM1`. |
| **Connection speed** | Usually `115200`. |

---

## 4. Entities

All entities are on one device (GSM Modem).

### Sensors

| Entity | Shows | Notes |
| --- | --- | --- |
| Signal strength | 0-100 % | Link quality |
| Modem health | `excellent`, `weak_signal`, `problem`, `sim_not_ready`, `not_registered` | Automations |
| Network operator | Operator name | |
| SIM card | `READY`, `SIM PIN`, etc. | |
| Network registration | Registration text | |
| Unread messages | Count | |
| Messages stored on modem | Count + **`messages` attribute** (last 20 SMS as JSON) | Inbox in HA |
| Connection test | `pass` / `fail` / `unknown` + `report` attribute | After diagnostics |
| Reconnect count | Watchdog reconnects | |
| Last error | Last error text | |
| Last SMS sender | Number | |
| Last SMS message | Text | |
| Last recognized command | E.g. `STATUS`, `GATE` | |
| Command handled | Yes/No | |
| Handled command type | `status`, `balance`, `help`, `custom` | |
| Reply SMS sent | Yes/No | |
| Last operator response | USSD text | |
| Sent SMS count | Counter | |
| Failed SMS count | Counter | |
| IMEI / Manufacturer / Model | Modem info | |

### Binary sensors

| Entity | On when |
| --- | --- |
| Modem problem | `health == problem` |
| SIM ready | SIM state is `READY` |
| Network registered | Registered on cellular network |

### Notify

| Entity | Action |
| --- | --- |
| **Send SMS** | Send SMS from automations (`notify.xxx`). Set `data.number`. |

---

## 5. Device buttons

| Button | Action |
| --- | --- |
| **Send test SMS** | Test message to test number (or first trusted) |
| **Check balance** | Balance USSD + `gsm_modem_ussd_response` event |
| **Clear all SMS from modem** | Deletes inbox (`ALL`) |
| **Fetch unread SMS** | `REC UNREAD` + `gsm_modem_sms_list` event |
| **Fetch all SMS** | `ALL` + inbox attribute update |
| **Refresh modem status** | Immediate status refresh |
| **Run connection test** | AT diagnostics + `gsm_modem_diagnostics` event |
| **Reconnect modem** | Reopen serial port |

---

## 6. Services

All services use the `gsm_modem.` prefix. With multiple modems, pass `config_entry_id` or `device_id`.

### `gsm_modem.send_sms`

```yaml
action: gsm_modem.send_sms
data:
  number: "+48501234567"
  message: "Alarm: {{ states('binary_sensor.leak') }}"
```

### `gsm_modem.send_test_sms`

Sends test SMS from integration options.

```yaml
action: gsm_modem.send_test_sms
```

### `gsm_modem.read_sms`

Reads SMS and fires `gsm_modem_sms_list`.

```yaml
action: gsm_modem.read_sms
data:
  box: "REC UNREAD"   # ALL | REC UNREAD | REC READ
```

### `gsm_modem.reply_sms`

Reply by storage **index** (from event or inbox attribute).

```yaml
action: gsm_modem.reply_sms
data:
  index: 3
  message: "Received at {{ now().strftime('%H:%M') }}"
```

### `gsm_modem.delete_sms`

```yaml
action: gsm_modem.delete_sms
data:
  index: 3
```

### `gsm_modem.delete_all_sms`

```yaml
action: gsm_modem.delete_all_sms
data:
  box: ALL
```

### `gsm_modem.send_ussd`

Fires `gsm_modem_ussd_response`.

```yaml
action: gsm_modem.send_ussd
data:
  code: "*101#"
```

### `gsm_modem.check_balance`

Sends balance USSD from options. Fires `gsm_modem_ussd_response`.

```yaml
action: gsm_modem.check_balance
```

### `gsm_modem.run_diagnostics`

Fires `gsm_modem_diagnostics`.

```yaml
action: gsm_modem.run_diagnostics
```

### `gsm_modem.reconnect`

```yaml
action: gsm_modem.reconnect
```

### `gsm_modem.enter_pin`

```yaml
action: gsm_modem.enter_pin
data:
  pin: "1234"
```

### `gsm_modem.preview_reply_templates`

Renders templates without sending SMS. Event `gsm_modem_template_preview`:

- `status_preview`, `balance_preview`, `help_preview`
- `custom_preview`, `custom_previews` (dict per command)

```yaml
action: gsm_modem.preview_reply_templates
```

---

## 7. Events

| Event | When | Data |
| --- | --- | --- |
| `gsm_modem_sms_received` | New SMS | `sender`, `message`, `index`, `authorized` |
| `gsm_modem_sms_command` | Recognized command | `command`, `sender`, `handled`, `action` |
| `gsm_modem_command_<command>` | Specific command | same as above |
| `gsm_modem_ussd_response` | USSD response | `code`, `response` |
| `gsm_modem_diagnostics` | After diagnostics | `checks`, `ok`, `report` |
| `gsm_modem_sms_list` | After `read_sms` / fetch button | `messages` |
| `gsm_modem_test_sms_sent` | After test SMS | `number`, `message` |
| `gsm_modem_watchdog_reconnect` | After auto reconnect | `reason`, `count` |
| `gsm_modem_template_preview` | After template preview | `status_preview`, `balance_preview`, … |

New SMS appear on the next `scan_interval` poll, not instantly.

---

## 8. SMS commands

### Flow

1. Trusted number sends one word (e.g. `STATUS`).
2. Integration receives it on the next poll.
3. Checks trusted list.
4. Matches body (uppercase, exact).
5. Runs action (status / USSD / help / custom event).
6. Optional SMS reply (Jinja2).
7. Fires automation events.

### Built-in commands

| Command | Action | Reply |
| --- | --- | --- |
| `STATUS` | Modem status | STATUS template |
| `BALANCE` | Balance USSD | BALANCE template |
| `HELP` | Command list | HELP template |

### Custom commands

**Custom SMS commands** in options, e.g. `GATE, GARAGE, ALARM`.

Each command:

- Fires `gsm_modem_command_gate` (lowercase, underscores).
- Can use shared or per-command reply template.
- Does not run HA actions alone; use automations on the event.

### Requirements

- Sender on **trusted numbers**.
- **Enable SMS commands** on.
- **Send SMS replies** on for auto-reply.
- Body is exactly one word (`STATUS`, not `status please`).
- Empty trusted list blocks everyone.

---

## 9. SMS reply templates

Five template fields in options. Templates use **Jinja2**: `states()`, `state_attr()`, `is_state()`, `{% if %}`.

| Field | Used when |
| --- | --- |
| Reply template for STATUS | After `STATUS` |
| Reply template for BALANCE | After `BALANCE` |
| Reply template for HELP | After `HELP` |
| Reply template for custom commands | Default for GATE/BRAMA/… |
| Per-command reply templates | Override per command |

### Variables

**STATUS, HELP, custom commands:** `health`, `registration`, `operator`, `signal_percent`, `sim_state`, `status`

**BALANCE:** `ussd_code`, `ussd_response`

**HELP:** `commands`, `status_command`, `balance_command`, `help_command`

**Custom commands:** `command` (e.g. `GATE`)

### Example: STATUS with HA sensors

```jinja
Modem: {{ health }}
Signal: {{ signal_percent }}%

Home:
- Temperature: {{ states('sensor.living_room_temperature') }} {{ state_attr('sensor.living_room_temperature', 'unit_of_measurement') }}
- Alarm: {{ states('alarm_control_panel.home') }}
```

Entity IDs: **Settings → Devices & services → Entities**.

### Example: per-command templates

**Per-command reply templates:**

```text
GATE | Gate: {{ states('cover.gate') }}
GARAGE | Garage: {{ states('cover.garage') }}
ALARM | Alarm: {{ states('alarm_control_panel.home') }}
```

Format: `COMMAND | Jinja2 body`. Lines starting with `#` are comments.

### Example: one template with conditions

```jinja
{% if command == 'GATE' %}
Gate: {{ states('cover.gate') }}
{% else %}
OK: {{ command }}
{% endif %}
```

### Preview

Developer tools → `gsm_modem.preview_reply_templates` → event `gsm_modem_template_preview`.

### SMS length

Long replies split into multiple segments. Keep text short when possible.

---

## 10. How to send SMS

### Service

```yaml
action: gsm_modem.send_sms
data:
  number: "+48501234567"
  message: "ALARM at home!"
```

### Notify entity

```yaml
action: notify.your_modem_send_sms
data:
  message: "Gate opened"
  data:
    number: "+48501234567"
```

### Test button

Device page → **Send test SMS**.

### Non-GSM characters

**UCS2** is supported (Polish and other extended characters).

---

## 11. How to receive SMS and react

### Polling

Inbox is checked every `scan_interval`. New SMS → event:

```yaml
trigger:
  - platform: event
    event_type: gsm_modem_sms_received
action:
  - action: logbook.log
    data:
      message: "SMS from {{ trigger.event.data.sender }}: {{ trigger.event.data.message }}"
```

### Command → action (e.g. gate)

```yaml
trigger:
  - platform: event
    event_type: gsm_modem_command_gate
condition:
  - condition: template
    value_template: "{{ trigger.event.data.authorized }}"
action:
  - action: cover.open_cover
    target:
      entity_id: cover.gate
  - action: gsm_modem.send_sms
    data:
      number: "{{ trigger.event.data.sender }}"
      message: "Gate opened"
```

### Manual read

**Fetch all SMS** or `read_sms` → `messages` on **Messages stored on modem** sensor.

---

## 12. How to return sensor state in an SMS reply

Text `STATUS` from your phone and get temperature and alarm in the reply.

1. **Settings → GSM Modem → Configure**
2. Enable SMS commands and Send SMS replies.
3. Add your number to trusted numbers: `+48...`
4. In **Reply template for STATUS**:

```jinja
Status: {{ health }}
Signal: {{ signal_percent }}%

Home:
- Temperature: {{ states('sensor.living_room_temperature') }} {{ state_attr('sensor.living_room_temperature', 'unit_of_measurement') }}
- Alarm: {{ states('alarm_control_panel.home') }}
```

5. Save. Send `STATUS` from a trusted number.
6. Test without SMS: `gsm_modem.preview_reply_templates`.

For one command only (e.g. gate), use custom command `GATE` with a per-command template.

---

## 13. USSD and balance

### One-time check

- **Check balance** button, or
- `gsm_modem.check_balance`

Result: `gsm_modem_ussd_response` and **Last operator response** sensor.

### Operator code

**Balance check code** in options (e.g. `*101#`). Carrier-specific.

### SMS BALANCE command

Trusted number sends `BALANCE` → USSD → reply from BALANCE template.

### Slow modem

Increase **Modem response timeout** to 3-4 s.

### Low-balance alert

Blueprint `cyclic_balance_low_alert.yaml` (see [Blueprints](#15-blueprints)).

---

## 14. Automation examples

### Alarm → SMS

```yaml
trigger:
  - platform: state
    entity_id: alarm_control_panel.home
    to: "triggered"
action:
  - action: gsm_modem.send_sms
    data:
      number: "+48501234567"
      message: "ALARM at home!"
```

### Water leak → SMS

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.bathroom_leak
    to: "on"
action:
  - action: gsm_modem.send_sms
    data:
      number: "+48501234567"
      message: "WATER LEAK in bathroom!"
```

### Notes

- One modem handles one AT operation at a time.
- With multiple modems, pass `config_entry_id`.
- SMS reception follows `scan_interval`.

---

## 15. Blueprints

Files in `blueprints/automation/gsm_modem/`.

**Import:** Settings → Automations & scenes → Blueprints → Import blueprint (GitHub raw URL or copy to `config/blueprints/automation/`).

| File | Description |
| --- | --- |
| `sms_command_to_action.yaml` | HA action on `gsm_modem_command_*` |
| `alarm_to_sms.yaml` | SMS on alarm state change |
| `auto_reply_incoming_sms.yaml` | Auto-reply to incoming SMS |
| `cyclic_balance_low_alert.yaml` | Scheduled balance check + alert |
| `custom_command_ack.yaml` | Action + ACK/NACK SMS to sender |

| Task | Use |
| --- | --- |
| SMS reply with status or sensors | Reply templates in options |
| Open gate, relay, etc. | `sms_command_to_action` |
| Alarm to fixed number | `alarm_to_sms` |
| Balance monitoring | `cyclic_balance_low_alert` |
| Action + SMS confirmation | `custom_command_ack` |

---

## 16. Full SMS memory prevention

Full modem memory blocks new SMS.

**Settings:**

- **Clear entire inbox after processing** enabled
- **Delete received SMS** = `unauthorized` or `all`

**Symptoms:**

- No `gsm_modem_sms_received` events
- Polling runs but no new messages

**Recovery:**

1. **Clear all SMS from modem** or `gsm_modem.delete_all_sms` (`box: ALL`)
2. **Reconnect modem**
3. Send a test SMS

---

## 17. Troubleshooting

| Problem | Fix |
| --- | --- |
| No modem in list | USB/VM passthrough, other port, baudrate 115200 |
| SIM: PIN required | `enter_pin` or disable PIN on SIM |
| Not registered | Antenna, signal, other SIM |
| USSD/balance timeout | `command_timeout` 3-4 s |
| SMS not sending | `sms_timeout`, check signal |
| Commands ignored | Trusted list, exact word, commands enabled |
| Raw keys in UI | Update integration, restart HA |
| Translation error under template | Update to latest version |
| Invalid phone number | `+48XXXXXXXXX` or 9 digits + country code `48` |

---

## 18. Modem compatibility

**Usually works:** `AT`, SMS (`AT+CMGF`, `AT+CMGS`, `AT+CMGL`), signal (`AT+CSQ`), registration (`AT+CREG`).

**Often differs:** USSD (`AT+CUSD`), response format, timeouts, SMS memory, UCS2.

Partial compatibility is common (SMS OK, USSD not).

On ZTE MF192, `/dev/ttyACM1` is usually the AT port.

---

## 19. Reporting issues

Include:

- Modem model and firmware
- Host (HA OS / Docker / VM / Proxmox)
- What works and what fails
- Diagnostics and logs (mask phone numbers)
- Baudrate, timeouts, delete policy

**Repository:** [github.com/marklabspl/ha-gsm-modem](https://github.com/marklabspl/ha-gsm-modem)  
**Website:** [marklabs.pl](https://marklabs.pl)
