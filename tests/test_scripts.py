import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_shell_scripts_parse():
    subprocess.run(
        [
            "bash",
            "-n",
            ROOT / "scripts" / "bootstrap.sh",
            ROOT / "scripts" / "qemu-mvp.sh",
        ],
        check=True,
    )
    subprocess.run(
        ["bash", "-n", ROOT / "src" / "airchinstall" / "data" / "airchinstall.bash"],
        check=True,
    )


def test_bootstrap_dry_run_is_noninteractive_and_describes_volatile_install():
    completed = subprocess.run(
        [ROOT / "scripts" / "bootstrap.sh", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "python-textual" in completed.stdout
    assert "/run/airchinstall" in completed.stdout
    assert "real Bash" in completed.stdout
    bootstrap = (ROOT / "scripts" / "bootstrap.sh").read_text()
    assert "pacman -Syu" not in bootstrap
    assert "pacman-key --populate archlinux" in bootstrap
    assert "no-reset-env" in bootstrap
    assert "reset-env=no" not in bootstrap
    assert "stty -echo" in bootstrap
    assert "RUNTIME_DIR/bin/airchinstall" in bootstrap


def test_qemu_headless_dry_run_keeps_host_disks_detached():
    completed = subprocess.run(
        [ROOT / "scripts" / "qemu-mvp.sh", "--dry-run", "--headless", "/tmp/arch.iso"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Display: serial console" in completed.stdout
    assert "Host disks: none attached" in completed.stdout
