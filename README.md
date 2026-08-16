# SmartRent Home Assistant Component

[![GitHub Release][releases-shield]][releases]
[![HACS Shield][hacs-shield]](https://github.com/hacs/integration)
[![GitHub][license-shield]](LICENSE.txt)
[![Code style: black][black-shield]](https://github.com/psf/black)
[![Downloads][downloads-shield]][releases]

> [!WARNING]
> I moved out of my apartment and don't have a way to access SmartRent anymore. I will add bug fix PRs as ppl contribute them

This is a basic Homeassistant component to support SmartRent Locks, Thermostats, Leak Sensors, Motion Sensors, and Light Switches. This component uses the `smartrent-py` library that can be found [here](https://github.com/ZacheryThomas/smartrent-py)!

Feel free to ⭐️ this repo to get notified about the latest features!

![example screenshot](dashboard_screenshot.png)

## Installation

You can either install this integration as an HACS custom component or install it mannually
### Installing with HACS
* Go to the `HACS` tab and select `Integrations`
* Click on `Explore & Download Repositories`
* Search for `SmartRent` and then download the repo by clicking `Download this repository with HACS`
* *You will then have to restart your Home Assistant instance*
* After that, you can add the Integration as usual by going to `Configuraton > Devices & Services > Add Integration`


### Installing manually

#### Moving custom component to right directory
```
# How your HA config directory should look

config
└── ...
└── configuration.yaml
└── secrets.yaml
└── custom_components
    └── smartrent
        └── climate.py
        └── lock.py
        └── manifest.json
        └── ...
```

You have to move all content in the `custom_components/smartrent` directory to the same location in Home Assistant. If a `custom_components` directory does not already exist in your Home Assistant instance, you will have to make one. You can learn more [here](https://developers.home-assistant.io/docs/creating_integration_file_structure#where-home-assistant-looks-for-integrations).

After all of those are in place, you can restart your Home Assistant instance and the component should load.

#### Start the integration
You should be able to now load the integration. This can be done by going to `Configuraton > Devices & Services > Add Integration`

You should be able to search for SmartRent and then enter your email and password in the popup.

## Guest access codes

SmartRent lock entities provide four response-only actions:

- `smartrent.get_guest_codes` returns guest PIN codes and the unit's live access
  policy limits.
- `smartrent.create_guest_code` asks SmartRent to generate a permanent,
  temporary, or recurring guest PIN.
- `smartrent.update_guest_code` updates guest metadata or a schedule by the
  `code_id` returned by the get/create actions.
- `smartrent.delete_guest_code` deletes a guest code by `code_id`.

All actions must target a SmartRent `lock` entity. Unit, hub, and device IDs are
resolved automatically. Accounts with multiple units fail safely if the target
lock cannot be matched unambiguously. Update and delete operate only on fresh
`guests[].pin_codes` data; they cannot mutate resident, mobile, or fob
credentials. These actions manage credentials only and never unlock or actuate
the lock.

Create does not accept a custom PIN: SmartRent generates it. Every mutation is
checked with a fresh read-back before the action reports success. An accepted
mutation that cannot be verified before the bounded timeout raises an error
instead of reporting success. Omitted update fields preserve their current
values.

> [!CAUTION]
> Guest PINs are secrets. They are never added to entity state or attributes
> and update/delete responses do not include them. However,
> `get_guest_codes` and `create_guest_code` intentionally return PINs in their
> explicit action responses. Home Assistant automation traces, action-response
> variables, debug tooling, and notifications/templates that consume those
> responses can therefore retain or expose sensitive PINs. Restrict trace and
> log access, avoid logging the response, and do not persist it longer than
> necessary.

### Guest PIN dashboard card

`www/smartrent-guest-pins-card.js` provides the
`custom:smartrent-guest-pins-card` Lovelace card. It lists verified guest PINs
and can create temporary or recurring
codes, copy a generated PIN, and delete a code. The card calls the
response-enabled SmartRent actions directly; it does not put PINs into entity
state or dashboard configuration.

Install the module under `/config/www/`, register it as a Lovelace module
resource, and add it to a dashboard with the SmartRent lock entity to manage:

```yaml
type: custom:smartrent-guest-pins-card
entity: lock.front_door
title: Guest PINs
```

Restrict the card's view to trusted Home Assistant users because viewing the
card reveals active guest PINs in that browser session.

Until the related `smartrent-py` changes are released, the integration manifest
points to the exact tested client commit. Replace that temporary Git dependency
with the corresponding published release before releasing this integration.

[license-shield]: https://img.shields.io/github/license/zacherythomas/homeassistant-smartrent.svg?style=for-the-badge
[hacs-shield]: https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge
[black-shield]: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge

[releases-shield]: https://img.shields.io/github/release/zacherythomas/homeassistant-smartrent.svg?style=for-the-badge
[releases]: https://github.com/zacherythomas/homeassistant-smartrent/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/zacherythomas/homeassistant-smartrent.svg?style=for-the-badge
[commits]: https://github.com/zacherythomas/homeassistant-smartrent/commits/master
[downloads-shield]: https://img.shields.io/github/downloads/zacherythomas/homeassistant-smartrent/total?color=green&style=for-the-badge
