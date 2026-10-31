"""Забирает новые сообщения из Telegram-бота обратной связи и создаёт по каждому
задачу (issue) в репозитории. Явный спам сразу помечается меткой.

Запускается из GitHub Actions (.github/workflows/feedback.yml). Нужны переменные:
  TELEGRAM_BOT_TOKEN — токен бота от @BotFather (секрет репозитория)
  GITHUB_TOKEN, GITHUB_REPOSITORY — выдаёт сам GitHub Actions

Персональные данные не сохраняются (152-ФЗ): задачи публичные и лежат не в России, поэтому
в задачу попадает только текст сообщения — без имени, @username и id чата. Телефоны, почта
и @упоминания в самом тексте заменяются на «[скрыто]». Id чата нужен лишь на время запуска,
чтобы сразу ответить «спасибо», и нигде не записывается — поэтому позже ответить человеку нельзя.
"""
import os
import re
import sys

import requests

TG = "https://api.telegram.org/bot{token}/{method}"
LABEL = "telegram"
SPAM_LABEL = "возможно спам"
# фразы, а не кусочки слов: «переходит», «ставка», «доходы» в обычном сообщении — не реклама
SPAM_WORDS = re.compile(
    r"(крипт|bitcoin|\bbtc\b|usdt|казино|инвестиц|пассивн\w* доход|заработ\w* (?:от|до|в день|без вложени)|"
    r"ставк\w* на спорт|бесплатн\w* деньг|подпис\w* на (?:мой |наш )?канал|переходи(?:те)? по ссылке|"
    r"промокод|скидк\w* \d|onlyfans|18\+)", re.I)
LINK = re.compile(r"(https?://|t\.me/|www\.|@\w{5,}bot\b)", re.I)

GREETING = ("Привет! Это бот сайта с расписанием УТЖТ.\n"
            "Напишите, если нашли ошибку в расписании или заменах, или есть идея.\n\n"
            "Сообщение сохраняется без вашего имени и аккаунта. Не пишите в нём личные данные "
            "(ФИО, телефон, почту). Подробнее — «Политика обработки данных» внизу сайта.")
THANKS = ("Спасибо! Сообщение получено ✅\n"
          "В течение дня его прочитают. Если это ошибка в расписании — исправим, если предложение — рассмотрим.\n"
          "Ваше имя и аккаунт не сохраняются, поэтому ответить сюда не получится — "
          "если нужен ответ, напишите на почту, указанную внизу сайта.")
# личное в тексте сообщения: телефоны, почта, @упоминания
PRIVATE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|(?<!\w)@\w{3,}|(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
NOT_TEXT = "Пока принимаем только текстовые сообщения — опишите, пожалуйста, словами."


def spam_reason(text):
    """Причина, по которой сообщение похоже на спам, или None."""
    if LINK.search(text):
        return "есть ссылка"
    if SPAM_WORDS.search(text):
        return "рекламные слова"
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        return "КАПСЛОК"
    if len(text) > 15 and len(set(text.replace(" ", ""))) <= 3:
        return "повтор символов"
    return None


def scrub(text):
    """Телефоны, почта и @упоминания -> «[скрыто]»."""
    return PRIVATE.sub("[скрыто]", text)


def issue_for(msg):
    """Сообщение Telegram -> (заголовок, текст, метки) или None, если задачу не создаём."""
    raw = (msg.get("text") or msg.get("caption") or "").strip()
    if not raw or raw.startswith("/"):
        return None
    text = scrub(raw)
    first_line = " ".join(text.split())[:60]
    title = "Telegram: " + first_line + ("…" if len(" ".join(text.split())) > 60 else "")
    quoted = "\n".join("> " + line for line in text.splitlines())
    body = f"{quoted}\n\n— сообщение в боте обратной связи (без данных отправителя)"
    labels = [LABEL]
    reason = spam_reason(raw)
    if reason:
        labels.append(SPAM_LABEL)
        body += f"\n\nАвтоматическая пометка: похоже на спам ({reason})."
    return title, body, labels


class Bot:
    def __init__(self, token, session=None):
        self.token, self.s = token, session or requests.Session()

    def call(self, method, **params):
        r = self.s.post(TG.format(token=self.token, method=method), json=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data}")
        return data["result"]


class Repo:
    def __init__(self, token, repo, session=None):
        self.repo, self.s = repo, session or requests.Session()
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def ensure_labels(self):
        for name, color in ((LABEL, "2456c7"), (SPAM_LABEL, "b3261e")):
            r = self.s.post(f"https://api.github.com/repos/{self.repo}/labels", headers=self.h,
                            json={"name": name, "color": color}, timeout=30)
            if r.status_code not in (201, 422):  # 422 — метка уже есть
                r.raise_for_status()

    def create_issue(self, title, body, labels, assignees=()):
        data = {"title": title, "body": body, "labels": labels}
        if assignees:
            data["assignees"] = list(assignees)
        r = self.s.post(f"https://api.github.com/repos/{self.repo}/issues", headers=self.h, json=data, timeout=30)
        r.raise_for_status()
        return r.json()["number"]


def run(bot, repo, log=print, assignee=None):
    updates = bot.call("getUpdates", timeout=0, allowed_updates=["message"])
    if not updates:
        log("новых сообщений нет")
        return 0
    repo.ensure_labels()
    created, done = 0, None
    try:
        for u in updates:
            created += handle(u.get("message"), bot, repo, log, assignee)
            done = u["update_id"]
    finally:
        # подтверждаем Telegram только то, что уже обработано, — без дублей при сбое
        if done is not None:
            bot.call("getUpdates", offset=done + 1, timeout=0)
    log(f"обработано обновлений: {len(updates)}, создано задач: {created}")
    return created


def say(bot, chat, text, log):
    """Ответ человеку. Не вышло (заблокировал бота — 403) — не беда: задача уже создана, а сообщение
    иначе не подтвердилось бы Telegram и каждые 15 минут создавало бы такую же задачу снова."""
    try:
        bot.call("sendMessage", chat_id=chat, text=text)
    except Exception as e:  # noqa: BLE001
        log(f"не удалось ответить в чат: {e!r}")


def handle(msg, bot, repo, log, assignee=None):
    """Одно сообщение. True, если создана задача."""
    if not msg or msg.get("chat", {}).get("type") != "private":
        return False
    chat = msg["chat"]["id"]
    if (msg.get("text") or "").startswith("/start"):
        say(bot, chat, GREETING, log)
        return False
    issue = issue_for(msg)
    if issue is None:
        say(bot, chat, NOT_TEXT, log)
        return False
    # назначение на человека -> пуш «Assigned» в приложении GitHub; спам никому не назначаем
    spam = SPAM_LABEL in issue[2]
    number = repo.create_issue(*issue, assignees=[assignee] if assignee and not spam else [])
    log(f"задача #{number}: {issue[0]}" + (" [спам?]" if SPAM_LABEL in issue[2] else ""))
    if SPAM_LABEL not in issue[2]:
        say(bot, chat, THANKS, log)
    return True


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан — бот обратной связи ещё не настроен, пропускаю")
        return 0
    bot = Bot(token)
    repo = Repo(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    me = bot.call("getMe")
    hook = bot.call("getWebhookInfo")
    print(f"бот: @{me.get('username')}, ждут в очереди: {hook.get('pending_update_count', 0)}"
          + (", ВНИМАНИЕ: установлен вебхук — getUpdates не работает" if hook.get("url") else ""))
    if hook.get("url"):
        bot.call("deleteWebhook")  # сообщения забираем сами, вебхук мешает
    run(bot, repo, assignee=os.environ.get("FEEDBACK_ASSIGNEE") or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
