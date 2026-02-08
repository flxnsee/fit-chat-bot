import re

BAD_WORDS = [
    "бля", "блядь", "сука", "сучара", 
    "хуй", "хуйовий", "хуйня", "хуєсос", "нахуй", "похуй",
    "пизда", "пиздець", "пиздити", "манда",
    "єбати", "єбало", "єблан", "довбойоб", "уйобок", "заїбав",
    "мудак", "мудило", 
    "підор", "підар", "підарас", "гандон",
    "шлюха", "курва", "хвойда", "шмара",
    "гівно", "лайно", "срака", "засранець",
    "чмо", "лох", "чмирь", "дебіл", "ідіот", "придурок"
]

# Регулярний вираз для виявлення посилань
URL_PATTERN = re.compile(
    r'(?:http[s]?://[^\s]+|'  # HTTP/HTTPS посилання
    r'www\.[^\s]+|'            # www посилання
    r'ftp://[^\s]+|'           # FTP посилання
    r't\.me/[^\s]+|'           # Telegram посилання
    r'@\w+|'                   # Telegram username (@username)
    r'(?:https?://)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)',  # Доменні імена
    re.IGNORECASE
)

def contains_bad_words(text: str) -> bool:
    text_lower = text.lower()

    for word in BAD_WORDS:
        if word in text_lower:
            return True
        
    return False

def contains_links_or_urls(text: str) -> bool:
    """Перевіряє чи текст содержит посилання або URL-адреса"""
    return bool(URL_PATTERN.search(text))