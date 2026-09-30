import threading
import unittest
from unittest.mock import patch

from automation.collector import collect
from utils.exceptions import NetworkError


SITE = "https://matnam12.blogspot.com"


class CollectorTests(unittest.TestCase):
    def test_blogspot_feed_returns_post_urls(self):
        rss = b"""<rss><channel><item><link>https://matnam12.blogspot.com/2026/09/post.html</link></item></channel></rss>"""
        with patch("automation.collector._fetch", return_value=(SITE, rss)):
            _, urls = collect(SITE + "/", 30)
        self.assertEqual(urls, [SITE + "/2026/09/post.html"])

    def test_blogspot_feed_failure_uses_sitemap(self):
        sitemap = b"""<urlset><url><loc>https://matnam12.blogspot.com/2026/09/post.html</loc></url></urlset>"""

        def fetch(url):
            if "/feeds/" in url:
                raise NetworkError("Feed unavailable")
            return url, sitemap

        with patch("automation.collector._fetch", side_effect=fetch):
            _, urls = collect(SITE + "/", 30)
        self.assertEqual(urls, [SITE + "/2026/09/post.html"])

    def test_cancel_before_request(self):
        stopped = threading.Event()
        stopped.set()
        with patch("automation.collector._fetch") as fetch:
            _, urls = collect(SITE + "/", 30, stopped)
        self.assertEqual(urls, [])
        fetch.assert_not_called()

    def test_reports_collection_progress(self):
        rss = b"""<rss><channel><item><link>https://matnam12.blogspot.com/2026/09/post.html</link></item></channel></rss>"""
        updates = []
        with patch("automation.collector._fetch", return_value=(SITE, rss)):
            collect(SITE + "/", 30, progress=lambda message, count: updates.append((message, count)))
        self.assertEqual(updates[-1][1], 1)
        self.assertTrue(any("가져오는 중" in message for message, _ in updates))


if __name__ == "__main__":
    unittest.main()
