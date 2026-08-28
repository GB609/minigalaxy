""" MiniGalaxy packages """
from enum import Enum


INSTALLER_REPO = None


class Platform(str, Enum):
    """
    This enum represents a fundamental data type of minigalaxy: the target platform of a game.
    This should normally go into constants.py, but can't because of circular imports.
    """
    LINUX = "linux"
    WINDOWS = "windows"
