import json

import pytest

from airchinstall.probes import ProbeRegistry, parse_lsblk


def test_lsblk_probe_returns_only_safe_disk_identity_fields():
    payload = json.dumps(
        {
            "blockdevices": [
                {
                    "name": "vda",
                    "path": "/dev/vda",
                    "size": "32G",
                    "type": "disk",
                    "model": "QEMU HARDDISK",
                    "serial": "secret-host-serial",
                    "rm": False,
                    "children": [{"name": "vda1", "path": "/dev/vda1", "type": "part"}],
                },
                {"name": "sr0", "path": "/dev/sr0", "size": "1.5G", "type": "rom"},
            ]
        }
    )

    assert parse_lsblk(payload) == [
        {
            "path": "/dev/vda",
            "size": "32G",
            "model": "QEMU HARDDISK",
            "removable": False,
        }
    ]


def test_probe_registry_rejects_unknown_probe_names():
    registry = ProbeRegistry({"uefi": list})

    try:
        registry.collect("generated-shell-command")
    except ValueError as error:
        assert "unknown probe" in str(error)
    else:
        raise AssertionError("unknown probes must be rejected")


def test_probe_registry_validates_catalog_registrations():
    registry = ProbeRegistry({"uefi": list})

    with pytest.raises(ValueError, match="unregistered probes"):
        registry.require_registered(("uefi", "network", "disks"))
