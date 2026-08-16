"""Tests for SmartRent guest access management without a Home Assistant runtime."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

import pytest

MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "smartrent" / "access_manager.py"
)
SPEC = importlib.util.spec_from_file_location("smartrent_access_manager", MODULE_PATH)
assert SPEC and SPEC.loader
access_manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = access_manager
SPEC.loader.exec_module(access_manager)

AccessAcceptedNotVerifiedError = access_manager.AccessAcceptedNotVerifiedError
AccessOperationError = access_manager.AccessOperationError
AccessValidationError = access_manager.AccessValidationError
SmartRentAccessManager = access_manager.SmartRentAccessManager
canonicalize_weekdays = access_manager.canonicalize_weekdays
find_guest_code = access_manager.find_guest_code
guest_codes_for_lock = access_manager.guest_codes_for_lock
normalize_access_config = access_manager.normalize_access_config
resolve_hub_for_lock = access_manager.resolve_hub_for_lock
validate_create_capacity = access_manager.validate_create_capacity
validate_create_values = access_manager.validate_create_values

LOCK_ID = 56
HUB_ID = 12
UNIT_ID = 34


def pin_code(
    code_id: int = 9,
    *,
    device_id: int = LOCK_ID,
    pin: str = "004321",
    status: str = "provisioned",
) -> dict[str, Any]:
    return {
        "id": code_id,
        "device_id": device_id,
        "code": pin,
        "provisioning_status": status,
    }


def guest(
    *,
    code: dict[str, Any] | None = None,
    activation_type: str = "permanent",
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    phone: str | None = None,
    email: str | None = "ada@example.com",
    **schedule: Any,
) -> dict[str, Any]:
    return {
        "id": 90,
        "activation_type": activation_type,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email,
        "pin_codes": [code or pin_code()],
        **schedule,
    }


def unit_access(
    *guests: dict[str, Any],
    config: dict[str, Any] | None = None,
    primary_device_id: int = LOCK_ID,
) -> dict[str, Any]:
    return {
        "config": {
            "primary_device_id": primary_device_id,
            "allowed_pin_lengths": [4, 6],
            "max_guest_codes": 20,
            "max_permanent_codes": 10,
            "max_temporary_codes": 10,
            "max_recurring_codes": 10,
            **(config or {}),
        },
        "guests": list(guests),
        "resident": {
            "first_name": "Resident",
            "pin_codes": [{"id": 777, "device_id": LOCK_ID, "code": "9999"}],
        },
        "mobile_credentials": [{"id": 778, "credential": "secret-mobile"}],
        "fobs": [{"id": 779, "credential": "secret-fob"}],
    }


class FakeAPI:
    def __init__(
        self,
        accesses: list[dict[str, Any]],
        *,
        hubs: list[dict[str, Any]] | None = None,
        create_response: dict[str, Any] | None = None,
    ) -> None:
        self.hubs = hubs or [
            {"id": HUB_ID, "unit_id": UNIT_ID, "devices": [{"id": LOCK_ID}]}
        ]
        self.accesses = list(accesses)
        self.last_access = accesses[-1]
        self.create_response = create_response or {"id": 9, "code": "004321"}
        self.get_calls: list[int] = []
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.create_error: Exception | None = None
        self.update_error: Exception | None = None
        self.delete_error: Exception | None = None

    async def async_get_hubs(self) -> list[dict[str, Any]]:
        return self.hubs

    async def async_get_unit_access(self, unit_id: int) -> dict[str, Any]:
        self.get_calls.append(unit_id)
        if self.accesses:
            self.last_access = self.accesses.pop(0)
        return self.last_access

    async def async_create_guest_access_code(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        if self.create_error:
            raise self.create_error
        return self.create_response

    async def async_update_guest_access_code(self, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append(kwargs)
        if self.update_error:
            raise self.update_error
        return {"accepted": True}

    async def async_delete_guest_access_code(self, **kwargs: Any) -> None:
        self.delete_calls.append(kwargs)
        if self.delete_error:
            raise self.delete_error


def manager(api: FakeAPI, timeout: float = 0) -> Any:
    return SmartRentAccessManager(
        api,
        LOCK_ID,
        verification_timeout=timeout,
        verification_interval=0.01,
    )


def test_resolve_single_unit_and_explicit_multiple_unit_target() -> None:
    assert resolve_hub_for_lock([{"id": 1, "unit_id": 2}], LOCK_ID) == {
        "hub_id": 1,
        "unit_id": 2,
    }
    hubs = [
        {"id": 1, "unit_id": 2, "devices": [{"id": 100}]},
        {"id": 3, "unit": {"id": 4}, "locks": [{"device_id": LOCK_ID}]},
    ]
    assert resolve_hub_for_lock(hubs, LOCK_ID) == {"hub_id": 3, "unit_id": 4}


def test_ambiguous_multiple_unit_account_fails_instead_of_guessing() -> None:
    hubs = [{"id": 1, "unit_id": 2}, {"id": 3, "unit_id": 4}]
    with pytest.raises(AccessValidationError, match="multiple units"):
        resolve_hub_for_lock(hubs, LOCK_ID)


def test_duplicate_lock_hub_mapping_is_rejected() -> None:
    hubs = [
        {"id": 1, "unit_id": 2, "device_id": LOCK_ID},
        {"id": 3, "unit_id": 4, "device_id": LOCK_ID},
    ]
    with pytest.raises(AccessValidationError, match="multiple SmartRent hubs"):
        resolve_hub_for_lock(hubs, LOCK_ID)


@pytest.mark.parametrize("invalid_id", [True, 0, -1, 1.5, "1.5"])
def test_ids_must_be_positive_integers(invalid_id: Any) -> None:
    with pytest.raises(AccessValidationError, match="positive integer"):
        find_guest_code(unit_access(guest()), LOCK_ID, invalid_id)


def test_safe_normalization_preserves_pin_string_and_excludes_other_credentials() -> (
    None
):
    access = unit_access(guest())
    result = guest_codes_for_lock(access, LOCK_ID)

    assert result[0]["pin"] == "004321"
    assert isinstance(result[0]["pin"], str)
    serialized = repr(result)
    assert "9999" not in serialized
    assert "secret-mobile" not in serialized
    assert "secret-fob" not in serialized


def test_live_nested_devices_shape_is_scoped_to_selected_lock() -> None:
    live_guest = {
        "id": 91,
        "first_name": "Live",
        "last_name": "Shape",
        "email": "live@example.invalid",
        "access": {
            "pin_codes": [
                {
                    "id": 777,
                    "code": "0123",
                    "activation_type": "temporary",
                    "devices": [
                        {
                            "id": LOCK_ID,
                            "primary_lock": True,
                            "status": "add_success",
                        }
                    ],
                }
            ],
            "mobile": [],
            "fobs": [],
        },
    }
    access = unit_access()
    access["guests"] = [live_guest]

    result = guest_codes_for_lock(access, LOCK_ID)

    assert [code["code_id"] for code in result] == [777]
    assert result[0]["pin"] == "0123"


def test_live_recurring_weekday_policy_alias_is_normalized() -> None:
    access = unit_access(
        config={
            "allowed_pin_code_lengths": [4, 6],
            "max_recurring_days_per_week": 5,
            "max_temporary_window_hours": 48,
            "guest_phone_number_required": True,
        }
    )

    normalized = normalize_access_config(access)

    assert normalized["allowed_pin_lengths"] == [4, 6]
    assert normalized["max_recurring_days"] == 5
    assert normalized["max_temporary_hours"] == 48
    assert normalized["guest_phone_number_required"] is True


def test_live_phone_required_policy_is_enforced() -> None:
    values = {
        "activation_type": "temporary",
        "first_name": "A",
        "last_name": "B",
        "email": "guest@example.invalid",
        "start_at": "2026-08-16T08:00:00Z",
        "end_at": "2026-08-16T09:00:00Z",
    }

    with pytest.raises(AccessValidationError, match="phone is required"):
        validate_create_values(values, {"guest_phone_number_required": True})


@pytest.mark.asyncio
async def test_get_response_has_safe_config_and_only_explicit_guest_pin() -> None:
    api = FakeAPI([unit_access(guest())])
    response = await manager(api).async_get_guest_codes()

    assert response["config"]["allowed_pin_lengths"] == [4, 6]
    assert response["guest_codes"][0]["pin"] == "004321"
    rendered = repr(response)
    assert "ada@example.com" not in rendered
    assert "9999" not in rendered
    assert "secret-mobile" not in rendered


def test_config_normalization_includes_limits_but_not_unknown_values() -> None:
    access = unit_access(
        config={
            "temporary_max_days": 7,
            "recurring_max_days": 3,
            "max_recurring_duration_minutes": 180,
            "private_payload": "do-not-return",
        }
    )
    result = normalize_access_config(access)

    assert result["max_temporary_days"] == 7
    assert result["max_recurring_days"] == 3
    assert result["max_recurring_window_minutes"] == 180
    assert "private_payload" not in result
    assert "do-not-return" not in repr(result)


@pytest.mark.parametrize("activation", ["permanent", "temporary", "recurring"])
def test_all_activation_types_validate(activation: str) -> None:
    values: dict[str, Any] = {
        "activation_type": activation,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
    }
    if activation == "temporary":
        values.update(
            start_at="2026-08-16T08:00:00+00:00",
            end_at="2026-08-16T09:00:00+00:00",
        )
    if activation == "recurring":
        values.update(
            recurring_start_time="08:00",
            recurring_end_time="09:00:00",
            recurring_days=["monday", "FRIDAY"],
        )

    result = validate_create_values(values, {})

    assert result["activation_type"] == activation
    if activation == "recurring":
        assert result["recurring_days"] == ["Monday", "Friday"]


@pytest.mark.parametrize(
    "values, message",
    [
        ({"activation_type": "sometimes"}, "activation_type"),
        ({"first_name": ""}, "first_name"),
        ({"email": "not-an-email"}, "email"),
        ({"phone": "bad"}, "phone"),
        (
            {
                "activation_type": "temporary",
                "start_at": "2026-08-16T08:00:00",
                "end_at": "2026-08-16T09:00:00+00:00",
            },
            "timezone",
        ),
    ],
)
def test_identity_contact_and_timestamp_validation(
    values: dict[str, Any], message: str
) -> None:
    valid = {
        "activation_type": "permanent",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
    }
    valid.update(values)
    with pytest.raises(AccessValidationError, match=message):
        validate_create_values(valid, {})


def test_temporary_and_recurring_live_window_limits() -> None:
    temporary = {
        "activation_type": "temporary",
        "first_name": "A",
        "last_name": "B",
        "email": "a@example.com",
        "start_at": "2026-08-16T08:00:00Z",
        "end_at": "2026-08-18T08:00:01Z",
    }
    with pytest.raises(AccessValidationError, match="temporary access window"):
        validate_create_values(temporary, {"max_temporary_days": 2})

    recurring = {
        "activation_type": "recurring",
        "first_name": "A",
        "last_name": "B",
        "email": "a@example.com",
        "recurring_start_time": "08:00",
        "recurring_end_time": "12:00",
        "recurring_days": ["Monday", "Tuesday", "Wednesday"],
    }
    with pytest.raises(AccessValidationError, match="weekday limit"):
        validate_create_values(recurring, {"max_recurring_days": 2})
    with pytest.raises(AccessValidationError, match="recurring access window"):
        validate_create_values(recurring, {"max_recurring_window_minutes": 120})


@pytest.mark.parametrize(
    "activation, extra",
    [
        ("permanent", {"start_at": "2026-08-16T08:00:00Z"}),
        ("temporary", {"recurring_days": ["Monday"]}),
        ("recurring", {"end_at": "2026-08-16T08:00:00Z"}),
    ],
)
def test_create_rejects_schedule_for_another_activation_type(
    activation: str, extra: dict[str, Any]
) -> None:
    values = {
        "activation_type": activation,
        "first_name": "A",
        "last_name": "B",
        "email": "a@example.com",
        **extra,
    }
    with pytest.raises(AccessValidationError, match="[Ss]chedule|timestamps"):
        validate_create_values(values, {})


def test_canonical_weekdays_reject_abbreviations() -> None:
    assert canonicalize_weekdays(["monday", "MONDAY", "Sunday"]) == [
        "Monday",
        "Sunday",
    ]
    with pytest.raises(AccessValidationError, match="full English"):
        canonicalize_weekdays(["Mon"])


def test_create_capacity_enforces_zero_permanent_and_count_limits() -> None:
    access = unit_access(guest())
    with pytest.raises(AccessValidationError, match="disabled"):
        validate_create_capacity(access, "permanent", {"max_permanent_codes": 0})
    with pytest.raises(AccessValidationError, match="guest code limit"):
        validate_create_capacity(access, "temporary", {"max_guest_codes": 1})


@pytest.mark.asyncio
async def test_create_uses_isolated_adapter_and_verified_readback() -> None:
    before = unit_access()
    created = unit_access(
        guest(
            activation_type="temporary",
            start_at="2026-08-16T08:00:00Z",
            end_at="2026-08-16T10:00:00Z",
        )
    )
    api = FakeAPI([before, created])

    response = await manager(api).async_create_guest_code(
        activation_type="temporary",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        start_at="2026-08-16T08:00:00+00:00",
        end_at="2026-08-16T10:00:00+00:00",
    )

    assert response["verified"] is True
    assert response["guest_code"]["pin"] == "004321"
    assert response["guest_code"]["provisioning_status"] == "provisioned"
    call = api.create_calls[0]
    assert call["temporary_start_at"] == "2026-08-16T08:00:00+00:00"
    assert call["temporary_end_at"] == "2026-08-16T10:00:00+00:00"
    assert "start_at" not in call
    assert "code" not in call


@pytest.mark.asyncio
async def test_create_prefers_returned_pin_over_timestamp_formatting() -> None:
    before = unit_access()
    created = unit_access(
        guest(
            activation_type="temporary",
            start_at="2026-08-16T08:00:00.000Z",
            end_at="2026-08-16T10:00:00.000Z",
        )
    )
    api = FakeAPI(
        [before, created],
        create_response={"code": "004321"},
    )

    response = await manager(api).async_create_guest_code(
        activation_type="temporary",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        start_at="2026-08-16T08:00:00+00:00",
        end_at="2026-08-16T10:00:00+00:00",
    )

    assert response["verified"] is True
    assert response["guest_code"]["pin"] == "004321"


@pytest.mark.asyncio
async def test_create_can_verify_server_response_with_pin_only() -> None:
    api = FakeAPI(
        [unit_access(), unit_access(guest())],
        create_response={"code": "004321"},
    )
    response = await manager(api).async_create_guest_code(
        activation_type="permanent",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )
    assert response["guest_code"]["pin"] == "004321"


@pytest.mark.asyncio
async def test_create_correlates_nested_response_id_without_pin() -> None:
    api = FakeAPI(
        [unit_access(), unit_access(guest())],
        create_response={"data": {"guest": {"id": 90}}},
    )
    response = await manager(api).async_create_guest_code(
        activation_type="permanent",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )
    assert response["guest_code"]["code_id"] == 9
    assert response["guest_code"]["pin"] == "004321"


@pytest.mark.asyncio
async def test_create_correlates_unique_new_code_when_response_is_empty() -> None:
    existing = guest(code=pin_code(code_id=8, pin="1111"), first_name="Old")
    created = guest()
    api = FakeAPI(
        [unit_access(existing), unit_access(existing, created)],
        create_response={},
    )
    response = await manager(api).async_create_guest_code(
        activation_type="permanent",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )
    assert response["guest_code"]["code_id"] == 9


@pytest.mark.asyncio
async def test_create_verification_retries_without_blocking_event_loop() -> None:
    pending = unit_access()
    created = unit_access(guest())
    api = FakeAPI([unit_access(), pending, created])
    sleep_calls: list[float] = []

    async def async_no_wait(delay: float) -> None:
        sleep_calls.append(delay)

    access = SmartRentAccessManager(
        api,
        LOCK_ID,
        verification_timeout=1,
        verification_interval=0.01,
        sleep=async_no_wait,
    )
    response = await access.async_create_guest_code(
        activation_type="permanent",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )

    assert response["verified"] is True
    assert sleep_calls
    assert api.get_calls == [UNIT_ID, UNIT_ID, UNIT_ID]


@pytest.mark.asyncio
async def test_create_timeout_says_accepted_not_verified_without_secrets() -> None:
    pin = "004321"
    contact = "private@example.com"
    api = FakeAPI(
        [unit_access(), unit_access()],
        create_response={"id": 9, "code": pin},
    )

    with pytest.raises(AccessAcceptedNotVerifiedError) as error:
        await manager(api).async_create_guest_code(
            activation_type="permanent",
            first_name="Private",
            last_name="Person",
            email=contact,
        )

    rendered = str(error.value)
    assert "accepted" in rendered
    assert "verified" in rendered
    assert pin not in rendered
    assert contact not in rendered


@pytest.mark.asyncio
async def test_update_preserves_omitted_fields_routes_ids_and_returns_no_pin() -> None:
    before = unit_access(guest())
    after = unit_access(guest(first_name="Grace"))
    api = FakeAPI([before, after])

    response = await manager(api).async_update_guest_code(9, first_name="Grace")

    assert response["verified"] is True
    assert "pin" not in repr(response)
    call = api.update_calls[0]
    assert call["hub_id"] == HUB_ID
    assert call["device_id"] == LOCK_ID
    assert call["code_id"] == 9
    assert call["last_name"] == "Lovelace"
    assert call["email"] == "ada@example.com"


@pytest.mark.asyncio
async def test_update_verifies_when_smartrent_truncates_fractional_seconds() -> None:
    before = unit_access(
        guest(
            activation_type="temporary",
            start_at="2026-08-16T08:00:00Z",
            end_at="2026-08-16T10:00:00Z",
        )
    )
    after = unit_access(
        guest(
            activation_type="temporary",
            start_at="2026-08-16T08:00:00Z",
            end_at="2026-08-16T11:00:00Z",
        )
    )
    api = FakeAPI([before, after])

    response = await manager(api).async_update_guest_code(
        9,
        end_at="2026-08-16T11:00:00.750000+00:00",
    )

    assert response["verified"] is True


@pytest.mark.asyncio
async def test_update_without_readable_contact_is_rejected_before_call() -> None:
    api = FakeAPI([unit_access(guest(email=None, phone=None))])

    with pytest.raises(AccessValidationError, match="contact could not be read"):
        await manager(api).async_update_guest_code(9, first_name="Grace")

    assert api.update_calls == []


@pytest.mark.asyncio
async def test_update_verification_requires_requested_schedule() -> None:
    before = unit_access(guest())
    unchanged = unit_access(guest())
    api = FakeAPI([before, unchanged])

    with pytest.raises(AccessAcceptedNotVerifiedError, match="accepted"):
        await manager(api).async_update_guest_code(
            9,
            activation_type="recurring",
            recurring_start_time="08:00",
            recurring_end_time="10:00",
            recurring_days=["Monday"],
        )


@pytest.mark.asyncio
async def test_delete_verifies_absence_and_returns_no_pin() -> None:
    api = FakeAPI([unit_access(guest()), unit_access()])

    response = await manager(api).async_delete_guest_code(9)

    assert response == {
        "verified": True,
        "deleted": True,
        "code_id": 9,
        "device_id": LOCK_ID,
    }
    assert api.delete_calls == [{"hub_id": HUB_ID, "device_id": LOCK_ID, "code_id": 9}]


@pytest.mark.asyncio
async def test_delete_timeout_does_not_report_success() -> None:
    unchanged = unit_access(guest())
    api = FakeAPI([unchanged, unchanged])

    with pytest.raises(AccessAcceptedNotVerifiedError, match="could not be verified"):
        await manager(api).async_delete_guest_code(9)


def test_resident_id_can_never_be_selected_for_mutation() -> None:
    access = unit_access()
    with pytest.raises(AccessValidationError, match="No guest code"):
        find_guest_code(access, LOCK_ID, 777)


@pytest.mark.asyncio
async def test_resident_delete_is_rejected_before_any_mutation_call() -> None:
    api = FakeAPI([unit_access()])
    with pytest.raises(AccessValidationError, match="No guest code"):
        await manager(api).async_delete_guest_code(777)
    assert api.delete_calls == []


def test_guest_code_on_unrelated_lock_is_rejected() -> None:
    access = unit_access(guest(code=pin_code(device_id=999)), primary_device_id=1000)
    with pytest.raises(AccessValidationError, match="does not belong"):
        find_guest_code(access, LOCK_ID, 9)


def test_primary_device_guest_code_is_allowed_and_routed() -> None:
    access = unit_access(guest(code=pin_code(device_id=1000)), primary_device_id=1000)
    code = find_guest_code(access, LOCK_ID, 9)
    assert code["device_id"] == 1000


@pytest.mark.asyncio
async def test_upstream_errors_are_sanitized() -> None:
    pin = "004321"
    contact = "private@example.com"
    api = FakeAPI([unit_access()])
    api.create_error = RuntimeError(f"PIN {pin} belongs to {contact}")

    with pytest.raises(AccessOperationError) as error:
        await manager(api).async_create_guest_code(
            activation_type="permanent",
            first_name="Private",
            last_name="Person",
            email=contact,
        )

    rendered = str(error.value)
    assert pin not in rendered
    assert contact not in rendered
    assert "payload" not in rendered.lower()
