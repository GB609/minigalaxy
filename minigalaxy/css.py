import logging

from minigalaxy.resources import get_data_file
from minigalaxy.ui.gtk import Gtk, Gdk


CSS_PROVIDER = Gtk.CssProvider()


def load_css():
    """
    Load CSS data.
    """
    try:
        css_data_file = get_data_file("style.css")
        # css_data = css_data_file.read_text(encoding='utf-8')
        css_data = css_data_file.read_bytes()
        CSS_PROVIDER.load_from_data(css_data)
    except Exception:
        logging.error("The CSS could not be loaded", exc_info=1)
#        logging.error("file:%s, data:%s", str(css_data_file), str(css_data))
    Gtk.StyleContext().add_provider_for_screen(Gdk.Screen.get_default(), CSS_PROVIDER, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
