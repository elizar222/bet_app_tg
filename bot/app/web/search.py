"""Поиск матча по тексту, как его видит пользователь на 1win: «Словения Шотландия», «Реал».

Названия в API английские, пользователи пишут по-русски. Поэтому запрос
переводится: страны и популярные клубы — по словарю, остальное — транслитом,
а совпадение считается «похожестью» строк, чтобы прощать опечатки и окончания.
"""

from __future__ import annotations

import difflib
import re

COUNTRIES = {
    "англия": "england", "шотландия": "scotland", "уэльс": "wales", "северная ирландия": "northern ireland",
    "ирландия": "ireland", "франция": "france", "германия": "germany", "испания": "spain", "италия": "italy",
    "португалия": "portugal", "нидерланды": "netherlands", "голландия": "netherlands", "бельгия": "belgium",
    "швейцария": "switzerland", "австрия": "austria", "дания": "denmark", "швеция": "sweden", "норвегия": "norway",
    "финляндия": "finland", "исландия": "iceland", "польша": "poland", "чехия": "czech republic",
    "словакия": "slovakia", "венгрия": "hungary", "румыния": "romania", "болгария": "bulgaria", "сербия": "serbia",
    "хорватия": "croatia", "словения": "slovenia", "босния": "bosnia", "черногория": "montenegro",
    "северная македония": "north macedonia", "македония": "north macedonia", "албания": "albania",
    "греция": "greece", "турция": "turkey", "кипр": "cyprus", "мальта": "malta", "украина": "ukraine",
    "беларусь": "belarus", "белоруссия": "belarus", "россия": "russia", "молдова": "moldova", "грузия": "georgia",
    "армения": "armenia", "азербайджан": "azerbaijan", "казахстан": "kazakhstan", "израиль": "israel",
    "эстония": "estonia", "латвия": "latvia", "литва": "lithuania", "люксембург": "luxembourg",
    "лихтенштейн": "liechtenstein", "андорра": "andorra", "сан-марино": "san marino", "сан марино": "san marino",
    "гибралтар": "gibraltar", "фарерские острова": "faroe islands", "фареры": "faroe islands", "косово": "kosovo",
    "бразилия": "brazil", "аргентина": "argentina", "уругвай": "uruguay", "колумбия": "colombia", "чили": "chile",
    "перу": "peru", "эквадор": "ecuador", "парагвай": "paraguay", "боливия": "bolivia", "венесуэла": "venezuela",
    "мексика": "mexico", "сша": "usa", "канада": "canada", "коста-рика": "costa rica", "панама": "panama",
    "гондурас": "honduras", "ямайка": "jamaica", "сальвадор": "el salvador", "гватемала": "guatemala",
    "япония": "japan", "корея": "korea republic", "южная корея": "korea republic", "китай": "china",
    "австралия": "australia", "иран": "iran", "саудовская аравия": "saudi arabia", "катар": "qatar", "оаэ": "united arab emirates",
    "ирак": "iraq", "узбекистан": "uzbekistan", "индия": "india", "таиланд": "thailand", "вьетнам": "vietnam",
    "индонезия": "indonesia", "египет": "egypt", "марокко": "morocco", "алжир": "algeria", "тунис": "tunisia",
    "нигерия": "nigeria", "гана": "ghana", "сенегал": "senegal", "камерун": "cameroon", "кот-д'ивуар": "ivory coast",
    "кот д ивуар": "ivory coast", "мали": "mali", "южная африка": "south africa", "юар": "south africa",
    "гвинея": "guinea", "кения": "kenya", "эритрея": "eritrea", "эфиопия": "ethiopia", "уганда": "uganda",
    "танзания": "tanzania", "замбия": "zambia", "зимбабве": "zimbabwe", "ангола": "angola", "конго": "congo",
    "габон": "gabon", "буркина-фасо": "burkina faso", "бенин": "benin", "того": "togo", "ливия": "libya",
    "судан": "sudan", "мадагаскар": "madagascar", "намибия": "namibia", "мозамбик": "mozambique",
    "новая зеландия": "new zealand",
}

CLUBS = {
    "реал": "real madrid", "реал мадрид": "real madrid", "барселона": "barcelona", "барса": "barcelona",
    "атлетико": "atletico madrid", "севилья": "sevilla", "валенсия": "valencia", "вильярреал": "villarreal",
    "бетис": "real betis", "манчестер сити": "manchester city", "ман сити": "manchester city",
    "манчестер юнайтед": "manchester united", "ман юнайтед": "manchester united", "мю": "manchester united",
    "ливерпуль": "liverpool", "арсенал": "arsenal", "челси": "chelsea", "тоттенхэм": "tottenham",
    "ньюкасл": "newcastle", "астон вилла": "aston villa", "вест хэм": "west ham", "эвертон": "everton",
    "бавария": "bayern munich", "боруссия": "borussia dortmund", "боруссия дортмунд": "borussia dortmund",
    "байер": "bayer leverkusen", "лейпциг": "rb leipzig", "ювентус": "juventus", "интер": "inter",
    "милан": "ac milan", "наполи": "napoli", "рома": "roma", "лацио": "lazio", "аталанта": "atalanta",
    "псж": "paris saint germain", "пари сен-жермен": "paris saint germain", "марсель": "marseille",
    "монако": "monaco", "лион": "lyon", "аякс": "ajax", "псв": "psv", "фейеноорд": "feyenoord",
    "бенфика": "benfica", "порту": "porto", "спортинг": "sporting cp", "галатасарай": "galatasaray",
    "фенербахче": "fenerbahce", "бешикташ": "besiktas", "селтик": "celtic", "рейнджерс": "rangers",
    "зенит": "zenit", "спартак": "spartak moscow", "цска": "cska moscow", "динамо москва": "dinamo moscow",
    "локомотив": "lokomotiv moscow", "краснодар": "krasnodar", "ростов": "rostov", "рубин": "rubin",
    "ахмат": "akhmat grozny", "крылья советов": "krylya sovetov", "шахтер": "shakhtar donetsk",
    "динамо киев": "dynamo kyiv",
}

WORDS = {
    "лига наций": "nations league", "лига чемпионов": "champions league", "лига европы": "europa league",
    "премьер лига": "premier league", "кубок": "cup", "женщины": "women", "молодежные": "u21",
}

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def translit(text: str) -> str:
    return "".join(_TR.get(ch, ch) for ch in text)


def norm(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s-]", " ", t)
    return " ".join(t.replace("-", " ").split())


def translate(query: str) -> list[str]:
    """Русский запрос → варианты на латинице (по словарям и транслитом)."""

    q = norm(query)
    for src, dst in sorted({**WORDS, **CLUBS, **COUNTRIES}.items(), key=lambda kv: -len(kv[0])):
        q = re.sub(rf"(?<!\w){re.escape(norm(src))}(?!\w)", dst, q)
    parts = [translit(q), norm(query)]  # и исходный текст — вдруг названия в базе русские
    return list(dict.fromkeys(p for p in parts if p))


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def score(query: str, home: str, away: str, league: str = "", country: str = "") -> float:
    """Насколько матч похож на запрос (0…1+). Учитывает обе команды и лигу."""

    variants = translate(query)
    h, a, lg = norm(home), norm(away), norm(f"{league} {country}")
    best = 0.0
    for v in variants:
        tokens = [t for t in re.split(r"\s+(?:vs|v|—|-)\s+|\s{2,}", v) if t] or [v]
        # «словения шотландия» — две команды через пробел: пробуем разбить на две половины
        if len(tokens) == 1:
            words = v.split()
            splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
        else:
            splits = [(tokens[0], tokens[1])]
        single = max(_ratio(v, h), _ratio(v, a))
        pair = max((max(_ratio(x, h) + _ratio(y, a), _ratio(x, a) + _ratio(y, h)) / 2 for x, y in splits), default=0.0)
        in_league = (0.75 if v in lg else 0.6 * _ratio(v, lg)) if len(v) > 3 else 0.0
        # слово целиком входит в название команды — сильный сигнал
        word_hit = 0.85 if any(w in h.split() or w in a.split() for w in v.split() if len(w) > 2) else 0.0
        best = max(best, single, pair, in_league, word_hit)
    return best


# ── обратный перевод: англ. названия из API → по-русски, как на 1win ─────────
_EN_RU = {}
for _ru, _en in COUNTRIES.items():
    _EN_RU.setdefault(_en, _ru)
_EN_RU.update({
    "south africa": "Южная Африка", "saudi arabia": "Саудовская Аравия", "north macedonia": "Северная Македония",
    "northern ireland": "Северная Ирландия", "new zealand": "Новая Зеландия", "united arab emirates": "ОАЭ",
    "korea republic": "Южная Корея", "costa rica": "Коста-Рика", "burkina faso": "Буркина-Фасо",
    "czech republic": "Чехия", "ivory coast": "Кот-д'Ивуар", "faroe islands": "Фарерские острова", "usa": "США",
})
_EN_RU.update({"czechia": "чехия", "türkiye": "турция",
               "bosnia & herzegovina": "босния и герцеговина", "cote d'ivoire": "кот-д'ивуар"})

LEAGUE_RU = [
    ("nations league", "Лига наций"), ("world cup - qualification", "Отбор ЧМ"), ("world cup", "Чемпионат мира"),
    ("euro championship - qualification", "Отбор Евро"), ("champions league", "Лига чемпионов"),
    ("europa league", "Лига Европы"), ("conference league", "Лига конференций"), ("friendlies", "Товарищеские"),
    ("africa cup of nations", "Кубок африканских наций"), ("copa libertadores", "Кубок Либертадорес"),
]
REGION_RU = {"world": "Мир", "europe": "Европа", "africa": "Африка", "asia": "Азия", "south america": "Юж. Америка"}


def team_ru(name: str) -> str:
    """Сборные — по-русски («Slovenia» → «Словения»), клубы оставляем как есть."""

    key = norm(name)
    for suffix in (" w", " u21", " u19", " u17"):
        if key.endswith(suffix) and key[: -len(suffix)] in _EN_RU:
            return _cap(_EN_RU[key[: -len(suffix)]]) + suffix.upper().replace(" W", " (Ж)")
    ru = _EN_RU.get(key)
    return _cap(ru) if ru else name


def _cap(text: str) -> str:
    """«сан-марино» → «Сан-Марино», «фарерские острова» → «Фарерские острова»."""

    first = text[:1].upper() + text[1:]
    return "-".join(p[:1].upper() + p[1:] for p in first.split("-"))


def league_ru(name: str, country: str) -> tuple[str, str]:
    low = (name or "").lower()
    for en, ru in LEAGUE_RU:
        if en in low:
            suffix = ""
            for part in ("africa", "europe", "asia", "south america", "concacaf"):
                if part in low and ru.startswith("Отбор"):
                    suffix = ", " + REGION_RU.get(part, part.upper())
            return ru + suffix, REGION_RU.get((country or "").lower(), team_ru(country or ""))
    return name, REGION_RU.get((country or "").lower(), team_ru(country or ""))
