# Local configuration for the Open Rowing Monitor deploy.
#
# pyinfra 3 uses Python inventories (YAML inventory files were dropped in v3);
# this file is the direct equivalent of the old inventory.yml and holds all
# per-host connection and install settings.
#
# Single group "sbc" containing one host. Group data applies to all hosts
# in the group; `_sudo_password` is a global-argument default used by every
# operation that runs with `_sudo=True`.

sbc = ([
    'sbc',
], {
    # SSH access for the SBC
    'ssh_hostname': '192.168.47.149',
    'ssh_user': 'pi',
    'ssh_password': 'pi',

    # Sudo password for the deploy user (global argument default)
    '_sudo_password': 'pi',

    # Open Rowing Monitor install settings
    'orm_repo': 'https://github.com/JaapvanEkris/openrowingmonitor.git',
    'orm_branch': 'main',
    'orm_install_dir': '/opt/openrowingmonitor',
    'orm_hostname': 'rowingmonitor',
})
