"""
Some helpers to handle selection, configuration and start of wine commands
"""
import shutil

from minigalaxy.constants import WINE_VARIANTS

def is_wine_installed() -> bool:
    for wine in WINE_VARIANTS:
        if shutil.which(wine[0]):
            return True
    return False

def get_wine_path(game):
    binary_name = "wine"
    custom_wine_path = game.get_info("custom_wine")
    if custom_wine_path and custom_wine_path != shutil.which(binary_name):
        binary_name = custom_wine_path
    return binary_name