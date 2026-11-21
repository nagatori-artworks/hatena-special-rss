#!/usr/bin/env python3
"""Convert three *exact* Hatena Bookmark special hotentry pages to RSS 2.0.

Designed for GitHub Actions + Pages, with stable GUIDs and first-seen dates.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
STATE_PATH = ROOT / "state.json"
STATUS_PATH = SITE / "status.json"
JST = timezone(timedelta(hours=9))
MIN_ENTRIES = 3
MAX_SUMMARY_CHARS = 220
MEDIA_NS = "http://search.yahoo.com/mrss/"
ET.register_namespace("media", MEDIA_NS)


@dataclass(frozen=True)
class Feed:
    slug: str
    name: str

    @property
    def source_url(self) -> str:
        return "https://b.hatena.ne.jp/hotentry/it/" + quote(self.name, safe="")


FEEDS = (
    Feed("it", "IT"),
    Feed("ai", "AI・機械学習"),
    Feed("programming", "プログラミング"),
)


@dataclass(frozen=True)
class Entry:
    title: str
    url: str
    count: str = ""
    summary: str = ""
    image_url: str = ""

    @property
    def guid(self) -> str:
        return "urn:sha256:" + hashlib.sha256(self.url.encode("utf-8")).hexdigest()


def compact_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_thumbnail(card, source_url: str) -> str:
    """Find an article thumbnail in Hatena's card without fetching article pages.

    Hatena often uses a CSS background-image rather than an <img> tag.
    Some layouts instead use lazy-loaded img attributes.
    """
    thumb = card.select_one(".entrylist-contents-thumb")
    if thumb is None:
        return ""

    def valid_url(value: str) -> str:
        value = html.unescape(str(value).strip())
        if not value or value.startswith(("data:", "javascript:", "#")):
            return ""
        absolute = urljoin(source_url, value)
        parsed = urlparse(absolute)
        return absolute if parsed.scheme in ("https", "http") and parsed.netloc else ""

    # The common Hatena markup is:
    # <p class="entrylist-contents-thumb"><span style="background-image:url(...)"></span></p>
    for element in [thumb, *thumb.select("[style]")]:
        style = element.get("style", "")
        for match in re.finditer(r"""url\(\s*(?:"([^"]+)"|'([^']+)'|([^)]*))\s*\)""", style, re.I):
            candidate = next((group for group in match.groups() if group is not None), "")
            image_url = valid_url(candidate)
            if image_url:
                return image_url

    # Fallback for layouts using regular/lazy-loaded images.
    for element in [thumb, *thumb.select("img, [data-background-image], [data-src], [data-original]")]:
        for attr in ("data-background-image", "data-src", "data-original", "data-lazy-src", "src"):
            candidate = element.get(attr)
            if candidate:
                image_url = valid_url(candidate)
                if image_url:
                    return image_url
        srcset = element.get("data-srcset") or element.get("srcset")
        if srcset:
            image_url = valid_url(srcset.split(",", 1)[0].strip().split()[0])
            if image_url:
                return image_url
    return ""


def parse_entries(html_text: str, source_url: str) -> list[Entry]:
    """Only capture the main hotentry cards, not arbitrary sidebar links."""
    soup = BeautifulSoup(html_text, "html.parser")
    cards = soup.select("div.entrylist-contents")
    entries: list[Entry] = []
    seen_urls: set[str] = set()

    for card in cards:
        title_link = card.select_one("h3.entrylist-contents-title a[href]")
        if title_link is None:
            continue
        title = compact_text(title_link.get_text(" ", strip=True))
        href = title_link.get("href", "")
        url = urljoin(source_url, str(href))
        parsed = urlparse(url)
        if (not title or parsed.scheme not in ("http", "https") or
                not parsed.netloc or url in seen_urls):
            continue
        # Exclude links back to category indexes: this must be an article.
        if parsed.netloc == "b.hatena.ne.jp" and parsed.path.startswith("/hotentry"):
            continue
        seen_urls.add(url)
        count_node = card.select_one(".entrylist-contents-users")
        count_match = re.search(r"[\d,]+", count_node.get_text(" ", strip=True)) if count_node else None
        count = count_match.group(0).replace(",", "") if count_match else ""
        summary_node = card.select_one(".entrylist-contents-description")
        summary = compact_text(summary_node.get_text(" ", strip=True))[:MAX_SUMMARY_CHARS] if summary_node else ""
        entries.append(Entry(title=title, url=url, count=count, summary=summary, image_url=extract_thumbnail(card, source_url)))

    if len(entries) < MIN_ENTRIES:
        raise ValueError(
            f"取得した記事が{len(entries)}件しかありません（必要数: {MIN_ENTRIES}件）。"
            "ページのHTML構造が変わったか、取得を制限されている可能性があります。"
        )
    return entries


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Unexpected JSON: {path}")
    return result


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=1,
        status=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        backoff_factor=2,
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; PersonalHatenaRSS/1.0; +https://github.com/)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.7",
    })
    return session


def make_rss(feed: Feed, entries: list[Entry], state: dict[str, str], now: datetime) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"はてなブックマーク 人気エントリー - {feed.name}（非公式RSS）"
    ET.SubElement(channel, "link").text = feed.source_url
    ET.SubElement(channel, "description").text = f"はてなブックマーク『{feed.name}』特集の人気エントリーを掲載順に配信する非公式フィードです。"
    ET.SubElement(channel, "language").text = "ja"
    ET.SubElement(channel, "generator").text = "PersonalHatenaRSS"

    for entry in entries:
        first_seen = state.setdefault(entry.guid, now.isoformat())
        published = datetime.fromisoformat(first_seen)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = entry.title
        ET.SubElement(item, "link").text = entry.url
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = entry.guid
        ET.SubElement(item, "pubDate").text = format_datetime(published)
        details = []
        if entry.count:
            details.append(f"{entry.count}ブックマーク")
        if entry.summary:
            details.append(entry.summary)
        ET.SubElement(item, "description").text = " / ".join(details) or "はてなブックマークの人気記事"
        ET.SubElement(item, "category").text = feed.name
        if entry.image_url:
            ET.SubElement(item, f"{{{MEDIA_NS}}}thumbnail", {"url": entry.image_url})
    ET.indent(rss, space="  ")
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def render_index(status: dict[str, dict]) -> str:
    rows: list[str] = []
    for feed in FEEDS:
        info = status.get(feed.slug, {})
        success = html.escape(str(info.get("last_success_jst", "未取得")))
        label = "正常" if info.get("ok") else "前回のデータを維持（取得失敗）"
        source_url = html.escape(feed.source_url, quote=True)
        rows.append(
            f'<li><strong>{html.escape(feed.name)}</strong> — '
            f'<a href="{feed.slug}.xml">RSSを開く</a> ／ '
            f'<a href="{source_url}">元ページ</a>'
            f'<div class="small">最終取得成功日（日本時間）: {success} ／ {label}</div></li>'
        )
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>はてなブックマーク特集 非公式RSS</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;max-width:740px;margin:55px auto;padding:0 22px;color:#26313a;line-height:1.8}li{margin:25px 0}.small{font-size:.84em;color:#566}a{color:#1467ad}</style>
</head><body><h1>はてなブックマーク特集の非公式RSS</h1>
<p>IT・AI／機械学習・プログラミングの「人気エントリー」を自動取得してRSS 2.0として公開しています。下記のRSSリンクをInoreaderに登録してください。</p>
<ul>""" + "\n".join(rows) + """</ul>
<p class="small">個人作成の非公式フィードです。はてなブックマーク運営とは関係ありません。取得が失敗した場合は前回成功したRSSを維持します。更新時刻は保証されません。</p>
</body></html>\n"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / ".nojekyll").touch()
    now = datetime.now(timezone.utc)
    today_jst = now.astimezone(JST).date().isoformat()
    state = load_json(STATE_PATH, {})
    existing_status = load_json(STATUS_PATH, {})
    new_status = existing_status.copy()
    session = make_session()
    failures: list[str] = []

    for feed in FEEDS:
        path = SITE / f"{feed.slug}.xml"
        try:
            logging.info("取得中 %s: %s", feed.name, feed.source_url)
            response = session.get(feed.source_url, timeout=30)
            response.raise_for_status()
            entries = parse_entries(response.text, feed.source_url)
            path.write_bytes(make_rss(feed, entries, state, now))
            images = sum(bool(entry.image_url) for entry in entries)
            logging.info("取得成功 %s: %d件 (サムネイル %d件)", feed.name, len(entries), images)
            new_status[feed.slug] = {"ok": True, "last_success_jst": today_jst, "items": len(entries)}
        except (requests.RequestException, ValueError) as exc:
            failures.append(feed.name)
            logging.warning("取得失敗 %s: %s", feed.name, exc)
            print(f"::warning::[{feed.name}] 取得に失敗。前回のRSSがあれば維持します。 {exc}", flush=True)
            if path.exists() and path.stat().st_size > 50:
                # Ensure the persisted file is valid before reusing it.
                ET.parse(path)
                prior = new_status.get(feed.slug, {})
                new_status[feed.slug] = {
                    "ok": False,
                    "last_success_jst": prior.get("last_success_jst", "不明"),
                    "items": prior.get("items", "不明"),
                }
            else:
                logging.error("%s: 前回のRSSもないため初回公開できません", feed.name)
                return 1
        time.sleep(1.3)

    # Prune entries not seen within 120 days to prevent unbounded state growth.
    threshold = now - timedelta(days=120)
    clean_state = {}
    for guid, iso in state.items():
        try:
            if datetime.fromisoformat(iso) >= threshold:
                clean_state[guid] = iso
        except (ValueError, TypeError):
            continue
    STATE_PATH.write_text(json.dumps(clean_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(new_status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (SITE / "index.html").write_text(render_index(new_status), encoding="utf-8")
    logging.info("生成完了: 3フィード、取得失敗 %d 件", len(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
