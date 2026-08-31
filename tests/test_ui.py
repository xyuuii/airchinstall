from pathlib import Path

import pytest
from rich.cells import cell_len
from textual.widgets import Static

from airchinstall.catalog import OperationCatalog
from airchinstall.ui import (
    MentorApp,
    WikiApp,
    layout_mode,
    local_wiki_version,
    render_mentor,
    render_wiki,
)


def snapshot():
    return {
        "facts": {"boot.uefi": True},
        "goal": {"id": "goal-1", "text": "我想先了解当前环境", "status": "active"},
        "observed_operations": ["inspect-uefi"],
        "current_operation": "inspect-uefi",
        "last_observation": None,
        "active_command": None,
        "advice": {
            "summary": "可以继续检查网络或磁盘。",
            "options": [
                {"operation_id": "check-network", "rationale": "安装软件前确认联网"},
                {"operation_id": "list-disks", "rationale": "先识别虚拟磁盘"},
            ],
            "warnings": [],
        },
    }


def test_mentor_is_concise_and_wraps_to_cjk_cell_width():
    rendered = render_mentor(snapshot(), OperationCatalog.load_default(), width=38)

    assert "目标" in rendered
    assert "风险" in rendered
    assert "只读" in rendered
    assert "检查网络" in rendered
    assert "ping -c 3 ping.archlinux.org" in rendered
    assert "查看磁盘" in rendered
    assert "STEP" not in rendered
    assert all(cell_len(line) <= 38 for line in rendered.splitlines())


def test_mentor_details_are_hidden_until_requested():
    catalog = OperationCatalog.load_default()

    concise = render_mentor(snapshot(), catalog, width=38)
    expanded = render_mentor(snapshot(), catalog, width=38, show_details=True)

    assert "成功条件" not in concise
    assert "efivars 目录存在" in expanded
    assert "ls /sys/firmware/efi/efivars" in expanded


def test_wiki_tracks_the_current_operation_and_local_snapshot():
    rendered = render_wiki(
        snapshot(),
        OperationCatalog.load_default(),
        width=38,
        snapshot_version="20260801-1",
    )

    assert "Installation guide" in rendered
    assert "Verify the boot mode" in rendered
    assert "本地快照" in rendered
    assert "20260801-1" in rendered
    assert "wiki.archlinux.org" in rendered
    assert all(cell_len(line) <= 38 for line in rendered.splitlines())


def test_local_wiki_version_reads_pacman_metadata(tmp_path):
    package = tmp_path / "arch-wiki-lite-20260801-1"
    package.mkdir()
    (package / "desc").write_text("%NAME%\narch-wiki-lite\n\n%VERSION%\n20260801-1\n")

    assert local_wiki_version(tmp_path) == "20260801-1"


def test_running_bash_command_updates_context_before_it_finishes():
    running = snapshot()
    running["current_operation"] = None
    running["active_command"] = {
        "command_id": "cmd-running",
        "command": "ping -c 3 ping.archlinux.org",
        "cwd": "/root",
    }

    assert "确认网络连通" in render_mentor(running, OperationCatalog.load_default(), width=38)
    assert "Connect to the internet" in render_wiki(
        running, OperationCatalog.load_default(), width=38
    )


def test_finished_unknown_command_is_explanation_only_not_current_recommendation():
    unknown = snapshot()
    unknown["current_operation"] = None
    unknown["last_observation"] = {
        "command_id": "cmd-unknown",
        "command": "uname -a",
        "cwd": "/root",
        "exit_code": 0,
    }

    rendered = render_mentor(unknown, OperationCatalog.load_default(), width=38)

    assert "未收录命令" in rendered
    assert "uname -a" in rendered
    assert "当前  确认网络连通" not in rendered


def test_small_terminals_use_windows_instead_of_crushing_three_panes():
    assert layout_mode(columns=120, lines=30) == "three-pane"
    assert layout_mode(columns=80, lines=24) == "compact"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "app_class, widget_id, expected, detail",
    [
        (MentorApp, "#mentor", "Airchinstall", "我想先了解当前环境"),
        (WikiApp, "#wiki", "ArchWiki", "Verify the boot mode"),
    ],
)
async def test_textual_clients_render_snapshot_at_narrow_cjk_width(
    app_class, widget_id, expected, detail
):
    app = app_class(
        Path("/unused.sock"),
        OperationCatalog.load_default(),
        initial_snapshot=snapshot(),
        connect=False,
    )

    async with app.run_test(size=(42, 28)) as pilot:
        await pilot.pause()
        screenshot = app.export_screenshot()
        content = str(app.query_one(widget_id, Static).content)

    assert expected in screenshot
    assert detail in content
