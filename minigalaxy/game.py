import json
import logging
import os
import re

from enum import Enum
from minigalaxy.config import Config
from minigalaxy.paths import CONFIG_GAMES_DIR, ICON_DIR, THUMBNAIL_DIR


class InfoKey(str, Enum):
    """An enum representing all valid game-specific info/property keys"""

    CHECK_UPDATES = "check_for_updates"
    COMMAND = "command"
    CUSTOM_WINE = "custom_wine"
    GOG_PLATFORMS = "gog_platforms"
    HIDE_GAME = "hide_game"
    MANGOHUD = "use_mangohud"
    PLATFORM_CHOICE = "platform_choice"
    SHOW_FPS = "show_fps"
    GAMEMODE = "use_gamemode"
    VARIABLES = "variable"
    VERSION = "version"


class Game:

    def __init__(self, name: str, url: str = "", md5sum=None, game_id: int = 0, install_dir: str = "",
                 image_url="", platform="linux", dlcs=None, category=""):
        self.name = name
        self.url = url
        self.md5sum = {} if md5sum is None else md5sum
        self.id = game_id
        self.install_dir = install_dir
        self.image_url = image_url
        self.platform = platform
        self.dlcs = [] if dlcs is None else dlcs
        self.category = category
        self.status_file_path = self.get_status_file_path()

    def get_stripped_name(self, to_path=False):
        return Game.strip_string(self.name, to_path=to_path)

    @property
    def platform(self):
        """
        A game may support multiple platforms on GOG. There are places in the code where a distinction between
        a 'current' platform and all supported platforms is required.
        This is what this getter/property does - it provides the _current_ platform (selection) for a game.
        Current means:
        - It is installed OR
        - It is about to be installed and the target platform needs to be picked

        The logic backing it goes through a few cases:
        - When the game only supports one platform in the first place, return it.
          Note: An installed game is treated as supporting only the installed platform, regardless of what GOG says.
        - In case the game supports multiple platforms, the value of get_info(InfoKey.PLATFORM_CHOICE) is used (if any)

        **Note**
        This getter is mainly intended for UI purposes, because it can't provide one crucial information:
        The 'default' platform choice from preferences. This applies when a game supports multiple platforms,
        but the user has NOT picked which to install (=get_info(PLATFORM_CHOICE) is None).
        Since there is no singleton instance of 'Config', the default can not be retrieved by this getter automatically.

        Use 'Game.get_chosen_platform(config)' in that situation and (if required) update the game info.
        """
        return self.get_chosen_platform()

    @platform.setter
    def platform(self, platform_value):
        self.__platform = platform_value

    def get_chosen_platform(self, config=None):
        """
        A lot of games support multiple platforms. This method helps to determine which version to download.
        It depends on 2 pieces of info:
        - the type of Game.platform (list or string). As a list, it can currently only contain 'linux' and/or 'windows'
        - a game info flag 'platform_choice'. Set when a download is started to make sure it is correctly
          restarted on resume after MG restart

        Rules:
        1. When Game.platform is a string or list of size 1, take it. There is no other option.
        2. Check if 'platform_choice' was set and return it if yes
        3. If no choice was made and no Config instance given, return None
           Callers should then use Config.preferred_platform if applicable or throw an error otherwise
        4. If an instance of Config was given, default back to config.preferred_platform
        5. 'platform_choice' and 'preferred_platform' are subject to an additional check whether the
           game actually supports the given value. This guards against manual file edits in the game-info.json.
        """
        plf = self.__platform
        if isinstance(plf, str):
            return plf

        if isinstance(plf, list) and len(plf) == 1:
            return plf[0]

        plf = self.get_info(InfoKey.PLATFORM_CHOICE, None)
        if not plf and isinstance(config, Config):
            plf = config.preferred_platform

        if plf not in self.supported_platforms():
            logging.error("%s does not support platform %s", self.name, plf)
            return None

        return plf

    def is_singular_platform(self, platform):
        if isinstance(self.__platform, str) or (isinstance(self.__platform, list) and len(self.__platform) == 1):
            return platform in self.__platform

        return False

    def supports_multiple_platforms(self):
        return isinstance(self.__platform, list) and len(self.__platform) > 1

    def supported_platforms(self):
        if isinstance(self.__platform, str):
            return [self.__platform]
        return [*self.__platform]

    def get_install_directory_name(self):
        return Game.strip_string(self.name, to_path=True)

    def get_cached_icon_path(self, dlc_id=None):
        if dlc_id:
            return os.path.join(ICON_DIR, f"{dlc_id}.jpg")
        else:
            return os.path.join(ICON_DIR, f'{self.id}.png')

    def get_thumbnail_path(self, use_fallback=True):
        """
        Returns path to thumbnail file. Has 2 ways to use:
        1. As a file name/path factory - files don't have to exist
        2. To find the actually existing file
        Looks in 2 locations:
        - game.install_dir: When game is installed and file exists.
          use_fallback=False enforces returning this path even when the file does not exist.
          But the game must still be installed.
        - global thumbnail dir as denoted by minigalaxy.paths.THUMBNAIL_DIR
        """

        if self.is_installed():
            thumbnail_file = os.path.join(self.install_dir, "thumbnail.jpg")
            if os.path.isfile(thumbnail_file) or not use_fallback:
                return thumbnail_file

        thumbnail_file = os.path.join(THUMBNAIL_DIR, f"{self.id}.jpg")
        if os.path.isfile(thumbnail_file) or use_fallback:
            return thumbnail_file

        return ""

    def get_status_file_path(self):
        if self.install_dir:
            last_install_dir = os.path.basename(os.path.normpath(self.install_dir))
        else:
            last_install_dir = self.get_install_directory_name()
        status_file_path = os.path.join(CONFIG_GAMES_DIR, "{}.json".format(last_install_dir))
        return status_file_path

    def load_minigalaxy_info_json(self):
        json_dict = {}
        if os.path.isfile(self.status_file_path):
            with open(self.status_file_path, 'r') as status_file:
                json_dict = json.load(status_file)
        return json_dict

    def save_minigalaxy_info_json(self, json_dict):
        if not os.path.exists(CONFIG_GAMES_DIR):
            os.makedirs(CONFIG_GAMES_DIR, mode=0o755)
        # delete the json file if it exists and its new value would be just an empty dictionary
        if len(json_dict) == 0 and os.path.isfile(self.status_file_path):
            os.remove(self.status_file_path)
            return
        with open(self.status_file_path, 'w') as status_file:
            json.dump(json_dict, status_file)

    @staticmethod
    def strip_string(string, to_path=False):
        cleaned_string = re.sub('[^A-Za-z0-9]+', '', string) if not to_path else re.sub('[^A-Za-z0-9 ]+', '', string)
        return cleaned_string.strip()  # make sure the directory does not start or end with any whitespace

    def is_installed(self, dlc_title="") -> bool:
        installed = False
        if dlc_title:
            dlc_version = self.get_dlc_info("version", dlc_title)
            installed = bool(dlc_version)
        else:
            if self.install_dir and os.path.exists(self.install_dir):
                installed = True
        return installed

    def is_update_available(self, version_from_api, dlc_title="") -> bool:
        update_available = False
        if dlc_title:
            installed_version = self.get_dlc_info("version", dlc_title)
        else:
            installed_version = self.get_info(InfoKey.VERSION)
            if not installed_version:
                installed_version = self.fallback_read_installed_version()
                self.set_info(InfoKey.VERSION, installed_version)
        if installed_version and version_from_api and version_from_api != installed_version:
            update_available = True

        return update_available

    def fallback_read_installed_version(self):
        gameinfo = os.path.join(self.install_dir, "gameinfo")
        gameinfo_list = []
        if os.path.isfile(gameinfo):
            with open(gameinfo, 'r') as file:
                gameinfo_list = file.readlines()
        if len(gameinfo_list) > 1:
            version = gameinfo_list[1].strip()
        else:
            version = "0"
        return version

    def set_info(self, key: InfoKey, value):
        """Set given key-value-pair for the game. Deletes the entry when None is passed as value."""
        key = self.__info_key_from_arg(key)
        json_dict = self.load_minigalaxy_info_json()
        if value is None:
            if key in json_dict:
                del json_dict[key]
        else:
            json_dict[key] = value
        self.save_minigalaxy_info_json(json_dict)

    def set_dlc_info(self, key, value, dlc_title):
        json_dict = self.load_minigalaxy_info_json()
        if "dlcs" not in json_dict:
            json_dict["dlcs"] = {}
        if dlc_title not in json_dict["dlcs"]:
            json_dict["dlcs"][dlc_title] = {}
        json_dict["dlcs"][dlc_title][key] = value
        self.save_minigalaxy_info_json(json_dict)

    def get_info(self, key: InfoKey, default_value=""):
        key = self.__info_key_from_arg(key)
        value = ""
        json_dict = self.load_minigalaxy_info_json()
        if key in json_dict:
            value = json_dict[key]
        # Start: Code for compatibility with minigalaxy 1.0.1 and 1.0.2
        elif os.path.isfile(os.path.join(self.install_dir, "minigalaxy-info.json")):
            with open(os.path.join(self.install_dir, "minigalaxy-info.json"), 'r') as status_file:
                json_dict = json.load(status_file)
            if key in json_dict:
                value = json_dict[key]
                # Lets move this value to new config
                self.set_info(key, value)
        # End: Code for compatibility with minigalaxy 1.0.1 and 1.0.2
        return default_value if value == "" else value

    def get_dlc_info(self, key, dlc_title):
        value = ""
        json_dict = self.load_minigalaxy_info_json()
        if "dlcs" in json_dict:
            if dlc_title in json_dict["dlcs"]:
                if key in json_dict["dlcs"][dlc_title]:
                    value = json_dict["dlcs"][dlc_title][key]
        # Start: Code for compatibility with minigalaxy 1.0.1 and 1.0.2
        if os.path.isfile(os.path.join(self.install_dir, "minigalaxy-info.json")) and not value:
            with open(os.path.join(self.install_dir, "minigalaxy-info.json"), 'r') as status_file:
                json_dict = json.load(status_file)
            if "dlcs" in json_dict:
                if dlc_title in json_dict["dlcs"]:
                    if key in json_dict["dlcs"][dlc_title]:
                        value = json_dict["dlcs"][dlc_title][key]
                        # Lets move this value to new config
                        self.set_dlc_info(key, value, dlc_title)
        # End: Code for compatibility with minigalaxy 1.0.1 and 1.0.2
        return value

    def set_install_dir(self, install_dir) -> None:
        """
        Set the install directory based on the given install dir and the game name
        :param install_dir: the global install directory from the config
        """
        if not self.install_dir:
            self.install_dir = os.path.join(install_dir, self.get_install_directory_name())

    def update_from_other(self, other_game):
        """
        Take a certain set of property values from the given other Game instance.
        Useful to refresh Games created from local data with additional data from the GOG Api.
        """

        # this update is only necessary if self and other_game are 2 different object instances
        if self is other_game:
            return

        if self.id == 0 or self.name != other_game.name:
            self.id = other_game.id
            self.name = other_game.name

        self.image_url = other_game.image_url
        self.url = other_game.url
        self.category = other_game.category

    def __info_key_from_arg(self, key):
        """
        For test compatibility. Regular MG production could should use InfoKey for protection against typos etc.
        But this method takes either str or InfoKey and returns the str value to use as json key.
        """
        if isinstance(key, InfoKey):
            return key.value
        logging.warning("An instance of game.InfoKey is expected, but %s was given!", type(key))
        return key

    def __str__(self):
        return self.name

    def __repr__(self):
        return f'''Game(
            name="{self.name}",
            url="{self.url}",
            md5sum={self.md5sum},
            game_id={self.id},
            install_dir="{self.install_dir}",
            image_url="{self.image_url}",
            chosen_platform="{self.platform}",
            supported_platforms="${self.supported_platforms()}",
            dlcs={self.dlcs},
            category="{self.category}"
        )'''

    def __eq__(self, other):
        if self.id > 0 and other.id > 0:
            return self.id == other.id
        if self.name == other.name:
            return True
        # Compare names with special characters and capital letters removed
        if self.get_stripped_name().lower() == other.get_stripped_name().lower():
            return True
        if self.install_dir and \
                other.get_install_directory_name() == os.path.basename(os.path.normpath(self.install_dir)):
            return True
        if other.install_dir and \
                self.get_install_directory_name() == os.path.basename(os.path.normpath(other.install_dir)):
            return True
        return False

    def __lt__(self, other):
        # Sort installed games before not installed ones
        if self.is_installed() != other.is_installed():
            return self.is_installed()
        return str(self) < str(other)
