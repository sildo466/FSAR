# SPDX-License-Identifier: MIT
"""Birthday trigger decisions and the letter the app writes in its own voice.

Pure functions and static text only: no filesystem, no database, no model.
`src/server/birthday_runner.py` performs the effects this module decides on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.core.time_context import birthday_in_year, parse_birthday

SKIN_ID = "birthday"
DEFAULT_LOCALE = "en"

LANGUAGE_NAMES = {
    "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)",
    "en": "English",
    "ja": "Japanese",
    "de": "German",
    "fr": "French",
}

LETTERS: dict[str, str] = {
    "zh-Hans": (
        "生日快乐！\n\n"
        "今天是你的日子，其他事都可以先放一放。\n\n"
        "祝你天天开心，万事顺利。希望你想要的都能得到，在意的都能留住，"
        "想做的事都能做成。愿往后这一年，好事多一些，麻烦少一些。\n\n"
        "去通知里看看，你的角色可能给你写了祝福呢。\n\n"
        "最后，我以及 FSAR 在这里，给你送上最真挚的祝福。\n\n"
        "—— FSAR 及其开发者"
    ),
    "zh-Hant": (
        "生日快樂！\n\n"
        "今天是你的日子，其他事都可以先放一放。\n\n"
        "祝你天天開心，萬事順利。希望你想要的都能得到，在意的都能留住，"
        "想做的事都能做成。願往後這一年，好事多一些，麻煩少一些。\n\n"
        "去通知裡看看，你的角色可能給你寫了祝福呢。\n\n"
        "最後，我以及 FSAR 在這裡，給你送上最真摯的祝福。\n\n"
        "—— FSAR 及其開發者"
    ),
    "en": (
        "Happy birthday!\n\n"
        "Today is your day — everything else can wait.\n\n"
        "Wishing you happiness every day and smooth sailing in everything. "
        "May you get what you want, keep what you care about, and finish what "
        "you set out to do. Here's to a year with more good things and fewer "
        "troubles.\n\n"
        "Have a look in your notifications — your characters may have written "
        "you something.\n\n"
        "Finally, from me and FSAR: our warmest wishes.\n\n"
        "— FSAR and its developer"
    ),
    "ja": (
        "お誕生日おめでとう！\n\n"
        "今日はあなたの日です。他のことは後回しでいい。\n\n"
        "毎日が楽しく、何もかも順調でありますように。欲しいものが手に入り、"
        "大切なものがずっとそばにいて、やりたいことが全部できますように。"
        "この一年が、いいことが多く、面倒ごとの少ない年になりますように。\n\n"
        "通知ものぞいてみてください。あなたのキャラクターたちが、"
        "お祝いを書いてくれているかもしれません。\n\n"
        "最後に、私と FSAR から、心からのお祝いを。\n\n"
        "—— FSAR とその開発者"
    ),
    "de": (
        "Alles Gute zum Geburtstag!\n\n"
        "Heute ist dein Tag — alles andere kann warten.\n\n"
        "Ich wünsche dir jeden Tag Freude und dass alles gut läuft. Mögest du "
        "bekommen, was du willst, behalten, was dir wichtig ist, und schaffen, "
        "was du dir vornimmst. Auf ein Jahr mit mehr schönen Dingen und "
        "weniger Ärger.\n\n"
        "Schau mal in deine Benachrichtigungen — vielleicht haben deine "
        "Charaktere dir etwas geschrieben.\n\n"
        "Zum Schluss, von mir und FSAR: die herzlichsten Glückwünsche.\n\n"
        "— FSAR und seine Entwickler"
    ),
    "fr": (
        "Joyeux anniversaire !\n\n"
        "C'est ton jour — tout le reste peut attendre.\n\n"
        "Je te souhaite du bonheur chaque jour et que tout te réussisse. "
        "Puisses-tu obtenir ce que tu veux, garder ce qui t'est cher et mener "
        "à bien ce que tu entreprends. À une année avec plus de belles choses "
        "et moins d'ennuis.\n\n"
        "Va voir dans tes notifications — tes personnages t'ont peut-être "
        "écrit quelque chose.\n\n"
        "Enfin, de ma part et de celle de FSAR : nos vœux les plus sincères.\n\n"
        "— FSAR et son développeur"
    ),
}


@dataclass(frozen=True)
class BirthdayActions:
    unlock_skin: bool
    apply_skin: bool
    show_letter: bool
    write_letters: bool


def letter_for(locale: str | None) -> str:
    return LETTERS.get((locale or "").strip(), LETTERS[DEFAULT_LOCALE])


def letters_instruction(locale: str | None) -> str:
    language = LANGUAGE_NAMES.get(
        (locale or "").strip(), LANGUAGE_NAMES[DEFAULT_LOCALE],
    )
    return (
        "Today is the birthday of the person you are talking to. Write them a "
        "short letter — three to six sentences — in " + language + ". Say it in "
        "your own words, the way someone from your world would say it. Write "
        "only the letter itself: no title, no explanation, and never mention "
        "systems, prompts, or that you were told anything."
    )


def birthday_actions(
    now: datetime,
    birthday_raw,
    *,
    skin_present: bool,
    letter_shown_on: str | None = None,
    letters_year: int | None = None,
) -> BirthdayActions:
    """What to do on this connection. `arrived` covers the whole stretch from
    the birthday onward, because the skin and the notifications are meant to
    survive the user not opening the app that day."""
    birthday = parse_birthday(birthday_raw)
    if birthday is None or not isinstance(now, datetime):
        return BirthdayActions(False, False, False, False)
    month, day = birthday
    this_year = birthday_in_year(now.year, month, day)
    today = now.date()
    arrived = today >= this_year
    is_today = today == this_year
    return BirthdayActions(
        unlock_skin=arrived and not skin_present,
        apply_skin=is_today,
        show_letter=is_today and letter_shown_on != today.isoformat(),
        write_letters=arrived and letters_year != now.year,
    )
