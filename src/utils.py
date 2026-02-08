import re

BAD_WORDS = [
    "бля",
    "блядь",
    "сука",
    "сучара",
    "хуй",
    "хуйовий",
    "хуйня",
    "хуєсос",
    "нахуй",
    "похуй",
    "пизда",
    "пиздець",
    "пиздити",
    "манда",
    "єбати",
    "єбало",
    "єблан",
    "довбойоб",
    "уйобок",
    "заїбав",
    "мудак",
    "мудило",
    "підор",
    "підар",
    "підарас",
    "гандон",
    "шлюха",
    "курва",
    "хвойда",
    "шмара",
    "гівно",
    "лайно",
    "срака",
    "засранець",
    "чмо",
    "лох",
    "чмирь",
    "дебіл",
    "ідіот",
    "придурок",
    "даун",
    "pornhub",
]

URL_PATTERN = re.compile(
    r"(?:http[s]?://[^\s]+|"
    r"www\.[^\s]+|"
    r"ftp://[^\s]+|"
    r"t\.me/[^\s]+|"
    r"@\w+|"
    r"(?:https?://)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)",
    re.IGNORECASE,
)


def contains_bad_words(text: str) -> bool:
    text_lower = text.lower()

    for word in BAD_WORDS:
        if word in text_lower:
            return True

    return False


def contains_links_or_urls(text: str) -> bool:
    return bool(URL_PATTERN.search(text))
