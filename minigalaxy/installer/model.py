from enum import Enum, auto

from minigalaxy import Platform
from minigalaxy.download import DownloadType
from minigalaxy.game import Game


class InstallableItem:
    """Helper class used to generalize handling of Game and DLC downloads."""

    def __init__(self, item_id, name, base_slug, slug, platform: Platform, item_type: DownloadType,
                 base_dir, sub_path="", install_target=""):
        self.id = item_id
        self.name = name
        self.platform = platform
        self.base_slug = base_slug                # like slug, but always refers to the one from Game (relevant for DLC)
        self.slug = slug                          # GOG-specific 'nickname', mostly a sanizited lower-case form of title
        self.installer_base_dir = base_dir        # name of the directory containing the installers  no path
        self.installer_sub_path = sub_path        # sub-path adjustment where DLC installers are saved
        self.item_type = item_type                # GAME or GAME_DLC
        self.install_target_dir = install_target  # The real, absolute directory where to install

    @staticmethod
    def for_gog_item(api, game: Game, dlc_id=None):
        if dlc_id:
            product_info = api.get_dlc_info(game, dlc_id)
            sub_path = Game.strip_string(product_info["title"], to_path=True)
            item_type = DownloadType.GAME_DLC
        else:
            product_info = api.get_info(game)
            sub_path = ""
            item_type = DownloadType.GAME

        name = product_info["title"]
        slug = product_info.get("slug", Game.strip_string(name, to_path=True))
        return InstallableItem(
            item_id=product_info["id"],
            name=name,
            base_slug=game.slug,
            slug=slug,
            platform=game.platform,
            item_type=item_type,
            base_dir=game.get_install_directory_name(),
            sub_path=sub_path
        )


class InstallResultType(Enum):
    """checksum verification has started"""
    VERIFY_START = auto()
    """A file has been verified successfully"""
    VERIFY_PROGRESS = auto()
    """The real installation has started"""
    INSTALL_START = auto()
    """Installation ended with success"""
    SUCCESS = auto()
    """Installation ended in failure"""
    FAILURE = auto()
    """Checksum verification failed"""
    CHECKSUM_ERROR = auto()
    """An error happened during post installation actions"""
    POST_INSTALL_FAILURE = auto()


class InstallResult:

    def __init__(self, install_id, result_type: InstallResultType, reason, details=None):
        """Data class that will be passed to result_callback of InstallTask
        reason is a type-dependent string:
        - INSTALL_START: game name
        - VERIFY_START: game name
        - VERIFY_PROGRESS: verified file
        - SUCCESS: install directory path
        - FAILURE and CHECKSUM_ERROR: string error message
        - POST_INSTALL_FAILURE: error message

        the "details" field provides additional context information:
        - VERIFY_START: InstallerInventory
        - VERIFY_PROGRESS: the md5 of the file
        - FAILURE: depending on the failing step, usually a directory path
        - CHECKSUM_ERROR: dict {abs_file: calculated_checksum} of all failed files
        """
        self.install_id = install_id
        self.type = result_type
        self.reason = reason
        self.details = details
        self.installation_terminated = result_type in [
            InstallResultType.SUCCESS,
            InstallResultType.FAILURE,
            InstallResultType.CHECKSUM_ERROR,
            InstallResultType.POST_INSTALL_FAILURE
        ]

    def __str__(self):
        return f"InstallResult(id={self.install_id}, type={self.type}), reason={self.reason})"

    def __eq__(self, other):
        """mainly used for testing, therefore not the most efficient implementation"""
        return str(self) == str(other)


class InstallException(Exception):

    def __init__(self, message, fail_type=InstallResultType.FAILURE, data=None):
        self.fail_type = fail_type
        self.message = message
        self.data = data
