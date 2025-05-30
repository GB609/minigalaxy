from minigalaxy.translation import _

SUPPORTED_DOWNLOAD_LANGUAGES = [
    ["br", _("Brazilian Portuguese")],
    ["cn", _("Chinese")],
    ["da", _("Danish")],
    ["nl", _("Dutch")],
    ["en", _("English")],
    ["fi", _("Finnish")],
    ["fr", _("French")],
    ["de", _("German")],
    ["hu", _("Hungarian")],
    ["it", _("Italian")],
    ["jp", _("Japanese")],
    ["ko", _("Korean")],
    ["no", _("Norwegian")],
    ["pl", _("Polish")],
    ["pt", _("Portuguese")],
    ["ru", _("Russian")],
    ["es", _("Spanish")],
    ["sv", _("Swedish")],
    ["tr", _("Turkish")],
    ["ro", _("Romanian")],
]

# match locale ids to special language names used by some installers
# mapping supports 1:n so we can add more than one per language if needed later
GAME_LANGUAGE_IDS = {
    "br": ["brazilian"],
    "cn": ["chinese"],
    "da": ["danish"],
    "nl": ["dutch"],
    "en": ["english"],
    "fi": ["finnish"],
    "fr": ["french"],
    "de": ["german"],
    "hu": ["hungarian"],
    "it": ["italian"],
    "jp": ["japanese"],
    "ko": ["korean"],
    "no": ["norwegian"],
    "pl": ["polish"],
    "pt": ["portuguese"],
    "ru": ["russian"],
    "es": ["spanish"],
    "sv": ["swedish"],
    "tr": ["turkish"],
    "ro": ["romanian"]
}

SUPPORTED_LOCALES = [
    ["", _("System default")],
    ["pt_BR", _("Brazilian Portuguese")],
    ["cs_CZ", _("Czech")],
    ["nl", _("Dutch")],
    ["en_US", _("English")],
    ["fi", _("Finnish")],
    ["fr", _("French")],
    ["de", _("German")],
    ["it_IT", _("Italian")],
    ["nb_NO", _("Norwegian Bokmål")],
    ["nn_NO", _("Norwegian Nynorsk")],
    ["pl", _("Polish")],
    ["pt_PT", _("Portuguese")],
    ["ru_RU", _("Russian")],
    ["zh_CN", _("Simplified Chinese")],
    ["es", _("Spanish")],
    ["es_ES", _("Spanish (Spain)")],
    ["sv_SE", _("Swedish")],
    ["zh_TW", _("Traditional Chinese")],
    ["tr", _("Turkish")],
    ["uk", _("Ukrainian")],
    ["el", _("Greek")],
    ["ro", _("Romanian")],
]

VIEWS = [
    ["grid", _("Grid")],
    ["list", _("List")],
]

# Game IDs to ignore when received by the API
IGNORE_GAME_IDS = [
    1424856371,  # Hotline Miami 2: Wrong Number - Digital Comics
    1980301910,  # The Witcher Goodies Collection
    2005648906,  # Spring Sale Goodies Collection #1
    1486144755,  # Cyberpunk 2077 Goodies Collection
    1581684020,  # A Plague Tale Digital Goodies Pack
    1185685769,  # CDPR Goodie Pack Content
]

DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB

# This is the file size needed for the download manager to consider resuming worthwhile
MINIMUM_RESUME_SIZE = 20 * 1024**2  # 20 MB

# Windows executables to not consider when launching
BINARY_NAMES_TO_IGNORE = [
    # Standard uninstaller
    "unins000.exe",
    # Common extra binaries
    "UnityCrashHandler64.exe",
    "nglide_config.exe",
    # Diablo 2 specific
    "ipxconfig.exe",
    "BNUpdate.exe",
    "VidSize.exe",
    # FreeSpace 2 specific
    "FRED2.exe",
    "FS2.exe",
]
