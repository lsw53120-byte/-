import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation import chrome_launcher


class ChromeLauncherTests(unittest.TestCase):
    def test_reuses_only_the_port_recorded_for_the_app_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            (profile / chrome_launcher.PORT_FILE).write_text("43123", encoding="ascii")
            with patch("automation.chrome_launcher._reject_default_profile"), \
                    patch("automation.chrome_launcher.is_debug_chrome_available", return_value=True):
                port, message = chrome_launcher.open_connected_chrome(profile)
            self.assertEqual(port, 43123)
            self.assertIn("기존", message)

    def test_allocated_port_is_loopback_only(self):
        port = chrome_launcher._free_loopback_port()
        self.assertGreaterEqual(port, 1024)
        self.assertLessEqual(port, 65535)


if __name__ == "__main__":
    unittest.main()
