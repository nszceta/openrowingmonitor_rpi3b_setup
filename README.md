# Open Rowing Monitor on Raspberry Pi 3B (Armbian) — pyinfra setup

## 1. Overview

This repository contains a pyinfra setup that installs [Open Rowing Monitor](https://github.com/JaapvanEkris/openrowingmonitor) v0.9.7 (main branch) on a Raspberry Pi 3B running Armbian 26.5.1 minimal ("resolute", Ubuntu 26.04 base), for a Concept2 RowErg with an optocoupler on GPIO 17. The Pi serves the web UI on port 80 and also runs a minimal Surf/Matchbox Xorg kiosk on its HDMI display; metrics are broadcast over BLE (FTMS) to rowing apps.

## 2. Manual steps (done once)

These steps were performed by hand on the Pi. They are documented here so a fresh SD card can be reproduced:

1. Download the Armbian 26.5.1 minimal image for Raspberry Pi 3B (arm64) from [armbian.com](https://www.armbian.com/rpi3b/), and verify the downloaded image against the published checksum.
2. Flash the image to a microSD card with balenaEtcher, or with dd:

   ```bash
   sudo dd bs=4M if=<image>.img of=/dev/<sdX> conv=fsync status=progress
   ```

3. Insert the SD card, boot the Pi, and attach it to the network (ethernet, or wifi via `armbian-config`).
4. On first boot, log in as `root` / `1234` — Armbian forces a new root password — and run through the first-login wizard: set the root password and create the user `rpi4b` with password `rpi4b` (the wizard grants sudo by default).
5. Confirm SSH from your workstation:

   ```bash
   ssh rpi4b@192.168.47.116
   ```

   The static IP 192.168.47.116 is reserved on the router (or configured statically via `armbian-config`).

## 3. Requirements on the workstation

- Python 3.10 or newer.
- [uv](https://docs.astral.sh/uv/) — everything else (pyinfra) is managed through `pyproject.toml` in this directory:

  ```toml
  dependencies = ["pyinfra>=3,<4"]
  ```

  `uv run` creates the environment on first use; no global install needed.
- pyinfra 3 dropped YAML inventory files, so the local configuration lives in the Python file `inventory.py` (same content as the old `inventory.yml`: SSH access, sudo password, and install settings).

## 4. Deploy

Run from this directory:

```bash
uv run pyinfra inventory.py deploy.py
```

Notes:

- The first run takes roughly 10–20 minutes on a Pi 3B: native modules (`pigpio`, `hci-socket`) are compiled from source and the app is built with rollup.
- Re-running is safe: the deploy is idempotent, and only missing steps execute (clone, `npm ci`, and build are guarded; the service is restarted each run by design).
- SSH password and sudo password are taken from `inventory.py` (`ssh_password: rpi4b`, `_sudo_password: rpi4b`); the deploy runs as `rpi4b` with `_sudo=True` where needed.
- In a non-interactive shell, add `-y` so pyinfra applies detected changes without the confirmation prompt (without it, an EOF aborts the run before anything is applied):

  ```bash
  uv run pyinfra inventory.py deploy.py -y
  ```

What the deploy does: installs system packages (bluetooth stack, git, build toolchain, and the minimal Xorg/Surf/Matchbox HDMI kiosk), builds the pigpio C library from source (Ubuntu resolute dropped the apt package; built with `-std=gnu89` for GCC 14+), clones Open Rowing Monitor to `/opt/openrowingmonitor`, runs `npm ci` and `npm run build`, prunes dev dependencies with `npm prune --omit=dev`, installs the systemd units (`openrowingmonitor`, `openrowingmonitor-display`, `cpufreq-performance`), disables triggerhappy/avahi/nfs-client per the official performance guide, renames the hostname to `rowingmonitor`, and unblocks bluetooth.

## 5. Verify

- The deploy ends with a curl smoke check against the web UI.
- Open http://192.168.47.116/ in a browser — you should see the live metrics dashboard. The same dashboard starts full-screen on the Pi's HDMI display through `openrowingmonitor-display.service`.
- Check the service:

  ```bash
  ssh rpi4b@192.168.47.116
  systemctl status openrowingmonitor
  ```

- Follow the logs:

  ```bash
  journalctl -u openrowingmonitor -f
  ```

## 6. Configuration

Configuration lives in `/opt/openrowingmonitor/config/config.js`. The deploy creates it only once (if it does not exist), so your edits survive later deploys and updates.

```bash
sudo nano /opt/openrowingmonitor/config/config.js
```

- **Rower profile**: `Concept2_RowErg` is pre-set (6 impulses/rev; covers Concept2 Model D/E/RowErg).
- **Bluetooth**: `bluetoothMode` defaults to `'FTMS'`; switch to `'PM5'` if an app requires the Concept2 PM5 app emulation (note: PM5 mode is not functionally complete per upstream).
- **Heart rate**: `heartRateMode` `'BLE'` enables a BLE heart-rate strap.
- **Priorities**: `gpioPriority -5` and `appPriority -2` are pre-set — safe because the kernel is PREEMPT (the official guide allows up to -7/-5). On non-PREEMPT kernels, reduce both to `-1`/`0`.

## 7. Performance notes

What was optimized and why:

- **Minimal HDMI kiosk**: Xorg, Matchbox, and Surf display the port-80 UI full-screen without installing a desktop environment. Surf runs with JavaScript and kiosk mode enabled; the client disables X screen blanking and DPMS.
- **Systemd unit with direct `node`**: no pm2 or npm wrapper — the unit runs `node app/server.js` directly under systemd (`ExecStart=/usr/bin/node app/server.js`) with restart on failure.
- **Slim node_modules**: `npm prune --omit=dev` after the rollup build removes dev dependencies (typescript, rollup, etc.) from the installed tree.
- **Performance CPU governor**: applied via a oneshot systemd unit (`cpufreq-performance.service`) instead of installing the cpufrequtils package.
- **Thread priorities**: the root service runs GPIO at `-5` and the app at `-2` on a PREEMPT kernel, which keeps sensor sampling and web serving responsive.
- **Background services disabled**: triggerhappy, avahi-daemon, and nfs-client are disabled per the official performance guide: https://github.com/JaapvanEkris/openrowingmonitor/blob/main/docs/Improving_Raspberry_Performance.md
- **Shallow clone**: `git clone --depth 1` keeps the checkout small.

**Optional, NOT enabled by default** (security risk): `mitigations=off`. To enable it on Armbian, add `extraargs="mitigations=off"` to `/boot/armbianEnv.txt` and reboot.

## 8. Hardware

The Concept2 RowErg flywheel sensor outputs a 15 V sinusoid — this must NOT go to the Pi's GPIO pins. Use an optocoupler to isolate it (the official guide uses an Al-Zard DST-1R4P-P with 2.5 mm jacks and PM5 passthrough), wired to GPIO 17.

The JS service enables the internal pull-up on GPIO 17 itself, so no `/boot` config line is needed on Armbian.

Full guide: https://github.com/JaapvanEkris/openrowingmonitor/blob/main/docs/hardware_setup_Concept2_RowErg.md

## 9. Updating

```bash
sudo bash -c 'cd /opt/openrowingmonitor && git pull && npm ci && npm run build'
sudo systemctl restart openrowingmonitor
```

`npm ci` restores the dev dependencies needed for the build; run `sudo npm prune --omit=dev` afterwards if you want to keep the slim node_modules tree.

## 10. Troubleshooting

- **`bluetoothctl` says "No default controller available"**: expected while Open Rowing Monitor runs. ORM drives the BCM43438 directly through its own BLE host (`node-ble-host`, HCI user channel) — `bluetoothd` is not in the data path, and the mgmt index intentionally excludes user-channel devices. Do not restart bluetoothd or "fix" this; the radio is unblocked at boot by `rfkill-unblock.service`.
- **BLE broadcast check**: rowing apps (EXR, ErgZone, Kinomap) discover the rower as "OpenRowingMonitor" (FTMS profile); the BLE stack logs no errors at startup.
- **Service failing**: `journalctl -u openrowingmonitor -e` shows the recent error output.
- **Bluetooth not broadcasting**: check `rfkill list`, then `sudo rfkill unblock bluetooth`, `sudo systemctl restart bluetooth`, and verify `hciconfig -a` shows `hci0` present.
- **Web UI down but service active**: check `ss -tlnp | grep :80` — the app serves on port 80.
- **HDMI display failing or black**: check `systemctl status openrowingmonitor-display`, `journalctl -u openrowingmonitor-display -e`, and `systemctl status getty@tty1`; the kiosk owns `/dev/tty1` and disables DPMS screen blanking.
- **Boot hangs right after login (no kiosk, no web UI, SSH still works)**: `systemctl list-jobs` shows `multi-user.target` and both ORM units stuck `waiting`, and `journalctl -b` reports `Found ordering cycle: openrowingmonitor-display.service/start after openrowingmonitor.service/start after multi-user.target/start`. The display unit is pulled in by `multi-user.target` and ordered `After=openrowingmonitor.service`, while `openrowingmonitor.service` used to declare `After=multi-user.target` — that closes a cycle, and systemd leaves the whole boot transaction pending forever. Fix: `openrowingmonitor.service` must NOT use `After=multi-user.target` (its `WantedBy=multi-user.target` already orders it before the target); remove the line, `systemctl daemon-reload`, then `systemctl start openrowingmonitor.service` unblocks the queued boot jobs.
- **pigpio errors**: check `which pigpiod` and `/usr/local/lib/libpigpio.so` — the deploy builds joan2937/pigpio from source (Ubuntu resolute no longer ships the pigpio package) with `-std=gnu89` for GCC 14+ compatibility. The npm `pigpio` addon only builds when `pigpiod` is on PATH.
- **Permission errors**: the service runs as root by design — port 80, the HCI socket, GPIO access, and thread priorities all require it.
