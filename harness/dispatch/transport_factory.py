"""
Transport factory — reads config/dispatch.yaml and returns the active transport module.

Switching between ROS 2 and MAVLink transports requires only changing
config/dispatch.yaml; no code changes outside this file.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_TRANSPORT = "ros2"
_DEFAULT_CONFIG_PATH = "config/dispatch.yaml"


def get_transport(config_path: str = _DEFAULT_CONFIG_PATH):
    """Return the dispatch transport module selected by config/dispatch.yaml.

    The returned module exposes dispatch_val() and build_val_from_mig().
    Falls back to 'ros2' if the config file is absent.
    """
    transport = _DEFAULT_TRANSPORT

    config_file = Path(config_path)
    if config_file.exists():
        with config_file.open() as f:
            config = yaml.safe_load(f) or {}
        transport = config.get("transport", _DEFAULT_TRANSPORT)
    else:
        logger.warning(
            f"[factory] {config_path} not found; defaulting to '{_DEFAULT_TRANSPORT}'"
        )

    logger.info(f"[factory] Active dispatch transport: {transport}")

    registry = {
        "ros2": _load_ros2,
        "mavlink": _load_mavlink,
    }

    loader = registry.get(transport)
    if loader is None:
        raise ValueError(
            f"Unknown transport '{transport}' in {config_path}. "
            f"Valid options: {list(registry)}"
        )

    return loader()


def _load_ros2():
    from harness.dispatch import ros2_transport
    return ros2_transport


def _load_mavlink():
    from harness.dispatch import mavlink_transport
    return mavlink_transport
