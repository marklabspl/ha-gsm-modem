from __future__ import annotations

DOMAIN = "gsm_modem"
DEFAULT_NAME = "GSM Modem"
DEFAULT_PORT = "/dev/ttyACM1"
DEFAULT_BAUDRATE = 115200
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_COMMAND_TIMEOUT = 2.0
DEFAULT_SMS_TIMEOUT = 35.0
DEFAULT_DELETE_POLICY = "unauthorized"
DEFAULT_PURGE_INBOX_AFTER_PROCESSING = True
DEFAULT_TEST_SMS_MESSAGE = "Test from Home Assistant"
DEFAULT_DEFAULT_COUNTRY_CODE = "48"
DEFAULT_BALANCE_USSD_CODE = "*101#"
DEFAULT_STATUS_COMMAND = "STATUS"
DEFAULT_BALANCE_COMMAND = "BALANCE"
DEFAULT_HELP_COMMAND = "HELP"
DEFAULT_CUSTOM_COMMANDS = "GATE, GARAGE, ALARM"
DEFAULT_CUSTOM_COMMAND_REPLY_TEMPLATE = "Command {{ command }} executed."
DEFAULT_STATUS_REPLY_TEMPLATE = (
    "Health: {{ health }}\n"
    "Network: {{ registration }}\n"
    "Operator: {{ operator }}\n"
    "Signal: {{ signal_percent }}%\n"
    "SIM: {{ sim_state }}"
)
DEFAULT_BALANCE_REPLY_TEMPLATE = "Balance: {{ ussd_response }}"
DEFAULT_HELP_REPLY_TEMPLATE = "Commands: {{ commands | join(', ') }}"

CONF_PORT = "port"
CONF_BAUDRATE = "baudrate"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ALLOWED_NUMBERS = "allowed_numbers"
CONF_DELETE_POLICY = "delete_policy"
CONF_PURGE_INBOX_AFTER_PROCESSING = "purge_inbox_after_processing"
CONF_COMMAND_TIMEOUT = "command_timeout"
CONF_SMS_TIMEOUT = "sms_timeout"
CONF_TEST_SMS_NUMBER = "test_sms_number"
CONF_TEST_SMS_MESSAGE = "test_sms_message"
CONF_DEFAULT_COUNTRY_CODE = "default_country_code"
CONF_BALANCE_USSD_CODE = "balance_ussd_code"
CONF_ENABLE_SMS_COMMANDS = "enable_sms_commands"
CONF_REPLY_TO_SMS_COMMANDS = "reply_to_sms_commands"
CONF_STATUS_COMMAND = "status_command"
CONF_BALANCE_COMMAND = "balance_command"
CONF_HELP_COMMAND = "help_command"
CONF_CUSTOM_COMMANDS = "custom_commands"
CONF_CUSTOM_COMMAND_REPLY_TEMPLATE = "custom_command_reply_template"
CONF_CUSTOM_COMMAND_REPLY_TEMPLATES = "custom_command_reply_templates"
CONF_STATUS_REPLY_TEMPLATE = "status_reply_template"
CONF_BALANCE_REPLY_TEMPLATE = "balance_reply_template"
CONF_HELP_REPLY_TEMPLATE = "help_reply_template"
CONF_NOTIFY_UNAUTHORIZED_SMS = "notify_unauthorized_sms"

CONFIG_ENTRY_OPTION_KEYS = (
    CONF_SCAN_INTERVAL,
    CONF_COMMAND_TIMEOUT,
    CONF_DEFAULT_COUNTRY_CODE,
    CONF_SMS_TIMEOUT,
    CONF_ALLOWED_NUMBERS,
    CONF_DELETE_POLICY,
    CONF_TEST_SMS_NUMBER,
    CONF_TEST_SMS_MESSAGE,
    CONF_BALANCE_USSD_CODE,
    CONF_ENABLE_SMS_COMMANDS,
    CONF_REPLY_TO_SMS_COMMANDS,
    CONF_NOTIFY_UNAUTHORIZED_SMS,
    CONF_PURGE_INBOX_AFTER_PROCESSING,
    CONF_STATUS_COMMAND,
    CONF_BALANCE_COMMAND,
    CONF_HELP_COMMAND,
    CONF_CUSTOM_COMMANDS,
    CONF_CUSTOM_COMMAND_REPLY_TEMPLATE,
    CONF_CUSTOM_COMMAND_REPLY_TEMPLATES,
    CONF_STATUS_REPLY_TEMPLATE,
    CONF_BALANCE_REPLY_TEMPLATE,
    CONF_HELP_REPLY_TEMPLATE,
)

CONF_DELETE_UNAUTHORIZED = "delete_unauthorized"
CONF_DELETE_AUTHORIZED = "delete_authorized"

DELETE_POLICY_NEVER = "never"
DELETE_POLICY_AUTHORIZED = "authorized"
DELETE_POLICY_UNAUTHORIZED = "unauthorized"
DELETE_POLICY_ALL = "all"
DELETE_POLICIES = [
    DELETE_POLICY_NEVER,
    DELETE_POLICY_AUTHORIZED,
    DELETE_POLICY_UNAUTHORIZED,
    DELETE_POLICY_ALL,
]

SCAN_INTERVALS = [5, 10, 15, 30, 60, 120, 300]
BAUDRATES = [9600, 19200, 38400, 57600, 115200]

SERVICE_SEND_SMS = "send_sms"
SERVICE_SEND_TEST_SMS = "send_test_sms"
SERVICE_READ_SMS = "read_sms"
SERVICE_DELETE_SMS = "delete_sms"
SERVICE_REPLY_SMS = "reply_sms"
SERVICE_DELETE_ALL_SMS = "delete_all_sms"
SERVICE_RUN_DIAGNOSTICS = "run_diagnostics"
SERVICE_RECONNECT = "reconnect"
SERVICE_SEND_USSD = "send_ussd"
SERVICE_CHECK_BALANCE = "check_balance"
SERVICE_ENTER_PIN = "enter_pin"
SERVICE_PREVIEW_REPLY = "preview_reply_templates"
SERVICE_CONFIG_ENTRY_ID = "config_entry_id"
EVENT_DIAGNOSTICS = "gsm_modem_diagnostics"
EVENT_TEST_SMS_SENT = "gsm_modem_test_sms_sent"
EVENT_SMS_RECEIVED = "gsm_modem_sms_received"
EVENT_SMS_LIST = "gsm_modem_sms_list"
EVENT_WATCHDOG_RECONNECT = "gsm_modem_watchdog_reconnect"
EVENT_USSD_RESPONSE = "gsm_modem_ussd_response"
EVENT_SMS_COMMAND = "gsm_modem_sms_command"
EVENT_SMS_CUSTOM_COMMAND_PREFIX = "gsm_modem_command_"
EVENT_TEMPLATE_PREVIEW = "gsm_modem_template_preview"

SMS_BOX_BY_SELECTOR: dict[str, str] = {
    "all": "ALL",
    "rec_unread": "REC UNREAD",
    "rec_read": "REC READ",
}
DEFAULT_SMS_BOX_SELECTOR = "all"
VALID_SMS_BOXES = frozenset(SMS_BOX_BY_SELECTOR.values())


def normalize_sms_box(value: str | None) -> str:
    """Map UI selector values to modem AT+CMGL mailbox names."""
    if value is None or str(value).strip() == "":
        return SMS_BOX_BY_SELECTOR[DEFAULT_SMS_BOX_SELECTOR]
    key = str(value).strip()
    if key in SMS_BOX_BY_SELECTOR:
        return SMS_BOX_BY_SELECTOR[key]
    upper = key.upper()
    if upper in VALID_SMS_BOXES:
        return upper
    return SMS_BOX_BY_SELECTOR[DEFAULT_SMS_BOX_SELECTOR]
