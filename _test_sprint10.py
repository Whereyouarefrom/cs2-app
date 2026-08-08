"""E2E проверка Спринта 10 против реального ASGI-приложения (временный файл)."""
import asyncio, os, sys
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_s10.db"
if os.path.exists("test_s10.db"): os.remove("test_s10.db")

import httpx
import main, levels, cosmetics
from database import async_session, init_db, User, Inventory
from sqlalchemy import select

FAIL = []
def check(cond, label, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   -> {extra}" if extra and not cond else ""))
    if not cond: FAIL.append(label)

async def run():
    await init_db()
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        print("\n[1] Авторизация и профиль")
        r1 = await c.post("/api/auth/telegram/dev", json={"telegram_id": 1001, "username": "alice"})
        if r1.status_code != 200:
            print("AUTH FAILED", r1.status_code, r1.text[:3000]); return
        prof = r1.json()
        check("level" in prof, "профиль содержит level", list(prof)[:20])
        check(prof["level"]["level"] == 1, "новый игрок = уровень 1", prof.get("level"))
        check(prof["level"]["xp_needed"] == 100, "порог 1->2 = 100 XP", prof["level"])
        check(prof["showcase"]["slots"] == 3, "базовая витрина = 3 слота", prof["showcase"])
        check(prof["showcase"]["max_slots"] == 10, "максимум витрины = 10")
        check(prof["showcase"]["next_slot_level"] == 5, "следующий слот на 5 уровне", prof["showcase"]["next_slot_level"])
        keys = {t["key"] for t in prof["titles"]}
        check({"knifeman", "magnate", "lucky"} <= keys, "есть Ножеман/Магнат/Счастливчик", keys)
        check(all(not t["unlocked"] for t in prof["titles"] if t["key"] in {"knifeman","magnate","lucky"}),
              "три титула изначально закрыты")

        await c.post("/api/auth/telegram/dev", json={"telegram_id": 1002, "username": "bob"})

        print("\n[2] Уровень аккаунта от XP")
        async with async_session() as s:
            u = (await s.execute(select(User).where(User.telegram_id == 1001))).scalar_one()
            uid = u.id
            u.xp = levels.total_xp_for_level(12)
            await s.commit()
        prof = (await c.get("/api/user/profile", params={"telegram_id": 1001})).json()
        check(prof["level"]["level"] == 12, "xp порога 12 уровня -> уровень 12", prof["level"]["level"])
        check(prof["showcase"]["slots"] == 5, "12 уровень -> 3+2 = 5 слотов", prof["showcase"]["slots"])
        check(prof["showcase"]["next_slot_level"] == 15, "следующий слот на 15", prof["showcase"]["next_slot_level"])

        print("\n[3] Авто-разблокировка титулов")
        async with async_session() as s:
            u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            for _ in range(cosmetics.KNIFEMAN_REQUIRED_KNIVES):
                main._maybe_update_top_drop(u, {"name": "Karambit", "price": 90000, "rarity": "Knife", "image": ""})
            await s.commit()
        prof = (await c.get("/api/user/profile", params={"telegram_id": 1001})).json()
        tmap = {t["key"]: t for t in prof["titles"]}
        check(tmap["knifeman"]["unlocked"], "«Ножеман» открылся после дропов ножей", tmap["knifeman"])
        check(not tmap["lucky"]["unlocked"], "«Счастливчик» пока закрыт")

        r = await c.post("/api/profile/select-title", json={"telegram_id": 1001, "key": "knifeman"})
        check(r.status_code == 200 and r.json()["selected_title"] == "knifeman", "выбор открытого титула", r.text[:200])
        r = await c.post("/api/profile/select-title", json={"telegram_id": 1001, "key": "lucky"})
        check(r.status_code == 403, "выбор ЗАКРЫТОГО титула отклонён (403)", r.status_code)
        r = await c.post("/api/profile/select-title", json={"telegram_id": 1001, "key": "nope"})
        check(r.status_code == 400, "неизвестный титул отклонён (400)", r.status_code)
        r = await c.post("/api/profile/select-title", json={"telegram_id": 1001, "key": None})
        check(r.status_code == 200 and r.json()["selected_title"] is None, "снятие титула разрешено", r.text[:200])
        await c.post("/api/profile/select-title", json={"telegram_id": 1001, "key": "knifeman"})

        r = await c.get("/api/profile/cosmetics", params={"telegram_id": 1001})
        check(r.status_code == 200 and "frames" in r.json(), "каталог косметики", r.text[:200])
        fr = {f["key"]: f for f in r.json()["frames"]}
        unlocked_frame = next((k for k, v in fr.items() if v["unlocked"]), None)
        check(unlocked_frame is not None, "есть открытая рамка на 12 уровне", list(fr))
        if unlocked_frame:
            r = await c.post("/api/profile/select-frame", json={"telegram_id": 1001, "key": unlocked_frame})
            check(r.status_code == 200, "выбор рамки", r.text[:200])
        r = await c.post("/api/profile/select-frame", json={"telegram_id": 1001, "key": "fake"})
        check(r.status_code == 403, "закрытая рамка отклонена", r.status_code)

        print("\n[4] Витрина и StatTrak")
        inv_ids = []
        async with async_session() as s:
            for i in range(7):
                it = Inventory(user_id=uid, skin_name=f"Skin {i}", skin_price=100*(i+1), rarity="Covert",
                               quality="FN", stattrak=(i == 0), stattrak_count=0, float_val=0.013412,
                               image_url="", obtained_from_case="test")
                s.add(it); await s.flush(); inv_ids.append(it.id)
            await s.commit()

        r = await c.get("/api/inventory", params={"telegram_id": 1001})
        inv = r.json()["inventory"]
        st = next(i for i in inv if i["stattrak"])
        check(all(k in st for k in ("float_val","stattrak_count","quality_name")),
              "инвентарь отдаёт float/stattrak_count/quality_name", list(st))
        check(st["float_val"] == 0.013412, "точный float доезжает до фронта", st["float_val"])
        check(st["quality_name"] == "Factory New", "полное имя качества", st["quality_name"])

        for iid in inv_ids[:5]:
            r = await c.post("/api/profile/showcase/add", json={"telegram_id": 1001, "inventory_id": iid})
        check(r.status_code == 200 and r.json()["used"] == 5, "5 скинов помещаются в 5 слотов", r.text[:300])
        r = await c.post("/api/profile/showcase/add", json={"telegram_id": 1001, "inventory_id": inv_ids[5]})
        check(r.status_code == 400, "6-й скин отклонён — витрина полна", r.status_code)

        async with async_session() as s:
            u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
            await main._award_xp(s, u, 10)
            await s.commit()
        r = await c.get("/api/profile/showcase", params={"telegram_id": 1001})
        st_item = next((i for i in r.json()["items"] if i["stattrak"]), None)
        check(st_item and st_item["stattrak_count"] == 1, "счётчик StatTrak вырос от активности", st_item)

        r = await c.post("/api/profile/showcase/remove", json={"telegram_id": 1001, "inventory_id": inv_ids[0]})
        check(r.status_code == 200 and r.json()["used"] == 4, "удаление из витрины", r.text[:300])
        r = await c.post("/api/profile/showcase/add", json={"telegram_id": 1002, "inventory_id": inv_ids[1]})
        check(r.status_code == 404, "чужой предмет в витрину нельзя (404)", r.status_code)

        print("\n[5] События повышения уровня")
        async with async_session() as s:
            u = (await s.execute(select(User).where(User.telegram_id == 1002))).scalar_one()
            res = await main._award_xp(s, u, levels.total_xp_for_level(6))
            await s.commit()
        check(res["level"] == 6, "_award_xp вернул новый уровень", res["level"])
        check(len(res["level_up"]) == 5, "5 событий повышения (1->6)", len(res["level_up"]))
        gained = [e for e in res["level_up"] if e["showcase_slot_gained"]]
        check(len(gained) == 1 and gained[0]["level"] == 5, "слот витрины выдан ровно на 5 уровне", gained)

        print("\n[6] Модуль Друзья")
        r = await c.get("/api/friends/search", params={"telegram_id": 1001, "q": "bob"})
        check(r.status_code == 200 and len(r.json()["results"]) == 1, "поиск по username", r.text[:300])
        check(r.json()["results"][0]["relation_state"] == "none", "состояние связи = none")
        r = await c.get("/api/friends/search", params={"telegram_id": 1001, "q": "1002"})
        check(r.status_code == 200 and len(r.json()["results"]) == 1, "поиск по TG ID", r.text[:300])
        r = await c.get("/api/friends/search", params={"telegram_id": 1001, "q": "alice"})
        check(len(r.json()["results"]) == 0, "себя в поиске нет", r.json()["results"])
        r = await c.get("/api/friends/search", params={"telegram_id": 1001, "q": "a"})
        check(r.status_code == 400, "запрос из 1 символа отклонён", r.status_code)

        r = await c.post("/api/friends/request", json={"telegram_id": 1001, "target_telegram_id": 1002})
        check(r.status_code == 200 and r.json()["state"] == "request_sent", "заявка отправлена", r.text[:300])
        req_id = r.json()["request_id"]
        r = await c.post("/api/friends/request", json={"telegram_id": 1001, "target_telegram_id": 1002})
        check(r.status_code == 400, "дубль заявки отклонён", r.status_code)
        r = await c.post("/api/friends/request", json={"telegram_id": 1001, "target_telegram_id": 1001})
        check(r.status_code == 400, "заявка себе отклонена", r.status_code)

        r = await c.get("/api/friends/requests", params={"telegram_id": 1002})
        check(len(r.json()["incoming"]) == 1, "входящая заявка у получателя", r.text[:300])
        r = await c.get("/api/friends/requests", params={"telegram_id": 1001})
        check(len(r.json()["outgoing"]) == 1, "исходящая заявка у отправителя")

        r = await c.post("/api/friends/respond", json={"telegram_id": 1001, "request_id": req_id, "action": "accept"})
        check(r.status_code == 403, "отправитель не может принять свою заявку", r.status_code)
        r = await c.post("/api/friends/respond", json={"telegram_id": 1002, "request_id": req_id, "action": "accept"})
        check(r.status_code == 200 and r.json()["state"] == "friends", "получатель принял заявку", r.text[:300])
        r = await c.post("/api/friends/respond", json={"telegram_id": 1002, "request_id": req_id, "action": "accept"})
        check(r.status_code == 400, "повторный ответ отклонён", r.status_code)

        r = await c.get("/api/friends/list", params={"telegram_id": 1001})
        check(r.json()["count"] == 1, "друг в списке у A", r.text[:300])
        r = await c.get("/api/friends/list", params={"telegram_id": 1002})
        check(r.json()["count"] == 1, "дружба ненаправленная — друг и у B")

        r = await c.get("/api/friends/profile", params={"telegram_id": 1002, "target_telegram_id": 1001})
        check(r.status_code == 200, "публичная карточка отдана", r.text[:400])
        pub = r.json()
        check(pub["relation_state"] == "friends", "состояние в карточке = friends")
        leaked = [k for k in pub if k in ("balance","gold_balance","referral_code","referral_earnings","inventory")]
        check(not leaked, "приватных полей в публичной карточке НЕТ", leaked)
        check(pub["selected_title"] == "knifeman", "титул виден в карточке", pub.get("selected_title"))
        check(len(pub["showcase"]["items"]) == 4, "витрина видна в карточке", len(pub["showcase"]["items"]))
        # 7 тестовых скинов + предметы, начисленные ранговой наградой при
        # выставлении XP 12-го уровня — точное число зависит от наград ranks.py,
        # поэтому проверяем только что статистика реально заполнена.
        check(pub["stats"]["inventory_count"] >= 7 and pub["stats"]["knife_drops_count"] == 1,
              "статистика в карточке", pub["stats"])

        r = await c.post("/api/friends/remove", json={"telegram_id": 1002, "friend_telegram_id": 1001})
        check(r.status_code == 200, "удаление из друзей", r.text[:300])
        r = await c.get("/api/friends/list", params={"telegram_id": 1001})
        check(r.json()["count"] == 0, "после удаления список пуст")
        r = await c.post("/api/friends/request", json={"telegram_id": 1002, "target_telegram_id": 1001})
        check(r.status_code == 200, "после удаления можно добавить заново", r.text[:300])
        r = await c.post("/api/friends/request", json={"telegram_id": 1001, "target_telegram_id": 1002})
        check(r.status_code == 200 and r.json()["state"] == "friends", "встречная заявка = сразу дружба", r.text[:300])

        print("\n[7] Справка по уровням")
        r = await c.get("/api/profile/levels", params={"telegram_id": 1001, "up_to": 20})
        check(r.status_code == 200 and len(r.json()["table"]) == 20, "таблица уровней", r.text[:200])

    print("\n" + "=" * 55)
    print("ПРОВАЛЕНО: " + (", ".join(FAIL) if FAIL else "нет — все проверки пройдены"))
    print("=" * 55)

asyncio.run(run())
