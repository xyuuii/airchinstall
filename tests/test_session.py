import pytest

from airchinstall.catalog import OperationCatalog
from airchinstall.domain import (
    Advice,
    AdviceOption,
    AssistantSession,
    Fact,
    Observation,
)


def observation(command: str) -> Observation:
    return Observation(command_id=command, command=command, cwd="/root", exit_code=0)


def facts_for(command: str) -> list[Fact]:
    if command.startswith("ls /sys/firmware"):
        return [Fact(key="boot.uefi", value=True, source="uefi")]
    if command.startswith("ping"):
        return [Fact(key="network.online", value=True, source="network")]
    return [Fact(key="disks.inventory", value=["/dev/vda"], source="disks")]


def run_order(commands: list[str]):
    session = AssistantSession(OperationCatalog.load_default())
    for command in commands:
        session.observe(observation(command), facts_for(command))
    return session.snapshot()


def test_independent_observations_converge_to_the_same_facts():
    commands = [
        "ls /sys/firmware/efi/efivars",
        "ping -c 3 ping.archlinux.org",
        "lsblk -J -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS",
    ]

    forward = run_order(commands)
    reverse = run_order(list(reversed(commands)))

    assert (
        forward.facts
        == reverse.facts
        == {
            "boot.uefi": True,
            "network.online": True,
            "disks.inventory": ["/dev/vda"],
        }
    )
    assert set(forward.observed_operations) == {
        "inspect-uefi",
        "check-network",
        "list-disks",
    }


def test_goal_is_free_text_and_does_not_create_a_fixed_plan():
    session = AssistantSession(OperationCatalog.load_default())

    snapshot = session.set_goal("我想先确认磁盘，再决定装 KDE 还是 GNOME")

    assert snapshot.goal.text == "我想先确认磁盘，再决定装 KDE 还是 GNOME"
    assert not hasattr(snapshot, "step_index")


def test_advice_rejects_operations_outside_the_trusted_catalog():
    session = AssistantSession(OperationCatalog.load_default())

    with pytest.raises(ValueError, match="unknown operation"):
        session.apply_advice(
            Advice(
                summary="擦除磁盘",
                options=[AdviceOption(operation_id="generated-rm-rf", rationale="快")],
            )
        )


def test_fact_source_must_match_the_catalog_probe():
    session = AssistantSession(OperationCatalog.load_default())

    snapshot = session.observe(
        observation("lsblk -J"),
        [Fact(key="disks.inventory", value=["/dev/evil"], source="generated-shell")],
    )

    assert snapshot.facts == {}


def test_operation_prerequisites_use_verified_fact_keys():
    original = OperationCatalog.load_default().require("list-disks")
    dependent = original.model_copy(
        update={"id": "list-disks-after-network", "prerequisites": {"network.online": True}}
    )
    catalog = OperationCatalog((dependent,))

    assert catalog.available({}) == ()
    assert catalog.available({"network.online": False}) == ()
    assert catalog.available({"network.online": True}) == (dependent,)


def test_verified_operations_leave_the_next_advice_choices():
    session = AssistantSession(OperationCatalog.load_default())

    session.observe(
        observation("ping -c 3 ping.archlinux.org"),
        [Fact(key="network.online", value=True, source="network")],
    )

    assert {operation.id for operation in session.available_operations()} == {
        "inspect-uefi",
        "list-disks",
    }
