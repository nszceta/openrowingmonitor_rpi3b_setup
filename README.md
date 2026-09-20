# Open Rowing Monitor SBC setup (Armbian) — pyinfra

## 1. Overview

This repository contains a pyinfra setup that installs [Open Rowing Monitor](https://github.com/JaapvanEkris/openrowingmonitor) v0.9.7 (main branch) on a compatible SBC running Armbian or a Debian/Ubuntu-based equivalent (tested with Armbian 26.5.1 minimal ("resolute", Ubuntu 26.04 base)), for a Concept2 RowErg with an optocoupler on GPIO 17. The SBC serves the web UI on port 80 and also runs a minimal Surf/Matchbox Xorg kiosk on its display; metrics are broadcast over BLE (FTMS) to rowing apps.

Target compatibility (all REQUIRED except the kiosk display):

- OS with apt and systemd (Armbian or a Debian/Ubuntu-based equivalent).
- `joan2937/pigpio`-compatible GPIO support with the flywheel input exposed as GPIO 17.
- Linux HCI Bluetooth adapter (onboard or USB dongle) for the BLE broadcast.
- Optional kiosk only: Xorg-capable display output (HDMI) for the full-screen dashboard.

Boards missing any required item are not supported; no universal board support is claimed.

## 2. Manual steps (done once)

These steps were performed by hand on the SBC. They are documented here so fresh boot media can be reproduced:

1. Download the Armbian minimal image for your board from its board download page at [armbian.com](https://www.armbian.com/), and verify the downloaded image against the published checksum.
2. Flash the image to your board's boot media with balenaEtcher, or with dd:

   ```bash
   sudo dd bs=4M if=<image>.img of=/dev/<device> conv=fsync status=progress
   ```

   Replace `<device>` with your boot media device name.
3. Insert the boot media, boot the SBC, and attach it to the network (ethernet, or wifi via `armbian-config` or your image's equivalent).
4. On first boot, follow the image-provided first-boot process: set a new root password and create an admin user with sudo access.
   Update `ssh_hostname`, `ssh_user`, `ssh_password`, and `_sudo_password` in `inventory.py` to match that account.
5. Confirm SSH from your workstation (user and hostname as configured via `ssh_user` and `ssh_hostname` in `inventory.py`):

   ```bash
   ssh <ssh_user>@<ssh_hostname>
   ```

   Give the SBC a stable address (router-side reservation or a static address via your image's network tooling).

## 3. Requirements on the workstation

- Python 3.10 or newer.
- [uv](https://docs.astral.sh/uv/) — everything else (pyinfra) is managed through `pyproject.toml` in this directory:

  ```toml
  dependencies = ["pyinfra>=3,<4"]
  ```

  `uv run` creates the environment on first use; no global install needed.
- pyinfra 3 dropped YAML inventory files, so the local configuration lives in the Python file `inventory.py` (SSH access via `ssh_hostname`/`ssh_user`/`ssh_password`, sudo password via `_sudo_password`, and install settings).

## 4. Deploy

Run from this directory:

```bash
uv run pyinfra inventory.py deploy.py
```

Notes:

- The first run takes roughly 10–20 minutes on a small SBC: native modules (`pigpio`, `hci-socket`) are compiled from source and the app is built with rollup.
- Re-running is safe: the deploy is idempotent, and only missing steps execute (clone, `npm ci`, and build are guarded; the service is restarted each run by design).
- SSH password and sudo password are taken from `inventory.py` (`ssh_password`, `_sudo_password`); the deploy connects as the configured `ssh_user` and uses `_sudo=True` where needed.
- In a non-interactive shell, add `-y` so pyinfra applies detected changes without the confirmation prompt (without it, an EOF aborts the run before anything is applied):

  ```bash
  uv run pyinfra inventory.py deploy.py -y
  ```

What the deploy does: installs system packages (bluetooth stack, git, build toolchain, and the minimal Xorg/Surf/Matchbox display kiosk), builds the pigpio C library from source (Ubuntu resolute dropped the apt package; built with `-std=gnu89` for GCC 14+), clones Open Rowing Monitor to `/opt/openrowingmonitor`, runs `npm ci` and `npm run build`, prunes dev dependencies with `npm prune --omit=dev`, installs the systemd units (`openrowingmonitor`, `openrowingmonitor-display`, `cpufreq-performance`), disables triggerhappy/avahi/nfs-client per the official performance guide, renames the hostname to `rowingmonitor`, and unblocks bluetooth.

## 5. Verify

- The deploy ends with a curl smoke check against the web UI.
- Open `http://<ssh_hostname>/` in a browser (same host as `ssh_hostname` in `inventory.py`) — you should see the live metrics dashboard. The same dashboard starts full-screen on the SBC's display through `openrowingmonitor-display.service`.
- Check the service:

  ```bash
  ssh <ssh_user>@<ssh_hostname>
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
- **Priorities**: `gpioPriority -5` and `appPriority -2` are pre-set for PREEMPT kernels (the official guide allows up to -7/-5). On non-PREEMPT kernels, reduce both to `-1`/`0` — check `uname -a` for a PREEMPT marker and adjust to your kernel.

## 7. Performance notes

What was optimized and why:

- **Minimal display kiosk**: Xorg, Matchbox, and Surf display the port-80 UI full-screen without installing a desktop environment. Surf runs with JavaScript and kiosk mode enabled; the client disables X screen blanking and DPMS.
- **Systemd unit with direct `node`**: no pm2 or npm wrapper — the unit runs `node app/server.js` directly under systemd (`ExecStart=/usr/bin/node app/server.js`) with restart on failure.
- **Slim node_modules**: `npm prune --omit=dev` after the rollup build removes dev dependencies (typescript, rollup, etc.) from the installed tree.
- **Performance CPU governor**: applied via a oneshot systemd unit (`cpufreq-performance.service`) instead of installing the cpufrequtils package.
- **Thread priorities**: the root service runs GPIO at `-5` and the app at `-2`, which keeps sensor sampling and web serving responsive on PREEMPT kernels.
- **Background services disabled**: triggerhappy, avahi-daemon, and nfs-client are disabled per the official performance guide: https://github.com/JaapvanEkris/openrowingmonitor/blob/main/docs/Improving_Raspberry_Performance.md
- **Shallow clone**: `git clone --depth 1` keeps the checkout small.

**Optional, NOT enabled by default** (security risk): `mitigations=off`. To enable it on Armbian-based images, add `extraargs="mitigations=off"` to `/boot/armbianEnv.txt` and reboot.

## 8. Hardware

The Concept2 RowErg flywheel sensor outputs a 15 V sinusoid — this must NOT go directly to the SBC's GPIO pins. Use an optocoupler to isolate it (the official guide uses an Al-Zard DST-1R4P-P with 2.5 mm jacks and PM5 passthrough), wired to GPIO 17.

The JS service enables the internal pull-up on GPIO 17 itself, so no boot config line is needed.

Full guide: https://github.com/JaapvanEkris/openrowingmonitor/blob/main/docs/hardware_setup_Concept2_RowErg.md

## 9. Updating

```bash
sudo bash -c 'cd /opt/openrowingmonitor && git pull && npm ci && npm run build'
sudo systemctl restart openrowingmonitor
```

`npm ci` restores the dev dependencies needed for the build; run `sudo npm prune --omit=dev` afterwards if you want to keep the slim node_modules tree.

## 10. Troubleshooting

- **`bluetoothctl` says "No default controller available"**: expected while Open Rowing Monitor runs. ORM drives the configured Bluetooth adapter directly through its own BLE host (`node-ble-host`, HCI user channel) — `bluetoothd` is not in the data path, and the mgmt index intentionally excludes user-channel devices. Do not restart bluetoothd or "fix" this; the radio is unblocked at boot by `rfkill-unblock.service`.
- **BLE broadcast check**: rowing apps (EXR, ErgZone, Kinomap) discover the rower as "OpenRowingMonitor" (FTMS profile); the BLE stack logs no errors at startup.
- **Service failing**: `journalctl -u openrowingmonitor -e` shows the recent error output.
- **Bluetooth not broadcasting**: check `rfkill list`, then `sudo rfkill unblock bluetooth`, `sudo systemctl restart bluetooth`, and verify `hciconfig -a` shows `hci0` present.
- **Web UI down but service active**: check `ss -tlnp | grep :80` — the app serves on port 80.
- **Display failing or black**: check `systemctl status openrowingmonitor-display`, `journalctl -u openrowingmonitor-display -e`, and `systemctl status getty@tty1`; the kiosk owns `/dev/tty1` and disables DPMS screen blanking.
- **Boot hangs right after login (no kiosk, no web UI, SSH still works)**: `systemctl list-jobs` shows `multi-user.target` and both ORM units stuck `waiting`, and `journalctl -b` reports `Found ordering cycle: openrowingmonitor-display.service/start after openrowingmonitor.service/start after multi-user.target/start`. The display unit is pulled in by `multi-user.target` and ordered `After=openrowingmonitor.service`, while `openrowingmonitor.service` used to declare `After=multi-user.target` — that closes a cycle, and systemd leaves the whole boot transaction pending forever. Fix: `openrowingmonitor.service` must NOT use `After=multi-user.target` (its `WantedBy=multi-user.target` already orders it before the target); remove the line, run `systemctl daemon-reload`, then run `systemctl start openrowingmonitor.service` to unblock the queued boot jobs.
- **pigpio errors**: check `which pigpiod` and `/usr/local/lib/libpigpio.so` — the deploy builds joan2937/pigpio from source (Ubuntu resolute no longer ships the pigpio package) with `-std=gnu89` for GCC 14+ compatibility. The npm `pigpio` addon only builds when `pigpiod` is on PATH.
- **Permission errors**: the service runs as root by design — port 80, the HCI socket, GPIO access, and thread priorities all require it.
