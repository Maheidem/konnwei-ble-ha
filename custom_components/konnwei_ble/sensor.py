"""Sensor entities for KONNWEI BLE Battery Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    KEY_CCA,
    KEY_CHARGE,
    KEY_HEALTH,
    KEY_RESISTANCE,
    KEY_STATUS,
    KEY_VOLTAGE,
)
from .coordinator import KonnweiCoordinator

BATTERY_STATUS_MAP = {
    0: "unknown",
    1: "good",
    2: "fair",
    3: "low",
    255: "error",
}


@dataclass(frozen=True, kw_only=True)
class KonnweiSensorDescription(SensorEntityDescription):
    """Describe a KONNWEI sensor."""

    value_fn: Any = None  # callable(coordinator.data) -> value


SENSOR_DESCRIPTIONS: tuple[KonnweiSensorDescription, ...] = (
    KonnweiSensorDescription(
        key=KEY_VOLTAGE,
        translation_key="voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    KonnweiSensorDescription(
        key=KEY_CCA,
        translation_key="cca",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-dc",
    ),
    KonnweiSensorDescription(
        key=KEY_RESISTANCE,
        translation_key="resistance",
        native_unit_of_measurement="m\u03a9",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:resistor",
        suggested_display_precision=2,
    ),
    KonnweiSensorDescription(
        key=KEY_HEALTH,
        translation_key="health",
        native_unit_of_measurement=PERCENTAGE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:heart-pulse",
    ),
    KonnweiSensorDescription(
        key=KEY_CHARGE,
        translation_key="charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KonnweiSensorDescription(
        key=KEY_STATUS,
        translation_key="battery_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(BATTERY_STATUS_MAP.values()),
        value_fn=lambda data: BATTERY_STATUS_MAP.get(
            data.get(KEY_STATUS, 0), "unknown"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KONNWEI BLE sensors from a config entry."""
    coordinator: KonnweiCoordinator = hass.data[DOMAIN][entry.entry_id]
    address = entry.data[CONF_ADDRESS]

    async_add_entities(
        KonnweiSensor(coordinator, description, address)
        for description in SENSOR_DESCRIPTIONS
    )


class KonnweiSensor(CoordinatorEntity[KonnweiCoordinator], SensorEntity):
    """A KONNWEI BLE battery monitor sensor."""

    entity_description: KonnweiSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KonnweiCoordinator,
        description: KonnweiSensorDescription,
        address: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name="KONNWEI Battery Monitor",
            manufacturer="KONNWEI",
            model="BLE Battery Monitor",
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None

        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(self.coordinator.data)

        return self.coordinator.data.get(self.entity_description.key)
