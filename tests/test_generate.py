import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generate import Entry, Feed, make_rss, parse_entries  # noqa: E402


class FeedTests(unittest.TestCase):
    HTML = '''<html><body><div class="entrylist-main">
      <div class="entrylist-contents"><h3 class="entrylist-contents-title"><a href="https://example.org/a">記事A</a></h3><span class="entrylist-contents-users">123 users</span><p class="entrylist-contents-description">説明A</p></div>
      <div class="entrylist-contents"><h3 class="entrylist-contents-title"><a href="https://example.org/b">記事B</a></h3></div>
      <div class="entrylist-contents"><h3 class="entrylist-contents-title"><a href="https://example.org/c">記事C</a></h3></div>
      </div><aside><a href="https://example.org/sidebar">関連記事</a></aside></body></html>'''

    def test_parse_exact_cards(self):
        entries = parse_entries(self.HTML, 'https://b.hatena.ne.jp/hotentry/it/IT')
        self.assertEqual([e.title for e in entries], ['記事A', '記事B', '記事C'])
        self.assertEqual(entries[0].count, '123')
        self.assertEqual(entries[0].summary, '説明A')

    def test_rss_valid_and_guids_stable(self):
        entries = parse_entries(self.HTML, 'https://b.hatena.ne.jp/hotentry/it/IT')
        state = {}
        first_run = datetime(2026, 11, 21, tzinfo=timezone.utc)
        rss1 = make_rss(Feed('it', 'IT'), entries, state, first_run)
        rss2 = make_rss(Feed('it', 'IT'), entries, state, datetime(2026, 11, 22, tzinfo=timezone.utc))
        self.assertEqual(rss1, rss2)
        parsed = ET.fromstring(rss1)
        items = parsed.findall('./channel/item')
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].findtext('link'), 'https://example.org/a')
        self.assertEqual(items[0].findtext('guid'), Entry('a','https://example.org/a').guid)

    def test_empty_page_rejected(self):
        with self.assertRaises(ValueError):
            parse_entries('<html><p>blocked</p></html>', 'https://b.hatena.ne.jp/hotentry/it/IT')


if __name__ == '__main__':
    unittest.main()
