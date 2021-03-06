# -*- coding: utf-8 -*-

# Copyright 2020 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://aryion.com/"""

from .common import Extractor, Message
from .. import text, util


BASE_PATTERN = r"(?:https?://)?(?:www\.)?aryion\.com/g4"


class AryionExtractor(Extractor):
    """Base class for aryion extractors"""
    category = "aryion"
    directory_fmt = ("{category}", "{user!l}", "{path:J - }")
    filename_fmt = "{id} {title}.{extension}"
    archive_fmt = "{id}"
    root = "https://aryion.com"

    def __init__(self, match):
        Extractor.__init__(self, match)
        self.user = match.group(1)
        self.offset = 0

    def posts(self, url):
        while True:
            page = self.request(url).text
            yield from text.extract_iter(
                page, "class='thumb' href='/g4/view/", "'")

            pos = page.find("Next &gt;&gt;")
            if pos < 0:
                return
            url = self.root + text.rextract(page, "href='", "'", pos)[0]

    def parse_post(self, post_id):
        url = "{}/g4/data.php?id={}".format(self.root, post_id)
        with self.request(url, method="HEAD", fatal=False) as response:

            if response.status_code >= 400:
                return None
            headers = response.headers

            # folder
            if headers["content-type"] in (
                "application/x-folder",
                "application/x-comic-folder-nomerge",
            ):
                return False

            # get filename from 'Content-Disposition' header
            cdis = headers["content-disposition"]
            fname, _, ext = text.extract(
                cdis, 'filename="', '"')[0].rpartition(".")
            if not fname:
                fname, ext = ext, fname

            # get file size from 'Content-Length' header
            clen = headers.get("content-length")

            # fix 'Last-Modified' header
            lmod = headers["last-modified"]
            if lmod[22] != ":":
                lmod = "{}:{} GMT".format(lmod[:22], lmod[22:24])

        post_url = "{}/g4/view/{}".format(self.root, post_id)
        extr = text.extract_from(self.request(post_url).text)

        title, _, artist = text.unescape(extr(
            "<title>g4 :: ", "<")).rpartition(" by ")
        data = {
            "id"    : text.parse_int(post_id),
            "url"   : url,
            "user"  : self.user or artist,
            "title" : title,
            "artist": artist,
            "path"  : text.split_html(extr("cookiecrumb'>", '</span'))[4:-1:2],
            "date"  : extr("class='pretty-date' title='", "'"),
            "size"  : text.parse_int(clen),
            "views" : text.parse_int(extr("Views</b>:", "<").replace(",", "")),
            "width" : text.parse_int(extr("Resolution</b>:", "x")),
            "height": text.parse_int(extr("", "<")),
            "comments" : text.parse_int(extr("Comments</b>:", "<")),
            "favorites": text.parse_int(extr("Favorites</b>:", "<")),
            "tags"     : text.split_html(extr("class='taglist'>", "</span>")),
            "description": text.unescape(text.remove_html(extr(
                "<p>", "</p>"), "", "")),
            "filename" : fname,
            "extension": ext,
            "_mtime"   : lmod,
        }

        d1, _, d2 = data["date"].partition(",")
        data["date"] = text.parse_datetime(
            d1[:-2] + d2, "%b %d %Y %I:%M %p", -5)

        return data


class AryionGalleryExtractor(AryionExtractor):
    """Extractor for a user's gallery on eka's portal"""
    subcategory = "gallery"
    pattern = BASE_PATTERN + r"/(?:gallery/|user/|latest.php\?name=)([^/?&#]+)"
    test = (
        ("https://aryion.com/g4/gallery/jameshoward", {
            "pattern": r"https://aryion\.com/g4/data\.php\?id=\d+$",
            "range": "48-52",
            "count": 5,
        }),
        ("https://aryion.com/g4/user/jameshoward"),
        ("https://aryion.com/g4/latest.php?name=jameshoward"),
    )

    def skip(self, num):
        self.offset += num
        return num

    def items(self):
        url = "{}/g4/latest.php?name={}".format(self.root, self.user)
        for post_id in util.advance(self.posts(url), self.offset):
            post = self.parse_post(post_id)
            if post:
                yield Message.Directory, post
                yield Message.Url, post["url"], post


class AryionPostExtractor(AryionExtractor):
    """Extractor for individual posts on eka's portal"""
    subcategory = "post"
    pattern = BASE_PATTERN + r"/view/(\d+)"
    test = (
        ("https://aryion.com/g4/view/510079", {
            "url": "f233286fa5558c07ae500f7f2d5cb0799881450e",
            "keyword": {
                "artist"   : "jameshoward",
                "user"     : "jameshoward",
                "filename" : "jameshoward-510079-subscribestar_150",
                "extension": "jpg",
                "id"       : 510079,
                "width"    : 1665,
                "height"   : 1619,
                "size"     : 784239,
                "title"    : "I'm on subscribestar now too!",
                "description": r"re:Doesn't hurt to have a backup, right\?",
                "tags"     : ["Non-Vore", "subscribestar"],
                "date"     : "dt:2019-02-16 19:30:00",
                "path"     : [],
                "views"    : int,
                "favorites": int,
                "comments" : int,
                "_mtime"   : "Sat, 16 Feb 2019 19:30:34 GMT",
            },
        }),
        # folder (#694)
        ("https://aryion.com/g4/view/588928", {
            "pattern": pattern,
            "count": ">= 8",
        }),
    )

    def items(self):
        post_id = self.user
        self.user = None
        post = self.parse_post(post_id)

        if post:
            yield Message.Directory, post
            yield Message.Url, post["url"], post

        elif post is False:
            folder_url = "{}/g4/view/{}".format(self.root, post_id)
            data = {"_extractor": AryionPostExtractor}

            for post_id in self.posts(folder_url):
                url = "{}/g4/view/{}".format(self.root, post_id)
                yield Message.Queue, url, data
