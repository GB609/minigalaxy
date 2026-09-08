from unittest import TestCase
from unittest.mock import MagicMock

from minigalaxy import Platform
from minigalaxy.download import DownloadType
from minigalaxy.game import Game
from minigalaxy.installer import InstallableItem


class TestInstallableItem(TestCase):

    def setUp(self):
        self.game_attribs = {
            "name": "!Absolute Test&",
            "url": "www.neverssl.com",
            "game_id": 846412,
            "platform": Platform.LINUX
        }
        self.product_info_game = {
            "id": 333,
            "title": "!Absolute Test&",
        }
        self.product_info_dlc = {
            "id": 383,
            "title": "Absolute?: Test-DLC",
        }

        self.api_mock = MagicMock()
        self.api_mock.get_info.return_value = self.product_info_game
        self.api_mock.get_dlc_info.return_value = self.product_info_dlc

    def test_create_for_game_with_slug(self):
        self.game_attribs["slug"] = "super-test-slug"
        self.product_info_game["slug"] = "super-test-slug"

        game = Game(**self.game_attribs)
        result = InstallableItem.for_gog_item(self.api_mock, game)

        self.assertEqual(333, result.id)
        self.assertEqual("!Absolute Test&", result.name)
        self.assertEqual("super-test-slug", result.base_slug)
        self.assertEqual(result.base_slug, result.slug)
        self.assertEqual(Platform.LINUX, result.platform)
        self.assertEqual(DownloadType.GAME, result.item_type)

        self.assertEqual("Absolute Test", result.installer_base_dir)
        self.assertEqual("", result.installer_sub_path)

    def test_create_for_game_no_slug(self):
        game = Game(**self.game_attribs)
        result = InstallableItem.for_gog_item(self.api_mock, game)

        self.assertEqual(333, result.id)
        self.assertEqual("!Absolute Test&", result.name)
        self.assertEqual("Absolute Test", result.base_slug)
        self.assertEqual("Absolute Test", result.slug)
        self.assertEqual(Platform.LINUX, result.platform)
        self.assertEqual(DownloadType.GAME, result.item_type)

        self.assertEqual("Absolute Test", result.installer_base_dir)
        self.assertEqual("", result.installer_sub_path)

    def test_create_for_dlc(self):
        self.game_attribs["slug"] = "super-test-slug"

        game = Game(**self.game_attribs)
        result = InstallableItem.for_gog_item(self.api_mock, game, 383)

        self.assertEqual(383, result.id)
        self.assertEqual("Absolute?: Test-DLC", result.name)
        self.assertEqual("super-test-slug", result.base_slug)
        self.assertEqual("Absolute TestDLC", result.slug)
        self.assertEqual(Platform.LINUX, result.platform)
        self.assertEqual(DownloadType.GAME_DLC, result.item_type)

        self.assertEqual("Absolute Test", result.installer_base_dir)
        self.assertEqual("Absolute TestDLC", result.installer_sub_path)
