"""
A DownloadManager that provides an interface to manage and retry downloads.

First, you need to create a Download object, then pass the Download object to the
DownloadManager to download it.

Example:
>>> import os
>>> from minigalaxy.download import Download, DownloadType
>>> from minigalaxy.download_manager import DownloadManager
>>> def your_function():
>>>   image_url = "https://www.gog.com/bundles/gogwebsitestaticpages/images/icon_section1-header.png"
>>>   thumbnail = os.path.join(".", "{}.jpg".format("test-icon"))
>>>   download = Download(image_url, thumbnail, DownloadType.THUMBNAIL, finish_func=lambda x: print("Done downloading {}!".format(x))) # noqa: E501
>>>   DownloadManager.download(download)
>>> your_function() # doctest: +SKIP
"""
import logging
import os
import shutil
import time
import threading
import queue

import minigalaxy.logger  # noqa: F401

from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from minigalaxy.config import Config
from minigalaxy.constants import DOWNLOAD_CHUNK_SIZE, MINIMUM_RESUME_SIZE, GAME_DOWNLOAD_THREADS, UI_DOWNLOAD_THREADS
from minigalaxy.download import Download, DownloadType
from requests import codes, Session
from requests.exceptions import RequestException

module_logger = logging.getLogger("minigalaxy.download_manager")


class QueuedDownloadItem:
    """
    Wrap downloads in a simple class so we can manage when to download them
    """

    def __init__(self, download, priority=1):
        """
        Create a QueuedDownloadItem with a given download and priority level
        """
        self.priority = priority
        self.item = download
        self.queue_time = time.time()

    def __lt__(self, other):
        """
        Only compare QueuedDownloadItems on their priority level and
        time added to the queue.
        Later versions might use other factors (size, download type, etc.)
        For example, UX needs might want to prioritize items and other UI assets.
        """
        if self.priority != other.priority:
            return self.priority < other.priority
        else:
            return self.queue_time < other.queue_time


class DownloadState(Enum):
    '''This enum represents the various states that a Download goes through in DownloadManager'''

    QUEUED = 1  # Download request is put into the queue of pending downloads
    STARTED = 2  # The download url response is now actively being streamed into save_location
    PROGRESS = 3  # An active download made measurable progress
    COMPLETED = 4  # Download has completed without errors
    PAUSED = 5  # Download put on hold, will not go to active downloads unless specifically forced to
    STOPPED = 6  # Download was stopped. Does not prevent regular restart by calling download()
    FAILED = 7  # Active downloaded stopped because of an error
    CANCELED = 8  # Download was stopped, all partial progress and state info about it deleted


class DownloadManager:
    """
    A DownloadManager that provides an interface to manage and retry downloads.

    First, you need to create a Download object, then pass the Download object to the
    DownloadManager download or download_now method to download it.
    """

    CANCEL_STATES = [DownloadState.PAUSED, DownloadState.STOPPED, DownloadState.FAILED, DownloadState.CANCELED]

    STATE_DOWNLOAD_CALLBACKS = {
        DownloadState.COMPLETED: lambda d, *a: d.finish(),
        DownloadState.CANCELED: lambda d, *a: d.cancel(),
        DownloadState.FAILED: lambda d, *a: d.cancel(),
        DownloadState.STOPPED: lambda d, *a: d.cancel(),
        DownloadState.PROGRESS: lambda d, percent: d.set_progress(percent)
    }

    def __init__(self, session: Session, config: Config):
        """
        Create a new DownloadManager Object

        Args:
            This initializer takes no arguments
        """
        self.session = session
        self.config = config

        # A queue for UI elements
        self.__ui_queue = queue.PriorityQueue()

        # A queue for games and other long-running downloads
        self.__game_queue = queue.PriorityQueue()

        # The queues and associated limits
        self.queues = [(self.__ui_queue, UI_DOWNLOAD_THREADS),
                       (self.__game_queue, GAME_DOWNLOAD_THREADS)]

        self.__cancel = {}
        self.workers = []
        # The list of currently active downloads
        # These are items not in the queue, but currently being downloaded
        self.active_downloads = {}
        self.active_downloads_lock = threading.RLock()

        # to keep track and prevent re-queueing, because queue.get() would empty it otherwise
        self.queued_downloads = {}

        # members related to download change listener
        self.download_list_change_listener = []
        self.listener_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="download_listener")
        self.fork_listener = True

        self.logger = logging.getLogger("minigalaxy.download_manager.DownloadManager")

        for q, number_threads in self.queues:
            for i in range(number_threads):
                download_thread = threading.Thread(target=lambda: self.__download_thread(q))
                download_thread.daemon = True
                download_thread.start()
                self.workers.append(download_thread)

    def add_active_downloads_listener(self, listener):
        if listener not in self.download_list_change_listener:
            self.download_list_change_listener.append(listener)
            self.listener_thread.submit(self.__init_new_listener, listener)

    def remove_active_downloads_listener(self, listener):
        if listener in self.download_list_change_listener:
            self.download_list_change_listener.remove(listener)

    def __init_new_listener(self, listener):
        self.logger.debug("initialize new download listener")
        with self.active_downloads_lock:
            for download in self.active_downloads:
                self.__call_listener_failsafe(listener, DownloadState.STARTED, download)

            for download in self.queued_downloads:
                self.__call_listener_failsafe(listener, DownloadState.QUEUED, download)

    def __notify_listeners(self, change: DownloadState, download, additional_params=[], download_params=[], forked=None):
        '''helper function to notify listeners of changes to the active download list
        Will be used for each atomic add/remove action in the list of active downloads'''
        if not change:
            return

        # must differentiate from False to get default
        if forked is None:
            forked = not self.fork_listener

        if forked:
            self.logger.debug('[%s] NOTIFY:%s - %s, params:%s',
                              threading.currentThread().getName(), change, download.filename(), download_params)
            for listener in self.download_list_change_listener:
                self.__call_listener_failsafe(listener, change, download, *additional_params)
            self.__download_callback(download, change, *download_params, forked=forked)
        else:
            self.listener_thread.submit(self.__notify_listeners,
                                        change, download,
                                        additional_params=additional_params,
                                        download_params=download_params,
                                        forked=True)

    def __call_listener_failsafe(self, listener, *parameters):
        try:
            listener(*parameters)
        except BaseException:
            self.logger.exception("Error while trying to notify listener:")

    def download(self, download, restart_paused=False):
        """
        Add a download or list of downloads to the queue for downloading
        You can download a single Download or a list of Downloads

        Args:
            A single Download or a list of Download objects
        """
        if isinstance(download, Download):
            download = [download]

        paused_downloads = self.config.paused_downloads
        # Assume we've received a list of downloads
        for d in download:
            file = d.save_location
            if self.__is_pending(d):
                # ignore if the file is already pending
                continue

            if d.save_location in paused_downloads:
                self.logger.debug("Download [%s] is paused currently", file)
                if restart_paused:
                    self.config.remove_paused_download(file)
                else:
                    self.__notify_listeners(DownloadState.PAUSED, d)
                    # let paused downloads at least display a rough estimate of where they are
                    self.__notify_listeners(DownloadState.PROGRESS, d, download_params=[paused_downloads[file]])
                    continue

            self.put_in_proper_queue(d)

    def put_in_proper_queue(self, download):
        "Put the download in the proper queue"

        self.__notify_listeners(DownloadState.QUEUED, download)
        self.__add_to_queued_list(download)

        # Add game type downloads to the game queue
        if download.download_type == DownloadType.GAME:
            self.__game_queue.put(QueuedDownloadItem(download, 1))
        elif download.download_type == DownloadType.GAME_UPDATE:
            self.__game_queue.put(QueuedDownloadItem(download, 1))
        elif download.download_type == DownloadType.GAME_DLC:
            self.__game_queue.put(QueuedDownloadItem(download, 1))
        elif download.download_type == DownloadType.ICON:
            self.__ui_queue.put(QueuedDownloadItem(download, 0))
        elif download.download_type == DownloadType.THUMBNAIL:
            self.__ui_queue.put(QueuedDownloadItem(download, 0))
        else:
            # Add other items to the UI queue
            self.__ui_queue.put(QueuedDownloadItem(download, 0))

    def download_now(self, download):
        """
        Download an item with a higher priority
        Any item with the download_now priority set will get downloaded
        before other items.

        This is useful for things like thumbnails and icons that are important
        for UX responsiveness.

        Args:
            The Download to download
        """
        self.__ui_queue.put(QueuedDownloadItem(download, 0))

    def cancel_download(self, downloads, cancel_state=DownloadState.CANCELED):
        """
        Cancel a download or a list of downloads

        Args:
            A single Download or a list of Download objects
        """
        # Make sure we're always dealing with a list
        if isinstance(downloads, Download):
            downloads = [downloads]

        # Create a dictionary with the keys that are the downloads and the value is True
        # We use this to test for downloads more efficiently
        download_dict = dict(zip(downloads, [True] * len(downloads)))

        self.__cancel_paused_downloads(download_dict, cancel_state)
        self.__cancel_stopped_downloads(download_dict, cancel_state)

        # Next, loop through the downloads queued for download, comparing them to the
        # cancel list
        self.cancel_queued_downloads(download_dict, cancel_state)

        # This follows the previous logic
        # First cancel all the active downloads
        self.cancel_current_downloads(download_dict, cancel_state)

    def cancel_current_downloads(self, download_dict=None, cancel_state=DownloadState.CANCELED):
        """
        Cancel the current downloads
        """

        if not download_dict:
            download_dict = self.active_downloads

        with self.active_downloads_lock:
            for download in self.active_downloads:
                if download in download_dict:
                    self.logger.debug("Canceling download: %s", download.save_location)
                    # mark it for canceling
                    self.__request_download_cancel(download, cancel_state)

    def cancel_queued_downloads(self, download_dict, cancel_state=DownloadState.CANCELED):
        """
        Cancel selected downloads in the queue
        This is called by cancel_download

        Args:
          download_dict is a dictionary of downloads to cancel with values True
        """
        for download in download_dict.keys():
            self.logger.debug("download: {}".format(download))
            for download_queue, limit in self.queues:
                new_queue = queue.PriorityQueue()

                while not download_queue.empty():
                    queued_download = download_queue.get()

                    # Test a Download against a QueuedDownloadItem
                    should_cancel = download == queued_download.item
                    # test for games
                    if not should_cancel:
                        should_cancel = (download.game is not None) and (download.game == queued_download.item.game)
                    # test for other assets
                    if not should_cancel:
                        should_cancel = download.save_location == queued_download.item.save_location

                    if should_cancel:
                        self.__request_download_cancel(download, cancel_state)
                        self.__notify_listeners(cancel_state, download)
                    else:
                        new_queue.put(queued_download)
                    # Mark the task as "done" to keep counts correct so
                    # we can use join() or other functions later
                    download_queue.task_done()
                # Copy items back over to the queue
                while not new_queue.empty():
                    item = new_queue.get()
                    download_queue.put(item)

    def cancel_all_downloads(self, cancel_state=DownloadState.CANCELED):
        """
        Cancel all current downloads queued
        """
        self.logger.debug("Canceling all downloads")
        for download_queue, limit in self.queues:
            self.logger.debug("queue length: {}".format(download_queue.qsize()))
            while not download_queue.empty():
                download = download_queue.get().item
                self.logger.debug("canceling another download: {}".format(download.save_location))
                self.__request_download_cancel(download, cancel_state)
                self.__notify_listeners(cancel_state, download)
                # Mark the task as "done" to keep counts correct so
                # we can use join() or other functions later
                download_queue.task_done()

        self.cancel_current_downloads(cancel_state=cancel_state)

    def __cancel_paused_downloads(self, downloads, cancel_state=DownloadState.CANCELED):
        paused_downloads = self.config.paused_downloads
        for d in downloads:
            if d.save_location in paused_downloads:
                self.__request_download_cancel(d, cancel_state)
                self.__notify_listeners(cancel_state, d)

    def __cancel_stopped_downloads(self, downloads, cancel_state=DownloadState.CANCELED):
        # this method is pointless for other stop states
        if cancel_state not in [DownloadState.CANCELED, DownloadState.PAUSED]:
            return

        for d in downloads:
            if os.path.exists(d.save_location):
                self.__request_download_cancel(d, cancel_state)
                self.__notify_listeners(cancel_state, d)

    def __remove_download_from_active_downloads(self, download):
        "Remove a download from the list of active downloads"
        with self.active_downloads_lock:
            if download in self.active_downloads:
                self.logger.debug("Removing download from active downloads list")
                del self.active_downloads[download]
            else:
                self.logger.debug("Didn't find download in active downloads list")

    def __download_thread(self, download_queue):
        """
        The main DownloadManager thread calls this when it is created
        It checks the queue, starting new downloads when they are available
        Users of this library should not need to call this.
        """
        while True:
            if not download_queue.empty():
                # Update the active downloads
                with self.active_downloads_lock:
                    download = download_queue.get().item
                    self.active_downloads[download] = download
                    self.__remove_from_queued_list(download)

                self.__notify_listeners(DownloadState.STARTED, download)
                self.__download_file(download, download_queue)
                # Mark the task as done to keep counts correct so
                # we can use join() or other functions later
                download_queue.task_done()
            time.sleep(0.02)

    def __download_file(self, download, download_queue):
        """
        This is called by __download_thread to download a file
        It is also called directly by the thread created in download_now
        Users of this library should not need to call this.

        Args:
            The Download to download
        """
        self.__prepare_location(download.save_location)
        download_max_attempts = 5
        download_attempt = 0
        result = None
        additional_info = []
        last_error = None
        while download_attempt < download_max_attempts:
            try:
                start_point, download_mode = self.__get_start_point_and_download_mode(download)
                result = self.__download_operation(download, start_point, download_mode)
                break
            except RequestException as e:
                self.logger.error("Received error downloading file [%s]: %s", download.url, e)
                last_error = str(e)  # FIXME: need a way to remove token from error
                download_attempt += 1
                # TODO: maybe add an incrementally growing sleep time instead
                time.sleep(10)  # don't immediately use up all retries

        if download_attempt == download_max_attempts:
            result = DownloadState.FAILED
            if last_error:
                additional_info.append(last_error)

        # Successful downloads
        if result is DownloadState.COMPLETED:
            self.logger.debug("Download[%s] finished, thread %s", download.filename(), threading.get_ident())

        # Unsuccessful downloads and cancels
        if not result and self.__cancel_requested(download):
            result = self.__get_cancel_state(download)
            self.logger.debug("Download was canceled: {}, reason: {}".format(download.save_location, str(result)))
        if not result:
            result = DownloadState.FAILED

        self.__notify_listeners(result, download, additional_params=additional_info)
        self.__remove_download_from_active_downloads(download)
        self.__cleanup_meta(download, result)

    def __prepare_location(self, save_location):
        """
        Make sure the download directory exists and the file doesn't already exist

        Args:
            A filename string, where the download should be saved
        """
        # Make sure the directory exists
        save_directory = os.path.dirname(save_location)
        os.makedirs(save_directory, mode=0o755, exist_ok=True)

        # Fail if the file already exists
        if os.path.isdir(save_location):
            shutil.rmtree(save_location)
            self.logger.debug("{} is a directory. Will remove it, to make place for installer.".format(save_location))

    def __get_start_point_and_download_mode(self, download):
        """
        Resume the previous download if possible

        Args:
            The Download to download
        """
        start_point = 0
        download_mode = 'wb'
        if os.path.isfile(download.save_location):
            if self.__is_same_download_as_before(download):
                self.logger.debug("Resuming download {}".format(download.save_location))
                download_mode = 'ab'
                start_point = os.stat(download.save_location).st_size
            else:
                os.remove(download.save_location)
        return start_point, download_mode

    def __download_operation(self, download, start_point, download_mode):
        """
        Download the file
        This is called by __download_file to actually perform the download

        Args:
            The Download to download
            The start point in the download, specified in bytes
            The file mode to save the file as.
              For example, "wb" to create a new file
              or "ab" to append to a file for download resumes
        """
        resume_header = {'Range': 'bytes={}-'.format(start_point)}
        with self.session.get(download.url, headers=resume_header, stream=True, timeout=30) as download_request:
            # stop retries when 404 is received
            if download_request.status_code == 404:
                return DownloadState.FAILED

            downloaded_size = start_point
            self.__notify_listeners(DownloadState.PROGRESS, download, download_params=[0])
            file_size = self.__handle_download_size(download_request, download, downloaded_size)

            if file_size == downloaded_size:
                self.__notify_listeners(DownloadState.PROGRESS, download, download_params=[100])
                return DownloadState.COMPLETED

            current_progress = 0
            with open(download.save_location, download_mode) as save_file:
                for chunk in download_request.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    save_file.write(chunk)
                    downloaded_size += len(chunk)
                    if self.__cancel_requested(download):
                        return None

                    current_progress = self.__update_download_progress(downloaded_size, file_size, current_progress, download)

        if not file_size:
            self.__notify_listeners(DownloadState.PROGRESS, download, download_params=[100])
        return DownloadState.COMPLETED

    def __handle_download_size(self, request, download, downloaded_size):
        file_size = None
        try:
            file_size = int(request.headers.get('content-length'))
            if file_size and downloaded_size > 0:
                # we are resuming a partial file. file_size from content-length
                # will not include what we requested to skip over
                file_size += downloaded_size
        except (ValueError, TypeError):
            if download.expected_size:
                self.logger.warn("Couldn't get file size for %s. Use download.expected_size=%s.",
                                 download.save_location, download.expected_size)
                file_size = download.expected_size
            else:
                self.logger.error(f"Couldn't get file size for {download.save_location}. No progress will be shown.")

        if file_size != download.expected_size:
            # update expected_size in download with real values
            download.expected_size = file_size
        return file_size

    def __update_download_progress(self, current_size, total_size, last_progress_value, download):
        if total_size is None:
            # keep progress at 50 percent for files with unknown size.
            # this is rough, but better than no feedback at all
            progress = 50
        else:
            progress = int(current_size / total_size * 100)

        if progress > last_progress_value:
            self.logger.debug('%s: %d / %s * 100 = %s (previous=%s)',
                              download.filename(), current_size, total_size, progress, last_progress_value)
            self.__notify_listeners(DownloadState.PROGRESS, download, download_params=[progress])
            return progress
        else:
            return last_progress_value

    def __is_same_download_as_before(self, download):
        """
        Return true if the download is the same as an item with the same save_location already downloaded.

        Args:
            The Download to check
        """
        file_stats = os.stat(download.save_location)
        # Don't resume for very small files
        if file_stats.st_size < MINIMUM_RESUME_SIZE:
            return False

        size_to_check = DOWNLOAD_CHUNK_SIZE * 5
        # Check first part of the file
        resume_header = {'Range': 'bytes=0-{}'.format(size_to_check - 1)}  # range header is index-0-based
        with self.session.get(download.url, headers=resume_header, stream=True, timeout=30) as download_request:
            if not 200 <= download_request.status_code < 300:
                '''
                Response is not ok, so we can't download the file.
                Raise an error instead of returning False to prevent the potentially correct partial files from being deleted.
                '''
                download_request.raise_for_status()

            content_length = int(download_request.headers.get('content-length'))
            if content_length > size_to_check or download_request.status_code != 206:  # 206: partial content
                self.logger.debug("%s: server does not support http header 'Range' - need to restart download")
                return False

            for chunk in download_request.iter_content(chunk_size=size_to_check):
                with open(download.save_location, "rb") as file:
                    file_content = file.read(size_to_check)
                    return file_content == chunk

    def __download_callback(self, download, state, *params, forked=False):
        '''encapsulates invocation of callbacks on Download to assure uniform threading and
        error safeguarding to not kill downloads threads by uncaught exceptions'''
        if state in DownloadManager.STATE_DOWNLOAD_CALLBACKS:
            callback = DownloadManager.STATE_DOWNLOAD_CALLBACKS[state]
            error_wrapper = self.__call_listener_failsafe
            if forked:
                error_wrapper(callback, download, *params)
            else:
                self.listener_thread.submit(error_wrapper, callback, download, *params)

    def __is_pending(self, download):
        file = download.save_location
        with self.active_downloads_lock:
            # ignore if the file is already pending
            return file in self.active_downloads or file in self.queued_downloads

    def __add_to_queued_list(self, download):
        with self.active_downloads_lock:
            self.queued_downloads[download.save_location] = download

    def __remove_from_queued_list(self, download):
        with self.active_downloads_lock:
            if download.save_location in self.queued_downloads:
                del self.queued_downloads[download.save_location]

    def __request_download_cancel(self, download, cancel_type=DownloadState.CANCELED):
        '''used to separate data structure of self.__cancel from the logic procedure of flagging a download for cancel'''
        if not self.__is_cancel_type(cancel_type):
            raise ValueError(str(cancel_type) + " is not a valid cancel reason")

        is_active = False
        with self.active_downloads_lock:
            if download in self.active_downloads:
                self.__cancel[download] = cancel_type
                is_active = True

        # active downloads are taken care of in __download_file
        if not is_active and self.__is_cancel_type(cancel_type):
            self.__cleanup_meta(download, cancel_type)

        # must come after __cleanup_meta, because that might clear the pause flag
        if cancel_type == DownloadState.PAUSED:
            self.config.add_paused_download(download.save_location, download.current_progress)

    def __cancel_requested(self, download):
        return download in self.__cancel

    def __get_cancel_state(self, download):
        return self.__cancel.get(download, None)

    def __cleanup_meta(self, download, last_state):
        '''depending on the end state of a download, we might want to keep/remove a different set of state data
        about a download. That is what this method controls'''
        self.logger.debug('Cleaning up meta data for: %s', download.filename())
        if self.__is_cancel_type(last_state) and download in self.__cancel:
            del self.__cancel[download]

        if last_state in [DownloadState.CANCELED]:
            if os.path.isfile(download.save_location):
                os.remove(download.save_location)

        if self.__is_cancel_type(last_state) and last_state is not DownloadState.PAUSED:
            self.config.remove_paused_download(download.save_location)

        self.__remove_from_queued_list(download)
        # We may want to unset current_downloads here
        # For example, if a download was added that is impossible to complete

    def __is_cancel_type(self, state: DownloadState):
        return state in DownloadManager.CANCEL_STATES
