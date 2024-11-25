"""
Some helpers to handle selection, configuration and start of wine commands
"""
import shutil

from minigalaxy.constants import WINE_VARIANTS

GAMEINFO_UMUID = "umu_id"
GAMEINFO_CUSTOM_WINE = "custom_wine"

def is_wine_installed() -> bool:
    for wine in WINE_VARIANTS:
        if shutil.which(wine[0]):
            return True
    return False

def get_wine_path(game):
    custom_wine_path = game.get_info(GAMEINFO_CUSTOM_WINE)
    if custom_wine_path and shutil.which(custom_wine_path):
        return custom_wine_path

    #TODO: not really working - no initialized Config object accessible
    #basic idea instead is to write custom_wine on installation for all games
    #to make sure changing the default will not change and thus break already installed prefixes
    return get_default_wine({})

def get_default_wine(config: Config) -> str:
    runner = shutil.which(config.default_wine_runner)
    if runner:
        return runner

    #fallback: iterate through all known variants in declaration order
    for option in WINE_VARIANTS:
        runner = shutil.which(option[0])
        if runner:
            return runner
    
    #this should never happen when get_default_wine is used after is_wine_installed returns true
    return ""