import os
import re
import json

from minigalaxy.paths import CONFIG_GAMES_DIR, ICON_DIR, THUMBNAIL_DIR


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
          use_fallback=False enforces returning this path even when the file
          does not exist. But the game must still be installed.
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
            installed_version = self.get_info("version")
            if not installed_version:
                installed_version = self.fallback_read_installed_version()
                self.set_info("version", installed_version)
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

    def set_info(self, key, value):
        json_dict = self.load_minigalaxy_info_json()
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

    def get_info(self, key, default_value=""):
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

    def __str__(self):
        return self.name

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
