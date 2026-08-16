DOMAIN = "smartrent"
PROPER_NAME = "SmartRent"
CONFIGURATION_URL = "https://control.smartrent.com/login"

CONF_PASSWORD = "password"
CONF_USERNAME = "username"
CONF_TOKEN = "token"
PLATFORMS = ["binary_sensor", "climate", "light", "lock", "sensor", "switch"]
STARTUP_MESSAGE = f"Starting setup for {DOMAIN}"

SERVICE_GET_GUEST_CODES = "get_guest_codes"
SERVICE_CREATE_GUEST_CODE = "create_guest_code"
SERVICE_UPDATE_GUEST_CODE = "update_guest_code"
SERVICE_DELETE_GUEST_CODE = "delete_guest_code"
