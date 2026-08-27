# -*- coding: utf-8 -*-
from urllib.parse import quote

def quote_media_name(name: str) -> str:
    return quote(name.replace("/", "_"), safe="")
