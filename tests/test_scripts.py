import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_shell_scripts_parse():
    subprocess.run(
        [
            "bash",
            "-n",
            ROOT / "scripts" / "bootstrap.sh",
            ROOT / "scripts" / "parallels-arm-mvp.sh",
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
    assert "archlinuxarm-keyring" in bootstrap
    assert "aarch64:parallels" in bootstrap
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


def test_parallels_arm_dry_run_isolated_from_host_data():
    completed = subprocess.run(
        [ROOT / "scripts" / "parallels-arm-mvp.sh", "--dry-run", "/tmp/archboot.iso"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "UEFI ARM64 Archboot AArch64 ISO" in completed.stdout
    assert "Host disks, folders, clipboard, and cloud drives: not shared" in completed.stdout


def test_parallels_arm_launcher_creates_an_isolated_vm(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    iso = tmp_path / "archboot.iso"
    iso.touch()
    (tmp_path / "archboot.iso.sig").touch()
    log = tmp_path / "prlctl.log"
    (commands / "uname").write_text(
        "#!/bin/sh\ncase $1 in -s) echo Darwin;; -m) echo arm64;; esac\n"
    )
    (commands / "prlctl").write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$AIRCHINSTALL_PRLCTL_LOG\"\n"
        "if [ \"$1\" = list ]; then echo NAME; fi\n"
    )
    (commands / "gpg").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in *'--with-colons --fingerprint'*)\n"
        "  printf 'fpr:::::::::5B7E3FB71B7F10329A1C03AB771DF6627EDF681F:\\n';; esac\n"
    )
    for command in commands.iterdir():
        command.chmod(0o755)

    environment = {
        **os.environ,
        "PATH": f"{commands}:/usr/bin:/bin",
        "AIRCHINSTALL_PRLCTL_LOG": str(log),
    }
    completed = subprocess.run(
        [ROOT / "scripts" / "parallels-arm-mvp.sh", iso],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr

    calls = log.read_text()
    assert "create airchinstall-arm --ostype linux --distribution linux --no-hdd" in calls
    assert "--device-add hdd --size 32768 --iface sata --type expand" in calls
    assert f"--device-set cdrom0 --image {iso} --connect" in calls
    assert "--device-bootorder cdrom0 hdd0" in calls
    assert "--shf-host-defined off" in calls
    assert "--shared-clipboard off" in calls
    assert "--sh-app-host-to-guest off" in calls
    assert calls.index("--shf-host-defined off") < calls.index("--device-set cdrom0")


def test_parallels_arm_launcher_refuses_an_unsigned_iso(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    iso = tmp_path / "archboot.iso"
    iso.touch()
    (commands / "uname").write_text(
        "#!/bin/sh\ncase $1 in -s) echo Darwin;; -m) echo arm64;; esac\n"
    )
    (commands / "gpg").write_text("#!/bin/sh\n")
    (commands / "prlctl").write_text("#!/bin/sh\n")
    for command in commands.iterdir():
        command.chmod(0o755)

    environment = {**os.environ, "PATH": f"{commands}:/usr/bin:/bin"}
    completed = subprocess.run(
        [ROOT / "scripts" / "parallels-arm-mvp.sh", iso],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 1
    assert f"Archboot signature not found: {iso}.sig" in completed.stderr
