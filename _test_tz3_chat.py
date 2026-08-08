"""E2E проверка правок ТЗ №3 (модерация чата, удаление сообщений,
PII-фильтр, контекстный фильтр веществ) против реального ASGI-приложения
(временный файл, по образцу _test_sprint10.py)."""
import asyncio, os, sys
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_tz3.db"
if os.path.exists("test_tz3.db"): os.remove("test_tz3.db")

import config
config.DEV_MODE = True

import httpx
import main
from database import async_session, init_db, User
from sqlalchemy import select

FAIL = []
def check(cond, label, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   -> {extra}" if extra and not cond else ""))
    if not cond: FAIL.append(label)

async def run():
    await init_db()
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        await c.post("/api/auth/telegram/dev", json={"telegram_id": 2001, "username": "alice"})
        await c.post("/api/auth/telegram/dev", json={"telegram_id": 2002, "username": "bob"})

        print("\n[1] Обычное сообщение проходит")
        r = await c.post("/api/chat/send", json={"telegram_id": 2001, "text": "привет всем, как дела?"})
        check(r.status_code == 200, "чистое сообщение отправлено", r.text)
        msg_id = r.json()["message"]["id"] if r.status_code == 200 else None

        print("\n[2] Контекстный фильтр веществ — НЕ блокирует простое упоминание")
        r = await c.post("/api/chat/send", json={"telegram_id": 2002, "text": "мефедрон убивает нейроны, не советую"})
        check(r.status_code == 200, "простое упоминание вещества без коммерции проходит", r.text)

        await asyncio.sleep(4.2)  # обойти rate-limit (CHAT_RATE_LIMIT_SECONDS) между сообщениями одного игрока

        print("\n[3] Контекстный фильтр веществ — блокирует коммерческий контекст")
        r = await c.post("/api/chat/send", json={"telegram_id": 2002, "text": "продам мефедрон недорого, пишите"})
        check(r.status_code == 403, "продажа вещества блокируется", r.text)
        async with async_session() as s:
            bob = (await s.execute(select(User).where(User.telegram_id == 2002))).scalar_one()
            check(bob.is_muted, "автор замучен после продажи вещества")

        print("\n[4] PII-фильтр — блокирует телефон")
        await c.post("/api/auth/telegram/dev", json={"telegram_id": 2003, "username": "carl"})
        r = await c.post("/api/chat/send", json={"telegram_id": 2003, "text": "звоните мне +7 921 555 12 34 по любым вопросам"})
        check(r.status_code == 403, "телефон блокируется", r.text)
        async with async_session() as s:
            carl = (await s.execute(select(User).where(User.telegram_id == 2003))).scalar_one()
            check(carl.is_muted, "автор замучен после попытки слить телефон")

        print("\n[5] Кейс-батл реклама блокируется")
        await c.post("/api/auth/telegram/dev", json={"telegram_id": 2004, "username": "dave"})
        r = await c.post("/api/chat/send", json={"telegram_id": 2004, "text": "заходи на CSGOLIVE го дропать скины"})
        check(r.status_code == 403, "реклама кейс-батл сайта блокируется", r.text)

        print("\n[6] Удаление своего сообщения")
        r = await c.post("/api/chat/delete", json={"telegram_id": 2001, "message_id": msg_id})
        check(r.status_code == 200, "автор может удалить своё сообщение", r.text)

        r = await c.get("/api/chat/messages", params={"telegram_id": 2002, "after_id": 0})
        ids = [m["id"] for m in r.json()["messages"]]
        check(msg_id not in ids, "удалённое сообщение больше не отдаётся в ленте")
        check(msg_id in r.json().get("removed_ids", []), "удалённое сообщение попало в removed_ids для реалтайм-удаления")

        print("\n[7] Нельзя удалить чужое сообщение")
        await c.post("/api/auth/telegram/dev", json={"telegram_id": 2005, "username": "eve"})
        r2 = await c.post("/api/chat/send", json={"telegram_id": 2005, "text": "чужое сообщение"})
        other_id = r2.json()["message"]["id"]
        r = await c.post("/api/chat/delete", json={"telegram_id": 2001, "message_id": other_id})
        check(r.status_code == 403, "чужое сообщение удалить нельзя", r.text)

        print("\n[8] Публичный профиль по клику (используется чатом для 'Посмотреть профиль')")
        r = await c.get("/api/friends/profile", params={"telegram_id": 2001, "target_telegram_id": 2005})
        check(r.status_code == 200, "публичный профиль открывается", r.text)
        body = r.json()
        check("relation_state" in body and "stats" in body and "showcase" in body,
              "профиль содержит relation_state/stats/showcase", list(body)[:20])

    print(f"\n{'='*50}\n{'ВСЕ ПРОШЛИ' if not FAIL else str(len(FAIL)) + ' ПРОВАЛЕНО: ' + ', '.join(FAIL)}\n{'='*50}")
    sys.exit(1 if FAIL else 0)

asyncio.run(run())
