"""Safe, testable SmartRent guest access-code management."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, time, timedelta
import re
from typing import Any

ACTIVATION_TYPES = ("permanent", "temporary", "recurring")
WEEKDAYS = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)
_WEEKDAYS_BY_LOWER = {day.lower(): day for day in WEEKDAYS}
_RECURRING_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^\+?[0-9() .-]{7,32}$")
_MISSING = object()


class AccessManagerError(Exception):
    """Base class for deliberately sanitized access-manager errors."""


class AccessValidationError(AccessManagerError):
    """The requested operation is invalid or unsafe."""


class AccessOperationError(AccessManagerError):
    """SmartRent could not complete an access operation."""


class AccessAcceptedNotVerifiedError(AccessOperationError):
    """A mutation was accepted but could not be verified by read-back."""


class SmartRentAccessAPIAdapter:
    """Isolate the Home Assistant to smartrent-py argument mapping.

    The pending smartrent-py implementation uses the explicit
    ``temporary_*`` and ``recurring_*`` names below. If that public API changes,
    only this adapter should need to change.
    """

    def __init__(self, api: Any) -> None:
        self._api = api

    async def async_get_hubs(self) -> list[dict[str, Any]]:
        return await self._api.async_get_hubs()

    async def async_get_unit_access(self, unit_id: int) -> dict[str, Any]:
        return await self._api.async_get_unit_access(unit_id)

    async def async_create_guest(
        self, unit_id: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        return await self._api.async_create_guest_access_code(
            unit_id=unit_id,
            activation_type=values["activation_type"],
            first_name=values["first_name"],
            last_name=values["last_name"],
            phone=values.get("phone"),
            email=values.get("email"),
            temporary_start_at=values.get("start_at"),
            temporary_end_at=values.get("end_at"),
            recurring_start_time=values.get("recurring_start_time"),
            recurring_end_time=values.get("recurring_end_time"),
            recurring_repeat_on=values.get("recurring_days"),
        )

    async def async_update_guest(
        self,
        hub_id: int,
        device_id: int,
        code_id: int,
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        return await self._api.async_update_guest_access_code(
            hub_id=hub_id,
            device_id=device_id,
            code_id=code_id,
            activation_type=values.get("activation_type"),
            first_name=values.get("first_name"),
            last_name=values.get("last_name"),
            phone=values.get("phone"),
            email=values.get("email"),
            temporary_start_at=values.get("start_at"),
            temporary_end_at=values.get("end_at"),
            recurring_start_time=values.get("recurring_start_time"),
            recurring_end_time=values.get("recurring_end_time"),
            recurring_repeat_on=values.get("recurring_days"),
        )

    async def async_delete_guest(
        self, hub_id: int, device_id: int, code_id: int
    ) -> Any:
        return await self._api.async_delete_guest_access_code(
            hub_id=hub_id,
            device_id=device_id,
            code_id=code_id,
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _value(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise AccessValidationError(f"{field} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise AccessValidationError(f"{field} must be a positive integer") from None
    if result <= 0 or (isinstance(value, float) and not value.is_integer()):
        raise AccessValidationError(f"{field} must be a positive integer")
    if isinstance(value, str) and value.strip() != str(result):
        raise AccessValidationError(f"{field} must be a positive integer")
    return result


def _optional_positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _nested_id(data: Mapping[str, Any], key: str) -> int | None:
    nested = _mapping(data.get(key))
    return _optional_positive_int(nested.get("id"))


def _hub_device_ids(hub: Mapping[str, Any]) -> set[int]:
    ids: set[int] = set()
    for key in ("device_id", "primary_device_id", "lock_device_id"):
        value = _optional_positive_int(hub.get(key))
        if value:
            ids.add(value)
    for key in ("devices", "locks", "entry_controls"):
        for device in _sequence(hub.get(key)):
            if isinstance(device, Mapping):
                value = _optional_positive_int(
                    _value(device, "id", "device_id", "lock_device_id")
                )
            else:
                value = _optional_positive_int(device)
            if value:
                ids.add(value)
    return ids


def resolve_hub_for_lock(
    hubs: Sequence[Mapping[str, Any]], lock_device_id: int
) -> dict[str, int]:
    """Resolve a hub/unit for a lock without guessing across units."""
    lock_id = _positive_id(lock_device_id, "lock device ID")
    parsed: list[dict[str, Any]] = []
    for raw_hub in hubs:
        hub = _mapping(raw_hub)
        hub_id = _optional_positive_int(_value(hub, "id", "hub_id"))
        unit_id = _optional_positive_int(_value(hub, "unit_id", "home_unit_id"))
        if unit_id is None:
            unit_id = _nested_id(hub, "unit")
        if hub_id and unit_id:
            parsed.append(
                {
                    "hub_id": hub_id,
                    "unit_id": unit_id,
                    "device_ids": _hub_device_ids(hub),
                }
            )

    if not parsed:
        raise AccessValidationError("SmartRent returned no usable hub and unit")

    matches = [hub for hub in parsed if lock_id in hub["device_ids"]]
    if len(matches) == 1:
        return {
            "hub_id": matches[0]["hub_id"],
            "unit_id": matches[0]["unit_id"],
        }
    if len(matches) > 1:
        raise AccessValidationError(
            "The selected lock is associated with multiple SmartRent hubs"
        )

    units = {hub["unit_id"] for hub in parsed}
    if len(units) > 1:
        raise AccessValidationError(
            "This SmartRent account has multiple units and the selected lock "
            "could not be matched to exactly one"
        )
    if len(parsed) > 1:
        raise AccessValidationError(
            "The selected lock could not be matched to exactly one SmartRent hub"
        )
    return {"hub_id": parsed[0]["hub_id"], "unit_id": parsed[0]["unit_id"]}


def canonicalize_weekdays(days: Any) -> list[str]:
    """Validate and canonicalize full English weekday names."""
    if not _sequence(days):
        raise AccessValidationError("recurring_days must contain weekdays")
    result: list[str] = []
    for day in _sequence(days):
        if not isinstance(day, str) or day.lower() not in _WEEKDAYS_BY_LOWER:
            raise AccessValidationError(
                "recurring_days must use full English weekday names"
            )
        canonical = _WEEKDAYS_BY_LOWER[day.lower()]
        if canonical not in result:
            result.append(canonical)
    return result


def _required_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccessValidationError(f"{field} is required")
    value = value.strip()
    if len(value) > 100:
        raise AccessValidationError(f"{field} is too long")
    return value


def _optional_contact(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AccessValidationError(f"{field} must be a non-empty string")
    value = value.strip()
    if field == "email" and not _EMAIL_RE.fullmatch(value):
        raise AccessValidationError("email is not valid")
    if field == "phone" and not _PHONE_RE.fullmatch(value):
        raise AccessValidationError("phone is not valid")
    return value


def _activation_type(value: Any) -> str:
    if value not in ACTIVATION_TYPES:
        raise AccessValidationError(
            "activation_type must be permanent, temporary, or recurring"
        )
    return str(value)


def _aware_timestamp(value: Any, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str):
        raise AccessValidationError(f"{field} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AccessValidationError(
            f"{field} must be a timezone-aware ISO timestamp"
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AccessValidationError(f"{field} must include a timezone offset")
    return value, parsed


def _recurring_time(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _RECURRING_TIME_RE.fullmatch(value):
        raise AccessValidationError(f"{field} must be HH:MM or HH:MM:SS")
    return value


def _config_source(access: Mapping[str, Any]) -> Mapping[str, Any]:
    config = _mapping(access.get("config"))
    for key in ("guest_access", "guest_codes", "access_codes"):
        nested = _mapping(config.get(key))
        if nested:
            return {**config, **nested}
    return config


def _config_int(config: Mapping[str, Any], *keys: str) -> int | None:
    return _optional_positive_int(_value(config, *keys))


def normalize_access_config(access: Mapping[str, Any]) -> dict[str, Any]:
    """Return only documented, non-credential access policy fields."""
    config = _config_source(access)
    lengths = _value(
        config,
        "allowed_pin_lengths",
        "allowed_pin_code_lengths",
        "allowed_code_lengths",
        "pin_lengths",
        "code_lengths",
    )
    allowed_lengths: list[int] = []
    for length in _sequence(lengths):
        parsed = _optional_positive_int(length)
        if parsed and parsed not in allowed_lengths:
            allowed_lengths.append(parsed)
    singular_length = _config_int(config, "pin_code_length", "code_length")
    if singular_length and singular_length not in allowed_lengths:
        allowed_lengths.append(singular_length)
    minimum = _config_int(config, "min_pin_length", "minimum_pin_length")
    maximum = _config_int(config, "max_pin_length", "maximum_pin_length")
    if not allowed_lengths and minimum and maximum and maximum - minimum <= 12:
        allowed_lengths = list(range(minimum, maximum + 1))

    result: dict[str, Any] = {"allowed_pin_lengths": sorted(allowed_lengths)}
    aliases = {
        "max_guest_codes": ("max_guest_codes", "maximum_guest_codes"),
        "max_permanent_codes": (
            "max_permanent_codes",
            "maximum_permanent_codes",
        ),
        "max_temporary_codes": (
            "max_temporary_codes",
            "maximum_temporary_codes",
        ),
        "max_recurring_codes": (
            "max_recurring_codes",
            "maximum_recurring_codes",
        ),
        "max_temporary_days": (
            "max_temporary_days",
            "temporary_max_days",
            "temporary_window_days",
        ),
        "max_temporary_hours": (
            "max_temporary_hours",
            "temporary_max_hours",
            "temporary_window_hours",
            "max_temporary_window_hours",
        ),
        "max_recurring_days": (
            "max_recurring_days",
            "recurring_max_days",
            "max_recurring_days_per_week",
        ),
        "max_recurring_window_minutes": (
            "max_recurring_window_minutes",
            "recurring_max_window_minutes",
            "max_recurring_duration_minutes",
        ),
        "max_recurring_window_hours": (
            "max_recurring_window_hours",
            "recurring_max_window_hours",
            "max_recurring_duration_hours",
        ),
    }
    for output_key, source_keys in aliases.items():
        value = _config_int(config, *source_keys)
        if value is not None:
            result[output_key] = value
    phone_required = _value(
        config, "guest_phone_number_required", "require_guest_phone_number"
    )
    if isinstance(phone_required, bool):
        result["guest_phone_number_required"] = phone_required
    return result


def _primary_device_id(access: Mapping[str, Any]) -> int | None:
    direct = _optional_positive_int(
        _value(access, "primary_device_id", "primary_lock_device_id")
    )
    if direct:
        return direct
    config = _config_source(access)
    direct = _optional_positive_int(
        _value(config, "primary_device_id", "primary_lock_device_id")
    )
    return (
        direct
        or _nested_id(config, "primary_device")
        or _nested_id(access, "primary_device")
    )


def _guest_list(access: Mapping[str, Any]) -> Sequence[Any]:
    return _sequence(_value(access, "guests", "guest_access_codes"))


def _guest_pin_codes(guest: Mapping[str, Any]) -> Sequence[Any]:
    """Return only PIN records from current or legacy guest envelopes."""
    direct = _sequence(guest.get("pin_codes"))
    if direct:
        return direct
    return _sequence(_mapping(guest.get("access")).get("pin_codes"))


def _create_response_tokens(response: Mapping[str, Any]) -> tuple[set[int], set[str]]:
    """Extract create correlation IDs/PINs from known response envelopes."""
    ids: set[int] = set()
    pins: set[str] = set()
    pending: list[Mapping[str, Any]] = [response]
    while pending:
        item = pending.pop()
        for key in ("id", "code_id", "access_code_id", "guest_id"):
            value = _optional_positive_int(item.get(key))
            if value:
                ids.add(value)
        for key in ("code", "pin", "pin_code"):
            value = item.get(key)
            if value is not None and not isinstance(value, (Mapping, Sequence)):
                pins.add(str(value))
        for key in (
            "data",
            "guest",
            "guest_access_code",
            "access_code",
            "pin_code",
            "pin_codes",
        ):
            nested = item.get(key)
            if isinstance(nested, Mapping):
                pending.append(nested)
            else:
                pending.extend(
                    value for value in _sequence(nested) if isinstance(value, Mapping)
                )
    return ids, pins


def _guest_value(guest: Mapping[str, Any], *keys: str) -> Any:
    value = _value(guest, *keys)
    if value is not None:
        return value
    person = _mapping(_value(guest, "guest", "user", "person"))
    return _value(person, *keys)


def _normalize_code(
    guest: Mapping[str, Any], pin: Mapping[str, Any], primary_device_id: int | None
) -> dict[str, Any] | None:
    code_id = _optional_positive_int(_value(pin, "id", "code_id", "access_code_id"))
    if not code_id:
        return None
    device_id = _optional_positive_int(
        _value(pin, "device_id", "lock_device_id", "entry_control_id")
    ) or _nested_id(pin, "device")
    device_records = [
        _mapping(raw_device) for raw_device in _sequence(pin.get("devices"))
    ]
    device_ids = {
        parsed
        for device_record in device_records
        if (parsed := _optional_positive_int(device_record.get("id")))
    }
    primary_device_ids = [
        parsed
        for device_record in device_records
        if device_record.get("primary_lock") is True
        and (parsed := _optional_positive_int(device_record.get("id")))
    ]
    if device_id is None and len(primary_device_ids) == 1:
        device_id = primary_device_ids[0]
    if device_id is None and len(device_ids) == 1:
        device_id = next(iter(device_ids))
    if device_id is None:
        device_id = _optional_positive_int(_value(guest, "device_id", "lock_device_id"))
    if device_id is None:
        device_id = primary_device_id
    if device_id:
        device_ids.add(device_id)

    pin_value = _value(pin, "code", "pin", "pin_code")
    if pin_value is not None:
        pin_value = str(pin_value)

    recurring_days = _value(
        guest,
        "recurring_days",
        "recurring_repeat_on",
        "repeat_on",
    )
    if recurring_days is None:
        recurring_days = _value(
            pin,
            "recurring_days",
            "recurring_repeat_on",
            "repeat_on",
        )
    canonical_days: list[str] | None = None
    if _sequence(recurring_days):
        try:
            canonical_days = canonicalize_weekdays(recurring_days)
        except AccessValidationError:
            canonical_days = None

    return {
        "code_id": code_id,
        "guest_id": _optional_positive_int(
            _guest_value(guest, "id", "guest_id", "access_id")
        ),
        "device_id": device_id,
        "device_ids": device_ids,
        "activation_type": _value(guest, "activation_type", "type")
        or _value(pin, "activation_type", "type"),
        "first_name": _guest_value(guest, "first_name"),
        "last_name": _guest_value(guest, "last_name"),
        "phone": _guest_value(guest, "phone"),
        "email": _guest_value(guest, "email"),
        "start_at": _value(guest, "start_at", "temporary_start_at", "starts_at")
        or _value(pin, "start_at", "temporary_start_at", "starts_at"),
        "end_at": _value(guest, "end_at", "temporary_end_at", "ends_at")
        or _value(pin, "end_at", "temporary_end_at", "ends_at"),
        "recurring_start_time": _value(guest, "recurring_start_time", "start_time")
        or _value(pin, "recurring_start_time", "start_time"),
        "recurring_end_time": _value(guest, "recurring_end_time", "end_time")
        or _value(pin, "recurring_end_time", "end_time"),
        "recurring_days": canonical_days,
        "provisioning_status": _value(
            pin, "provisioning_status", "provision_status", "status", "state"
        ),
        "pin": pin_value,
    }


def guest_codes_for_lock(
    access: Mapping[str, Any], lock_device_id: int
) -> list[dict[str, Any]]:
    """Extract guest pin_codes for the selected lock or unit primary device."""
    lock_id = _positive_id(lock_device_id, "lock device ID")
    primary_id = _primary_device_id(access)
    allowed_device_ids = {lock_id}
    if primary_id:
        allowed_device_ids.add(primary_id)

    result: list[dict[str, Any]] = []
    for raw_guest in _guest_list(access):
        guest = _mapping(raw_guest)
        # Deliberately inspect only guest pin_codes. Resident/mobile/fob data is
        # never traversed or normalized by this integration.
        for raw_pin in _guest_pin_codes(guest):
            pin = _mapping(raw_pin)
            code = _normalize_code(guest, pin, primary_id)
            if code and set(code.get("device_ids", ())).intersection(
                allowed_device_ids
            ):
                result.append(code)
    return result


def find_guest_code(
    access: Mapping[str, Any], lock_device_id: int, code_id: int
) -> dict[str, Any]:
    """Find one guest PIN while rejecting resident and other-lock IDs."""
    requested_id = _positive_id(code_id, "code_id")
    matches = [
        code
        for code in guest_codes_for_lock(access, lock_device_id)
        if code["code_id"] == requested_id
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AccessValidationError(
            "The guest code ID is ambiguous for the selected lock"
        )

    guest_ids_elsewhere: set[int] = set()
    primary_id = _primary_device_id(access)
    for raw_guest in _guest_list(access):
        guest = _mapping(raw_guest)
        for raw_pin in _guest_pin_codes(guest):
            code = _normalize_code(guest, _mapping(raw_pin), primary_id)
            if code and code["code_id"] == requested_id:
                guest_ids_elsewhere.add(code["code_id"])
    if guest_ids_elsewhere:
        raise AccessValidationError(
            "The guest code does not belong to the selected lock or primary device"
        )
    raise AccessValidationError("No guest code with that ID exists")


def _public_code(code: Mapping[str, Any], include_pin: bool) -> dict[str, Any]:
    fields = (
        "code_id",
        "device_id",
        "activation_type",
        "first_name",
        "last_name",
        "start_at",
        "end_at",
        "recurring_start_time",
        "recurring_end_time",
        "recurring_days",
        "provisioning_status",
    )
    result = {key: code[key] for key in fields if code.get(key) is not None}
    if include_pin and code.get("pin") is not None:
        result["pin"] = str(code["pin"])
    return result


def _temporary_limit(config: Mapping[str, Any]) -> timedelta | None:
    if "max_temporary_hours" in config:
        return timedelta(hours=config["max_temporary_hours"])
    if "max_temporary_days" in config:
        return timedelta(days=config["max_temporary_days"])
    return None


def _time_seconds(value: str) -> int:
    parsed = time.fromisoformat(value)
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


def _validate_schedule(values: dict[str, Any], config: Mapping[str, Any]) -> None:
    activation = values["activation_type"]
    if activation == "permanent":
        for key in (
            "start_at",
            "end_at",
            "recurring_start_time",
            "recurring_end_time",
            "recurring_days",
        ):
            values.pop(key, None)
        return

    if activation == "temporary":
        if values.get("start_at") is None or values.get("end_at") is None:
            raise AccessValidationError(
                "start_at and end_at are required for temporary access"
            )
        start_text, start = _aware_timestamp(values["start_at"], "start_at")
        end_text, end = _aware_timestamp(values["end_at"], "end_at")
        if start >= end:
            raise AccessValidationError("start_at must be before end_at")
        limit = _temporary_limit(config)
        if limit is not None and end - start > limit:
            raise AccessValidationError(
                "The temporary access window exceeds the SmartRent policy limit"
            )
        values["start_at"] = start_text
        values["end_at"] = end_text
        for key in (
            "recurring_start_time",
            "recurring_end_time",
            "recurring_days",
        ):
            values.pop(key, None)
        return

    if (
        values.get("recurring_start_time") is None
        or values.get("recurring_end_time") is None
        or values.get("recurring_days") is None
    ):
        raise AccessValidationError(
            "recurring_start_time, recurring_end_time, and recurring_days are "
            "required for recurring access"
        )
    recurring_start = _recurring_time(
        values["recurring_start_time"], "recurring_start_time"
    )
    recurring_end = _recurring_time(values["recurring_end_time"], "recurring_end_time")
    days = canonicalize_weekdays(values["recurring_days"])
    max_days = config.get("max_recurring_days")
    if max_days is not None and len(days) > max_days:
        raise AccessValidationError(
            "The recurring schedule exceeds the SmartRent weekday limit"
        )
    duration = (_time_seconds(recurring_end) - _time_seconds(recurring_start)) % (
        24 * 3600
    )
    if duration == 0:
        duration = 24 * 3600
    max_minutes = config.get("max_recurring_window_minutes")
    if max_minutes is None and config.get("max_recurring_window_hours") is not None:
        max_minutes = config["max_recurring_window_hours"] * 60
    if max_minutes is not None and duration > max_minutes * 60:
        raise AccessValidationError(
            "The recurring access window exceeds the SmartRent policy limit"
        )
    values["recurring_start_time"] = recurring_start
    values["recurring_end_time"] = recurring_end
    values["recurring_days"] = days
    values.pop("start_at", None)
    values.pop("end_at", None)


def validate_create_values(
    values: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate and normalize a create request against live policy."""
    activation = _activation_type(values.get("activation_type"))
    has_temporary = (
        values.get("start_at") is not None or values.get("end_at") is not None
    )
    has_recurring = any(
        values.get(key) is not None
        for key in (
            "recurring_start_time",
            "recurring_end_time",
            "recurring_days",
        )
    )
    if activation == "permanent" and (has_temporary or has_recurring):
        raise AccessValidationError("Permanent access cannot include a schedule")
    if activation == "temporary" and has_recurring:
        raise AccessValidationError(
            "Temporary access cannot include a recurring schedule"
        )
    if activation == "recurring" and has_temporary:
        raise AccessValidationError(
            "Recurring access cannot include temporary timestamps"
        )
    result = {
        "activation_type": activation,
        "first_name": _required_name(values.get("first_name"), "first_name"),
        "last_name": _required_name(values.get("last_name"), "last_name"),
        "phone": _optional_contact(values.get("phone"), "phone"),
        "email": _optional_contact(values.get("email"), "email"),
    }
    if result["phone"] is None and result["email"] is None:
        raise AccessValidationError("phone or email is required")
    if config.get("guest_phone_number_required") is True and result["phone"] is None:
        raise AccessValidationError(
            "phone is required by the SmartRent guest access policy"
        )
    for key in (
        "start_at",
        "end_at",
        "recurring_start_time",
        "recurring_end_time",
        "recurring_days",
    ):
        if values.get(key) is not None:
            result[key] = values[key]
    _validate_schedule(result, config)
    return result


def _guest_counts(access: Mapping[str, Any]) -> tuple[int, dict[str, int]]:
    total = 0
    counts = {activation: 0 for activation in ACTIVATION_TYPES}
    for raw_guest in _guest_list(access):
        guest = _mapping(raw_guest)
        if not _guest_pin_codes(guest):
            continue
        total += 1
        activation = _value(guest, "activation_type", "type")
        if activation in counts:
            counts[activation] += 1
    return total, counts


def validate_create_capacity(
    access: Mapping[str, Any], activation_type: str, config: Mapping[str, Any]
) -> None:
    """Enforce the unit's live guest-code count limits."""
    total, counts = _guest_counts(access)
    total_limit = config.get("max_guest_codes")
    if total_limit is not None and total >= total_limit:
        raise AccessValidationError("The SmartRent guest code limit has been reached")
    activation_limit = config.get(f"max_{activation_type}_codes")
    if activation_type == "permanent" and activation_limit == 0:
        raise AccessValidationError(
            "Permanent guest codes are disabled by the SmartRent policy"
        )
    if activation_limit is not None and counts[activation_type] >= activation_limit:
        raise AccessValidationError(
            f"The SmartRent {activation_type} guest code limit has been reached"
        )


def _same_timestamp(left: Any, right: Any) -> bool:
    if left == right:
        return True
    try:
        left_datetime = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_datetime = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
        # SmartRent currently serializes guest schedules at whole-second
        # precision even when HA supplied fractional seconds.
        return abs((left_datetime - right_datetime).total_seconds()) < 1
    except (TypeError, ValueError):
        return False


def _matches_values(code: Mapping[str, Any], values: Mapping[str, Any]) -> bool:
    for key in ("activation_type", "first_name", "last_name", "phone", "email"):
        if key in values and values[key] is not None and code.get(key) != values[key]:
            return False
    for key in ("start_at", "end_at"):
        if key in values and not _same_timestamp(code.get(key), values[key]):
            return False
    for key in ("recurring_start_time", "recurring_end_time"):
        if key in values:
            try:
                if _time_seconds(str(code.get(key))) != _time_seconds(str(values[key])):
                    return False
            except ValueError:
                return False
    if "recurring_days" in values and set(code.get("recurring_days") or ()) != set(
        values["recurring_days"]
    ):
        return False
    if values.get("activation_type") == "permanent" and any(
        code.get(key) is not None
        for key in (
            "start_at",
            "end_at",
            "recurring_start_time",
            "recurring_end_time",
            "recurring_days",
        )
    ):
        return False
    return True


class SmartRentAccessManager:
    """Manage guest codes for exactly one SmartRent lock entity."""

    def __init__(
        self,
        api: Any,
        lock_device_id: int,
        *,
        verification_timeout: float = 12.0,
        verification_interval: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._api = SmartRentAccessAPIAdapter(api)
        self._lock_device_id = _positive_id(lock_device_id, "lock device ID")
        self._verification_timeout = max(0.0, verification_timeout)
        self._verification_interval = max(0.01, verification_interval)
        self._sleep = sleep

    async def _async_context(self) -> tuple[dict[str, int], dict[str, Any]]:
        try:
            hubs = await self._api.async_get_hubs()
            target = resolve_hub_for_lock(hubs, self._lock_device_id)
            access = await self._api.async_get_unit_access(target["unit_id"])
        except AccessManagerError:
            raise
        except Exception:
            raise AccessOperationError(
                "Unable to read SmartRent guest access data"
            ) from None
        if not isinstance(access, Mapping):
            raise AccessOperationError("SmartRent returned invalid guest access data")
        return target, dict(access)

    async def async_get_guest_codes(self) -> dict[str, Any]:
        """Get safe policy data and guest PINs for an explicit response."""
        target, access = await self._async_context()
        codes = guest_codes_for_lock(access, self._lock_device_id)
        return {
            **target,
            "lock_device_id": self._lock_device_id,
            "config": normalize_access_config(access),
            "guest_codes": [_public_code(code, include_pin=True) for code in codes],
        }

    async def _async_verify(
        self,
        unit_id: int,
        predicate: Callable[[Mapping[str, Any]], dict[str, Any] | None],
        operation: str,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._verification_timeout
        while True:
            remaining = deadline - loop.time()
            try:
                access = await asyncio.wait_for(
                    self._api.async_get_unit_access(unit_id),
                    timeout=max(remaining, 0.001),
                )
                if isinstance(access, Mapping) and (result := predicate(access)):
                    return result
            except (AccessManagerError, TimeoutError):
                pass
            except Exception:
                raise AccessOperationError(
                    "SmartRent guest access verification failed"
                ) from None
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AccessAcceptedNotVerifiedError(
                    f"SmartRent accepted the {operation}, but it could not be "
                    "verified by a fresh read-back"
                )
            await self._sleep(min(self._verification_interval, remaining))

    async def async_create_guest_code(self, **service_data: Any) -> dict[str, Any]:
        """Create a server-generated guest PIN and verify it by read-back."""
        target, access = await self._async_context()
        config = normalize_access_config(access)
        values = validate_create_values(service_data, config)
        validate_create_capacity(access, values["activation_type"], config)
        try:
            response = await self._api.async_create_guest(target["unit_id"], values)
        except Exception:
            raise AccessOperationError(
                "SmartRent did not accept the guest code creation"
            ) from None
        response_ids, response_pins = _create_response_tokens(_mapping(response))
        before_ids = {
            code["code_id"]
            for code in guest_codes_for_lock(access, self._lock_device_id)
        }

        def created(access_data: Mapping[str, Any]) -> dict[str, Any] | None:
            candidates = [
                code
                for code in guest_codes_for_lock(access_data, self._lock_device_id)
                if code["code_id"] not in before_ids
            ]
            if response_ids:
                candidates = [
                    code
                    for code in candidates
                    if response_ids.intersection(
                        value
                        for value in (code.get("code_id"), code.get("guest_id"))
                        if isinstance(value, int)
                    )
                ]
            if response_pins:
                candidates = [
                    code for code in candidates if code.get("pin") in response_pins
                ]
            if not response_ids and not response_pins:
                candidates = [
                    code for code in candidates if _matches_values(code, values)
                ]
            return candidates[0] if len(candidates) == 1 else None

        code = await self._async_verify(target["unit_id"], created, "creation")
        public_code = _public_code(code, include_pin=True)
        public_code.setdefault("provisioning_status", "unknown")
        return {
            "verified": True,
            "guest_code": public_code,
        }

    async def async_update_guest_code(
        self, code_id: int, **service_data: Any
    ) -> dict[str, Any]:
        """Update only a guest PIN and verify requested fields by read-back."""
        target, access = await self._async_context()
        current = find_guest_code(access, self._lock_device_id, code_id)
        if not service_data:
            raise AccessValidationError("At least one update field is required")

        current_phone = current.get("phone")
        current_email = current.get("email")
        if current_phone is None and current_email is None:
            raise AccessValidationError(
                "The current guest contact could not be read safely; "
                "update was not sent"
            )
        values: dict[str, Any] = {
            "activation_type": current.get("activation_type"),
            "first_name": current.get("first_name"),
            "last_name": current.get("last_name"),
            "phone": current_phone,
            "email": current_email,
            "start_at": current.get("start_at"),
            "end_at": current.get("end_at"),
            "recurring_start_time": current.get("recurring_start_time"),
            "recurring_end_time": current.get("recurring_end_time"),
            "recurring_days": current.get("recurring_days"),
        }
        for key, value in service_data.items():
            if value is not _MISSING:
                values[key] = value
        values["activation_type"] = _activation_type(values["activation_type"])
        values["first_name"] = _required_name(values["first_name"], "first_name")
        values["last_name"] = _required_name(values["last_name"], "last_name")
        values["phone"] = _optional_contact(values.get("phone"), "phone")
        values["email"] = _optional_contact(values.get("email"), "email")
        if values["phone"] is None and values["email"] is None:
            raise AccessValidationError("phone or email is required")
        _validate_schedule(values, normalize_access_config(access))

        device_id = _positive_id(current.get("device_id"), "guest code device ID")
        requested_id = _positive_id(code_id, "code_id")
        try:
            await self._api.async_update_guest(
                target["hub_id"], device_id, requested_id, values
            )
        except Exception:
            raise AccessOperationError(
                "SmartRent did not accept the guest code update"
            ) from None

        def updated(access_data: Mapping[str, Any]) -> dict[str, Any] | None:
            try:
                candidate = find_guest_code(
                    access_data, self._lock_device_id, requested_id
                )
            except AccessValidationError:
                return None
            return candidate if _matches_values(candidate, values) else None

        code = await self._async_verify(target["unit_id"], updated, "update")
        return {
            "verified": True,
            "guest_code": _public_code(code, include_pin=False),
        }

    async def async_delete_guest_code(self, code_id: int) -> dict[str, Any]:
        """Delete only a guest PIN and verify its absence by read-back."""
        target, access = await self._async_context()
        current = find_guest_code(access, self._lock_device_id, code_id)
        requested_id = _positive_id(code_id, "code_id")
        device_id = _positive_id(current.get("device_id"), "guest code device ID")
        try:
            await self._api.async_delete_guest(
                target["hub_id"], device_id, requested_id
            )
        except Exception:
            raise AccessOperationError(
                "SmartRent did not accept the guest code deletion"
            ) from None

        def deleted(access_data: Mapping[str, Any]) -> dict[str, Any] | None:
            matching = [
                code
                for code in guest_codes_for_lock(access_data, self._lock_device_id)
                if code["code_id"] == requested_id
            ]
            if matching:
                return None
            return {"deleted": True}

        await self._async_verify(target["unit_id"], deleted, "deletion")
        return {
            "verified": True,
            "deleted": True,
            "code_id": requested_id,
            "device_id": device_id,
        }
