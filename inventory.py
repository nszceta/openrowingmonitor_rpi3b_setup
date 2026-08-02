# Local configuration for the Open Rowing Monitor deploy.
#
# pyinfra 3 uses Python inventories (YAML inventory files were dropped in v3);
# this file is the direct equivalent of the old inventory.yml and holds all
# per-host connection and install settings.
#
# Single group "rpi3b" containing one host. Group data applies to all hosts
# in the group; `_sudo_password` is a global-argument default used by every
# operation that runs with `_sudo=True`.

rpi3b = ([
    'rpi3b',
], {
    # SSH access (rpi4b / rpi4b @ 192.168.47.116)
    'ssh_hostname': '192.168.47.116',
    'ssh_user': 'rpi4b',
    'ssh_password': 'rpi4b',

    # Sudo password for the deploy user (global argument default)
    '_sudo_password': 'rpi4b',

    # Open Rowing Monitor install settings
    'orm_repo': 'https://github.com/JaapvanEkris/openrowingmonitor.git',
    'orm_branch': 'main',
    'orm_install_dir': '/opt/openrowingmonitor',
    'orm_hostname': 'rowingmonitor',
})
