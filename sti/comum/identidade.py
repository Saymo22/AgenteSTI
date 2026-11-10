"""Normalização de referências auxiliares de inventário."""
import re

INVALID_SERIALS = {"", "0", "none", "unknown", "defaultstring", "systemserialnumber",
                   "tobefilledbyo.e.m.", "notapplicable", "notavailable"}


def clean_serial(value):
    text = str(value or "").strip()[:120]
    key = re.sub(r"\s+", "", text).casefold()
    return "" if key in INVALID_SERIALS or any(ord(c) < 32 for c in text) else text
