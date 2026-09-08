# set up package exports

from .inventory import InstallerInventory  # noqa: F401
# expose types from sub-package on 'public' api of 'installer' itself
from .model import InstallException, InstallResultType, InstallResult  # noqa: F401

from .core import check_diskspace, create_applications_file, \
    enqueue_game_install, uninstall_game, \
    InstallerQueue, InstallTask  # noqa: F401
