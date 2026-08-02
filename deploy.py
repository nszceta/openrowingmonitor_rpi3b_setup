"""
Deploy Open Rowing Monitor to a Raspberry Pi 3B running Armbian (Ubuntu base).

Mirrors the official installer (install/install.sh + docs/README.md), optimized
for minimal footprint and performance:
- systemd unit running node directly (no npm wrapper)
- performance CPU governor via a oneshot unit (no cpufrequtils package needed)
- pigpio source build fallback when the apt package is unavailable
- idempotent: clone/npm ci/build guarded via facts, config.js created only if absent

Written for pyinfra 3 (YAML inventories were dropped in v3; the inventory is the
Python file inventory.py). Run from this directory:
    pyinfra inventory.py deploy.py
"""

from pyinfra import host
from pyinfra.facts import files as files_facts
from pyinfra.facts import server as server_facts
from pyinfra.operations import apt, files, server, systemd

# Inventory data
orm_repo = host.data.get('orm_repo')
orm_branch = host.data.get('orm_branch')
install_dir = host.data.get('orm_install_dir')
orm_hostname = host.data.get('orm_hostname')


# Fact-based guards (pyinfra 3: `_if` takes callables only; `_unless` was removed)
def _pigpiod_missing():
    return host.get_fact(server_facts.Which, 'pigpiod') is None


def _repo_missing():
    return host.get_fact(files_facts.Directory, install_dir + '/.git') is None


def _node_modules_missing():
    return host.get_fact(files_facts.Directory, install_dir + '/node_modules') is None


def _build_missing():
    return host.get_fact(files_facts.File, install_dir + '/build/index.html') is None


def _config_missing():
    return host.get_fact(files_facts.File, install_dir + '/config/config.js') is None


# 1. Update apt index
server.shell(
    name='Update apt package index',
    commands=['apt-get update'],
    _sudo=True,
)

# 2. System dependencies
apt.packages(
    name='Install system dependencies',
    packages=[
        'git',
        'ca-certificates',
        'curl',
        'g++',
        'make',
        'python3',
        'libbluetooth-dev',
        'libudev-dev',
        'bluetooth',
        'bluez',
        'rfkill',
        # HDMI display kiosk (surf + matchbox on Xorg, validated on Pi 3B)
        'xserver-xorg',
        'xinit',
        'x11-xserver-utils',
        'surf',
        'matchbox-window-manager',
    ],
    _sudo=True,
)

# 2b. No apt pigpio package exists on Ubuntu resolute (only the libpigpiod-if
# client libs, which the npm addon cannot use) — pigpio is always built from
# source below.

# 3. Enable and start bluetooth stack
server.shell(
    name='Enable and start bluetooth stack',
    commands=[
        'systemctl enable bluetooth',
        'systemctl start bluetooth',
        'rfkill unblock bluetooth || true',
        'systemctl restart bluetooth',
    ],
    _sudo=True,
)

# 3b. Armbian minimal soft-blocks the radios at boot (verified: rfkill
# bluetooth state=1). The official installer unblocks once; we make it
# persistent with a oneshot unit that unblocks before bluetoothd starts.
files.put(
    name='Install rfkill unblock unit',
    src='files/rfkill-unblock.service',
    dest='/etc/systemd/system/rfkill-unblock.service',
    _sudo=True,
)
systemd.daemon_reload(name='Reload systemd for rfkill unblock unit', _sudo=True)
systemd.service(
    name='Enable rfkill unblock unit',
    service='rfkill-unblock',
    running=True,
    enabled=True,
    _sudo=True,
)

# 4. Build the pigpio C library from source — Ubuntu resolute (26.04) and
# Debian trixie dropped the pigpio package; only the libpigpiod-if daemon
# client libraries remain, which the npm addon cannot use (it links -lpigpio
# and gates its build on pigpiod being on PATH).
# `-std=gnu89` is required: modern GCC treats `void (*fn)()` as a strict
# no-arg prototype (C99+), which breaks joan2937's legacy code.
# `make install` runs the optional Python bindings step last, which fails on
# Python 3.12+ (distutils removed) — benign: the C library, headers and
# pigpiod are installed before that step, which the fallback guard verifies.
server.shell(
    name='Build pigpio C library from source',
    commands=[
        'git clone --depth 1 https://github.com/joan2937/pigpio /usr/local/src/pigpio || test -d /usr/local/src/pigpio/.git',
        'make -C /usr/local/src/pigpio -j2 CFLAGS="-O3 -Wall -pthread -fpic -std=gnu89"',
        'make -C /usr/local/src/pigpio install || (test -f /usr/local/lib/libpigpio.so && test -x /usr/local/bin/pigpiod)',
    ],
    _sudo=True,
    _if=_pigpiod_missing,
)

# 4b. Refresh the dynamic linker cache so the addon finds libpigpio.so.1 at
# runtime (runs unconditionally; cheap).
server.shell(
    name='Refresh dynamic linker cache',
    commands=['ldconfig'],
    _sudo=True,
)

# 4b. Mask the pigpiod daemon like the official installer does — the pigpio C
# library is used directly by the node wrapper, and a running daemon conflicts.
server.shell(
    name='Mask pigpiod daemon (official installer step)',
    commands=['systemctl mask pigpiod.service || true'],
    _sudo=True,
)

# 5. Node.js, adaptive (engines require >=20): prefer the distro package, fall
# back to NodeSource 22 when the distro version is missing or too old.
server.shell(
    name='Install distro Node.js if >=20 available',
    commands=['apt-get install -y nodejs npm || true'],
    _sudo=True,
)

server.shell(
    name='Install Node.js 22 via NodeSource if distro version too old',
    commands=[
        'if ! node --version 2>/dev/null | grep -qE "^v(2[0-9]|3[0-9])"; then '
        'curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs; fi',
    ],
    _sudo=True,
)

# 6. Hostname per official guide
if orm_hostname:
    server.hostname(
        name='Set device hostname',
        hostname=orm_hostname,
        _sudo=True,
    )
    server.shell(
        name='Ensure /etc/hosts entry for new hostname',
        commands=[
            'grep -q "127.0.1.1 {0}" /etc/hosts || echo "127.0.1.1 {0}" >> /etc/hosts'.format(orm_hostname),
        ],
        _sudo=True,
    )

# 7. Clone (only if absent)
server.shell(
    name='Clone Open Rowing Monitor',
    commands=['git clone --depth 1 --branch {0} {1} {2}'.format(orm_branch, orm_repo, install_dir)],
    _sudo=True,
    _if=_repo_missing,
)

# 8. Install npm dependencies (npm ci)
server.shell(
    name='Install npm dependencies (npm ci)',
    commands=['npm ci --no-audit --no-fund'],
    _sudo=True,
    _chdir=install_dir,
    _if=_node_modules_missing,
)

# 9. Build web frontend (rollup)
server.shell(
    name='Build web frontend (rollup)',
    commands=['npm run build'],
    _sudo=True,
    _chdir=install_dir,
    _if=_build_missing,
)

# 10. Prune dev dependencies (keeps the runtime tree small; idempotent)
server.shell(
    name='Prune dev dependencies',
    commands=['npm prune --omit=dev'],
    _sudo=True,
    _chdir=install_dir,
)

# 11. Config (never clobber user edits)
files.put(
    name='Install ORM config',
    src='files/config.js',
    dest='{0}/config/config.js'.format(install_dir),
    _sudo=True,
    _if=_config_missing,
)

# 12. Unit file
files.put(
    name='Install systemd unit',
    src='files/openrowingmonitor.service',
    dest='/lib/systemd/system/openrowingmonitor.service',
    _sudo=True,
)

# 13. Reload systemd
systemd.daemon_reload(name='Reload systemd', _sudo=True)

# 14. Enable and start Open Rowing Monitor
systemd.service(
    name='Enable and start Open Rowing Monitor',
    service='openrowingmonitor',
    running=True,
    enabled=True,
    restarted=True,
    _sudo=True,
)

# 14b. Display kiosk (surf + matchbox on Xorg via xinit, validated on Pi 3B)
files.put(
    name='Install display kiosk client script',
    src='files/openrowingmonitor-display',
    dest='/usr/local/bin/openrowingmonitor-display',
    mode='755',
    _sudo=True,
)
files.put(
    name='Install display kiosk unit',
    src='files/openrowingmonitor-display.service',
    dest='/etc/systemd/system/openrowingmonitor-display.service',
    _sudo=True,
)
systemd.daemon_reload(name='Reload systemd for display kiosk unit', _sudo=True)
systemd.service(
    name='Enable and start display kiosk',
    service='openrowingmonitor-display',
    running=True,
    enabled=True,
    _sudo=True,
)

# 15. Governor oneshot
files.put(
    name='Install CPU governor oneshot unit',
    src='files/cpufreq-performance.service',
    dest='/etc/systemd/system/cpufreq-performance.service',
    _sudo=True,
)
systemd.daemon_reload(name='Reload systemd for CPU governor unit', _sudo=True)
systemd.service(
    name='Enable performance governor',
    service='cpufreq-performance',
    running=True,
    enabled=True,
    _sudo=True,
)

# 16. Disable non-essential services (official perf guide)
server.shell(
    name='Disable non-essential services (official perf guide)',
    commands=[
        'systemctl disable --now triggerhappy.service || true',
        'systemctl disable --now avahi-daemon.service || true',
        'systemctl disable nfs-client.target || true',
    ],
    _sudo=True,
)

# 17. Smoke check: deploy must fail if the service is down
server.shell(
    name='Verify web UI responds on port 80',
    commands=['curl -fsS --retry 20 --retry-delay 3 --retry-connrefused http://127.0.0.1/ > /dev/null'],
    _sudo=True,
)
