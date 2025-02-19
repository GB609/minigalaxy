from enum import Enum
from zipfile import BadZipFile


# Enums were added in Python 3.4
class DownloadType(Enum):
    ICON = 1
    THUMBNAIL = 2
    GAME = 3
    GAME_UPDATE = 4
    GAME_DLC = 5


class Download:
    """
    A class to easily download from URLs and save the file.

    Usage:
    >>> import os
    >>> from minigalaxy.download import Download, DownloadType
    >>> from minigalaxy.download_manager import DownloadManager
    >>> def your_function():
    >>>   image_url = "https://www.gog.com/bundles/gogwebsitestaticpages/images/icon_section1-header.png"
    >>>   thumbnail = os.path.join(".", "{}.jpg".format("test-icon"))
    >>>   download = Download(image_url, thumbnail, DownloadType.THUMBNAIL, finish_func=lambda x: print("Done downloading {}!".format(x))) # noqa: E501
    >>>   download_manager.download(download)
    >>> your_function() # doctest: +SKIP

    API:
    Three different callback hooks can be defined when constructing an instance. 
    These expect the passed in function to be able to handle the following signature:
    - finish_func(Download): Called when the download completes successfully
    - progress_func(Download, percentage: int): 
      If the file size is known, this will be called whenever a new chunk is downloaded. If not, only at the beginning (0) and end (100)
    - cancel_func(Download, reason: str): When a download is aborted, either manually or because of an error during download

    Additional optional parameters:
    - download_type: Effectively determines queue to use and thus might impact priority
    - game: Game object this download is associated with
    - callback_context: 
      Arbitrary data that can be used as additional input in callbacks.
      Useful to avoid the need for nested lambdas
    """
    def __init__(self, url, save_location, download_type=None, 
                 finish_func=None, progress_func=None, cancel_func=None, 
                 number=1, out_of_amount=1, game=None, callback_context=None):
        self.url = url
        self.save_location = save_location
        self.callback_complete = finish_func
        self.callback_progress = progress_func
        self.callback_cancel = cancel_func
        self.callback_context = callback_context
        self.number = number
        self.out_of_amount = out_of_amount
        self.game = game
        # Type of object, e.g. icon, thumbnail, game, dlc,
        self.download_type = download_type

    def set_progress(self, percentage: int) -> None:
        "Set the download progress of the Download"
        if self.callback_progress:
            if self.out_of_amount > 1:
                # Change the percentage based on which number we are
                progress_start = 100 / self.out_of_amount * (self.number - 1)
                percentage = progress_start + percentage / self.out_of_amount
                percentage = int(percentage)
            self.callback_progress(self, percentage)

    def finish(self):
        """
        finish is called when the download has completed
        If a finish_func was specified when the Download was created, call the function
        """
        if self.callback_complete:
            try:
                self.callback_complete(self)
            except (FileNotFoundError, BadZipFile) as error:
                self.cancel(str(error))

    def cancel(self, reason=None):
        "Cancel the download, calling a cancel_func if one was specified"
        if self.callback_cancel:
            self.callback_cancel(self, reason)

    def _enqueue(self, download_manager):
        download_manager.put_in_proper_queue(self)
