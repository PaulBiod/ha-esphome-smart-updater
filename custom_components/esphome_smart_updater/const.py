DOMAIN = "esphome_smart_updater"

DEFAULT_TIMEOUT = 600
DEFAULT_DELAY_MIN = 5
DEFAULT_DELAY_MAX = 60
DEFAULT_MAX_ITEMS = 50
DEFAULT_RESTORE_RESUME_DELAY = 180
DEFAULT_REFRESH_INTERVAL = 30

CONF_TIMEOUT = "timeout"
CONF_THROTTLE = "throttle"
CONF_DELAY_MIN = "delay_min"
CONF_DELAY_MAX = "delay_max"
CONF_MAX_ITEMS = "max_items"
CONF_CPU_SENSOR = "cpu_sensor"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_LOAD_SENSOR = "load_sensor"
CONF_RESTORE_RESUME_DELAY = "restore_resume_delay"

CONF_DEVICE_SELECTION_MODE = "device_selection_mode"
CONF_SELECTED_UPDATE_ENTITIES = "selected_update_entities"
CONF_EXCLUDED_UPDATE_ENTITIES = "excluded_update_entities"

DEVICE_SELECTION_ALL = "all_devices"
DEVICE_SELECTION_SELECTED = "selected_devices"
DEVICE_SELECTION_EXCLUDE = "exclude_devices"

CAMPAIGN_SENSOR_UNIQUE_ID = "esphome_smart_updater_campaign"
PENDING_UPDATES_SENSOR_UNIQUE_ID = "esphome_smart_updater_pending_updates"
PROGRESS_SENSOR_UNIQUE_ID = "esphome_smart_updater_progress"

BINARY_SENSOR_REPORT_AVAILABLE_UNIQUE_ID = "esphome_smart_updater_report_available"
BINARY_SENSOR_THROTTLE_ENABLED_UNIQUE_ID = "esphome_smart_updater_throttle_enabled"
BINARY_SENSOR_PAUSE_REQUESTED_UNIQUE_ID = "esphome_smart_updater_pause_requested"
BINARY_SENSOR_STOP_REQUESTED_UNIQUE_ID = "esphome_smart_updater_stop_requested"
BINARY_SENSOR_LAST_DEVICE_RUNNING_UNIQUE_ID = "esphome_smart_updater_last_device_running"
BINARY_SENSOR_PAUSE_INFO_VISIBLE_UNIQUE_ID = "esphome_smart_updater_pause_info_visible"
BINARY_SENSOR_CURRENT_ERROR_VISIBLE_UNIQUE_ID = "esphome_smart_updater_current_error_visible"
BINARY_SENSOR_PREVIEW_AVAILABLE_UNIQUE_ID = "esphome_smart_updater_preview_available"
BINARY_SENSOR_CPU_METRIC_VISIBLE_UNIQUE_ID = "esphome_smart_updater_cpu_metric_visible"
BINARY_SENSOR_TEMP_METRIC_VISIBLE_UNIQUE_ID = "esphome_smart_updater_temp_metric_visible"
BINARY_SENSOR_LOAD_METRIC_VISIBLE_UNIQUE_ID = "esphome_smart_updater_load_metric_visible"

BUTTON_START_UNIQUE_ID = "esu_start"
BUTTON_PAUSE_UNIQUE_ID = "esu_pause"
BUTTON_RESUME_UNIQUE_ID = "esu_resume"
BUTTON_STOP_UNIQUE_ID = "esu_stop"

SERVICE_START_CAMPAIGN = "start_campaign"
SERVICE_PAUSE_CAMPAIGN = "pause_campaign"
SERVICE_RESUME_CAMPAIGN = "resume_campaign"
SERVICE_STOP_CAMPAIGN = "stop_campaign"
SERVICE_CLEAR_REPORT = "clear_report"

EVENT_CAMPAIGN_FINISHED = "esphome_smart_updater_campaign_finished"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_campaign"
