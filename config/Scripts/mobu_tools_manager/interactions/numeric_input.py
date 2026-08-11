"""Exact numeric input shared by interactive transforms."""

from __future__ import absolute_import


class NumericInput(object):
    def __init__(self):
        self.text = ""

    @property
    def active(self):
        return bool(self.text)

    @property
    def value(self):
        if self.text in ("", "-", ".", "-."):
            return None
        try:
            return float(self.text)
        except Exception:
            return None

    def clear(self):
        self.text = ""

    def feed(self, key, text=""):
        key = str(key or "").upper()
        text = str(text or "")
        previous = self.text
        if key == "BACKSPACE":
            self.text = self.text[:-1]
        elif key in ("MINUS", "-") or text == "-":
            if self.text.startswith("-"):
                self.text = self.text[1:]
            else:
                self.text = "-" + self.text
        elif key in ("PERIOD", "DECIMAL", ".") or text == ".":
            if "." not in self.text:
                self.text += "0." if self.text in ("", "-") else "."
        elif len(text) == 1 and text.isdigit():
            self.text += text
        elif len(key) == 1 and key.isdigit():
            self.text += key
        return self.text != previous
