# SmartRent Home Assistant Component

A basic Homeassistant component to support SmartRent Locks and Thermostats. This component uses the `smartrent.py` library that can be found [here](https://github.com/ZacheryThomas/smartrent.py)!

## Basic Setup

Quick and dirty:
```
└── ...
└── configuration.yaml
└── secrects.yaml
└── custom_components
    └── smartrent
        └── climate.py
        └── lock.py
        └── manifest.json
        └── ...
```

You have to move all content in the `custom_components/smartrent` directory to the same location in Home Assistant. If a `custom_components` directory does not already exist in your Home Assistant instance, you will have to make one.

You will also have to update your homeassistant config with the credentials you will use to connect to SmartRent.

```yaml
...
scene: !include scenes.yaml

lock:
  - platform: smartrent
    username: 'example@gmail.com'
    password: 'password'

climate:
  - platform: smartrent
    username: 'example@gmail.com'
    password: 'password'
```

After all of those are in place, you can restart your Home Assistant server and the component should load.
