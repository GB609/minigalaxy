import os
import shutil

from minigalaxy.config import Config
from minigalaxy.game import Game, InfoKey
from minigalaxy.installer import InstallerInventory


def handle_platform_switch(game: Game, new_platform: str, current_download_dir: str, config: Config):
    if new_platform != game.get_info(InfoKey.PLATFORM_CHOICE, None):
        game.set_info(InfoKey.PLATFORM_CHOICE, new_platform)

    if not config.keep_installers:
        # installers are not kept in general, or no platform-specific backups shall be kept
        if os.path.exists(current_download_dir):
            shutil.rmtree(current_download_dir)
        return

    # the next code handles the situation when there are downloaded files which don't match the new platform
    # what exactly happens depends on preferences

    current_downloads_platform = InstallerInventory.detect_platform_type(current_download_dir)
    if new_platform is None:
        # this happens when the chosen platform was deselected.
        # The current downloads must be checked against the default (which could be the same)
        new_platform = game.get_chosen_platform(config)

    # nothing to do, they are identical
    if current_downloads_platform == new_platform:
        return

    # when installers per platform shall be kept, then rename the current download dir with platform as suffix
    # optionally restore the identically created backup dir of the new platform
    backup_download_dir(current_download_dir, current_downloads_platform)
    restore_download_dir(current_download_dir, new_platform)


def backup_download_dir(download_dir, platform):
    platform_downloads = f"{download_dir}.{platform}"
    if not os.path.isdir(platform_downloads) and os.path.isdir(download_dir):
        shutil.move(download_dir, platform_downloads)


def restore_download_dir(download_dir, platform):
    platform_downloads = f"{download_dir}.{platform}"
    if os.path.isdir(platform_downloads) and not os.path.isdir(download_dir):
        shutil.move(platform_downloads, download_dir)


def update_supported_platforms(game: Game, config: Config):
    """Update 'Game.platform' of the given game depending on 'Config.platform_mode' and the install state"""
    if game.is_installed():
        # do nothing, installed games get their platform tag when loading from the install dir
        return

    active_platforms = set(config.platform_mode)
    supported_platforms = set(game.supported_platforms()) & active_platforms
    game.platform = list(supported_platforms)
