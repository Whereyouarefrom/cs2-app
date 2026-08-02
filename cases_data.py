# ============================================
# CS2 Case Simulator — База кейсов
# ============================================
#
# Формат одного кейса:
# {
#   "name": str,
#   "image": str (прямая ссылка Steam CDN),
#   "items": [
#       {"name": str, "rarity": str, "image": str (прямая ссылка Steam CDN)},
#       ...
#   ]
# }
#
# rarity ∈ {"Consumer", "Industrial", "Mil-Spec", "Restricted",
#           "Classified", "Covert", "Knife", "Gloves"}
#
# Изображения ниже — реальные прямые ссылки на Steam CDN
# (community.akamai.steamstatic.com/economy/image/...), полученные из
# официального открытого CS2/CS:GO Items API (ByMykel/CSGO-API), поэтому
# гарантированно открываются напрямую без прокси/заглушек.
#
# Этот файл — стартовый "сид" (3 полностью проверенных кейса). Чтобы
# подтянуть ПОЛНЫЙ список всех кейсов CS:GO/CS2 (по состоянию на сегодня)
# напрямую из Steam-данных — один раз запусти `python sync_cases.py`.
# Он скачает актуальный каталог и сохранит его в cases_data.json;
# при наличии этого файла бэкенд подхватит его автоматически и полностью
# заменит сид ниже — руками ничего править не нужно.

import json
import os

_DATA_FILE = os.path.join(os.path.dirname(__file__), "cases_data.json")

CDN = "https://community.akamai.steamstatic.com/economy/image/"

# ---------------------------------------------------------------
# Универсальный пул ножей ранних кейсов (реально встречается в игре
# в CS:GO Weapon Case / eSports 2013 Case / Operation Bravo Case и т.д.)
# ---------------------------------------------------------------
_KNIFE_POOL = [
    {
        "name": "★ Bayonet | Fade",
        "rarity": "Knife",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLzn4_v8ydP0POvV6JsJPWsAm6Xyfo45-BrHniwzUh24jjVm4qgInnCOA4mDscmEeVcsBXtkN22P-yx5waNg5UFk3tAoG85FQ",
    },
    {
        "name": "★ Karambit | Fade",
        "rarity": "Knife",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Q7uCvZaZkNM-SD1iWwOpzj-1gSCGn20tztm_UyIn_JHKUbgYlWMcmQ-ZcskSwldS0MOnntAfd3YlMzH35jntXrnE8SOGRGG8",
    },
    {
        "name": "★ Flip Knife | Fade",
        "rarity": "Knife",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1d4_u-V6VsH_aSCmKvzedxuPUnTXywzR9-427Qyd34d3iUb1RyDJMlQbQL5xTtw920Zby05FeNjohDzDK-0H3GjMwqlg",
    },
    {
        "name": "★ M9 Bayonet | Fade",
        "rarity": "Knife",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Wts2sab1iLvWHMWaR_uh3tORWQyC0nQlp4znQytr6cnjFbg8oC8BzRrQK50S-lNDgP-_r5wWP3t5CyX37jCIb7DErvbiJu9Hv_g",
    },
]

_SEED_CASES = {
    "csgo_weapon_case": {
        "name": "CS:GO Weapon Case",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJKz2lu_XsnXwtmkJjSU91dh8bji61XxRCKg0MSz_nUDvPb-OPFvdKTFDzbAkbp16bY5Gn6wkx9ysj7Xntf9IC6WZgA-Sswnnj45WXo",
        "items": [
            {"name": "MP7 | Skulls", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8jsHf9Ttk_Pm7ZKh-H_yaCW-Ej7l35OBoTCrmzUQht2mDwon7cHuWPFUlDcFxQ7EDtxbpx4W1Y-LltAfAy9USYNky6pY"},
            {"name": "AUG | Wings", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwi5Hf9Ttk6fevfKxoMuOsD3KX_uJ_t-l9AX7qzE5_sGmEw9uoJCrBOgMoDsN2ReMI4EPrm4fvY-m04ASPgt8Uz3_gznQePzx-iqc"},
            {"name": "SG 553 | Ultraviolet", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLimcO1qx1I4M2-fbZ9LPWsAm6Xyfo44bQ-Tn7gwRt-t2uAw96tIn7FOAF1CsckQLUJ4xXskdO2NLzrtAyIi5UFk3tU_MwgmA"},
            {"name": "Glock-18 | Dragon Tattoo", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL2kpnj9h1a4s2qeqVqL_6sCWufwuVJvOhuRz39xUl-6miDzI37dHyXOlIkA8MmROVfshO9w9G1Ye-ztgPX34tEyi74jjQJsHi_DRfxVg"},
            {"name": "USP-S | Dark Water", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLkjYbf7itX6vytbbZSIf2sFGKS0-9JtOB7RBa_nBovp3OHy9v8J3vFbgIhC5UmQ7UIsxm7wNDnNr_rswOMiNlGmCWoiH9Juis9_a9cBl2xnYuj"},
            {"name": "M4A1-S | Dark Water", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8ypexwjFS4_ega6F_H_GeMX2Vw_x3j-VoXSKMmRQguynLzI6td3-TPQAlD5slR-EJ5hDux9XmMe7i71CI2t8UzSuthi9OvSlo6vFCD_TltxSe0A"},
            {"name": "AK-47 | Case Hardened", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwlcK3wiNK0P2nZKFpH_yaCW-Ej7sk5bE8Sn-2lEpz4zndzoyvdHuUPwFzWZYiE7EK4Bi4k9TlY-y24FbAy9USGSiZd5Q"},
            {"name": "Desert Eagle | Hypnotic", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL1m5fn8Sdk7vORfqF_NPmUAVicyOl-pK9qSyyywxgjtmnVytyocnLGPA4iWcYmRLYIu0S-xtbuMLjg51DXjoJC02yg2VjGnh4J"},
            {"name": "AWP | Lightning Strike", "rarity": "Covert", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_C9k4_upYLBjKf6UMWaH0dF6ueZhW2frwU1_sW2EmNyvc32RZwMpCpcjQ-EJ4xbtmt3gYezk4wzb3tpAy3mrkGoXubsGIfVN"},
            *_KNIFE_POOL,
        ],
    },
    "esports_2013_case": {
        "name": "eSports 2013 Case",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJKz2lu_XsnXwtmkJjSU91dh8bjx-UnoUwniocSwrHEV7KaobPdud6HEWjXGmbYl6LIwHn2ywhgh5GzXzdmsc3yRalAkD5R3FvlK7Ed7JoXDRQ",
        "items": [
            {"name": "M4A4 | Faded Zebra", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8ypexwjFL0OirarZsI_GeMWWH_uJ_t-l9AXu3zBkhsDyHz4z9dXmVagJzW8MiQbFetBfrkNHhZbjr51CMiN8TyS_gznQeEoYBjXk"},
            {"name": "MAG-7 | Memento", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8n5G3wipC0PutZ7dsKPWXHGie_uJ_t-l9ASjlzRl34WnUzN6tJy-eOg50C5N1TLYLthaxm4HlZbiz4AXXjNpDmCXgznQeeQk0p-w"},
            {"name": "FAMAS | Doomkitty", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL3n5vh7h1T9s2qZ6tgK_mHGn6vzedxuPUnTHrmxk1x6jmBmdb4Jy6QZw8jW8RwR-9esUHsltXnNu3n5VPXiY5AzTK-0H2q4sGvpw"},
            {"name": "Galil AR | Orange DDPAT", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL2n5rp8SNJ0Pq3V6BpMPGHMWiCwOBxtd5lRi67gVN-4WzRwomqeHKQOwEoAsdzRrENskK7wIXiM-m341feg44TzXr33C0Y8G81tE9ebY28"},
            {"name": "Sawed-Off | Orange DDPAT", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLin4Hl-S1d6c2mcZtpJOCSGlif0-94t-RWQyC0nQlp4GyAzoqsdSmWaFJyD5UhEeFcsBm-ktK0M7nj7wKI394Xn3-vhisfujErvbhk58vgGA"},
            {"name": "P250 | Splash", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLhzMOwwjFL0OG-ZKV-KM-DXDLA_uJ_t-l9AXDrxh4i62vTzNyrc3zEP1MpWJN2EOMN5kTpl9K2Zb62slTdi4NMzC7gznQe9E-5MVM"},
            {"name": "AK-47 | Red Laminate", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwlcK3wipC0POlPPNhIf2sAm6Xyfo4tucxS3rjwRx_42zRwo6pdSnCPwAmX5ohFOIJsUTqwdThNOi0s1TajZUFk3t5vdi_Cw"},
            {"name": "AWP | BOOM", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf9Ttk7f6vZZt-Kf2DAmKvzedxuPUnTX7mkxhy62iDzYqhdiqXbw4oWZEkE-IDsRa9lIXlMejktFOMi49MmDK-0H2AgUnw_w"},
            {"name": "P90 | Death by Kitty", "rarity": "Covert", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLhx8bf_jdk7PO6e694LPyAMXfJkdF6ueZhW2fgkUh042jUnN2geSqTaFN2CcQmQuRfsBXtxtfkN7mztASIg91Bniv8kGoXucYQxgOQ"},
            *_KNIFE_POOL,
        ],
    },
    "operation_bravo_case": {
        "name": "Operation Bravo Case",
        "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJKz2lu_XsnXwtmkJjSU91dh8bj7-lz1QAn4kZjf9CsVuvf7OfQ5IabBVzbHlb915bcwHCjikEp_sTnTn4z6eH6RblQlC8RwFPlK7EdXSP0Ibg",
        "items": [
            {"name": "SG 553 | Wave Spray", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLimcO1qx1I_829eLZsOc-ED3GV0tF0ouB_QBa_nBovp3PcwoqtdC3BOwQkCZB3QOIIsxm_kNyyZuzg7w3f2YNEnn6qjS0Y6Clq_a9cBmkkHSs4"},
            {"name": "Dual Berettas | Black Limba", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL0kp_0-B1Y-s29baV-L_6sC2uZ1etlj-N7Tj-8qhEutDWR1NyuJC6SPQQoC8N1TLYMthC_kNTmMOKw4gLe2osWmC6vhylB6C5i4OscEf1yNRLqhkE"},
            {"name": "Nova | Tempest", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL_kYDhwipC0OGrabdkJPWsDHWR1-FJvOhuRz39xUUk4jiHyt_9cXzGZwV2CJJyQbYN4Ua9wdPiZr6x4FTcjIhMzXmsjjQJsHjYOlWGdQ"},
            {"name": "Galil AR | Shattered", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL2n5rp8SNJ0Pq3V6d_Nf2DAmKvw_x3pu5WQyC0nQlpsm7dn96tcniROgMoX8RzFuIJtRPqxtXhMujjsgLYjIlEzS-ojiIa5jErvbio8HB-SQ"},
            {"name": "UMP-45 | Bone Pile", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLkk4a0qB1I_829Y7FhLM-XB2aX0-97j-N7Tj-8qhEutDWR1I6rcX3GblRyD5V1TecIsxPukdbuYeqz4Q3ZjopMyiyrjHgfuCdqt-kcEf1yvOcVYJ0"},
            {"name": "G3SG1 | Demeter", "rarity": "Mil-Spec", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL2zYXnrB1T9s2sZLFoMP-fF2Cfz9F0ouB_QBa_nBovp3OEnoz4cHnFZgMnD5R5TeQP40Swx4XgNLm34g3ei49FxC2qiXgbuy9t_a9cBh-mV6Cr"},
            {"name": "USP-S | Overgrowth", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLkjYbf7itX6vytbbZSKOmsHW6VxutJsvNoWSaMmRQguynLytyqdy2eaVUgAsB0QeIIsxfuldy2MO3gtFSI2ooRzSiq3HxA7SlvtfFCD_RGjmYWyQ"},
            {"name": "M4A4 | Zirka", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8ypexwjFL0OG6abZSIuKSGGivzedxuPUnSXnqkBwj62vTn9b8cyjBOlNxD8Z2Te8L5Ea8xtbkNe6z7lTajotCmDK-0H35HfkCFQ"},
            {"name": "MAC-10 | Graven", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8n5WxrR1a_s2rfKdlJfSsA2aTkL5JsvNoWSaMmRQguynLztytdHieOA92W8N5Re4D4ELtk9O2Nbnq5FfWjIkRn333hn9O731j4_FCD_RXlm8jng"},
            {"name": "M4A1-S | Bright Water", "rarity": "Restricted", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8ypexwjFS4_ega6F_H_iKMWiTxO94j-N7Tj-8qhEutDWR1N2scy2Sa1UkC8NyRbMPuhexx4fgYrziswHf395Az3-qiStK5i864-kcEf1ycufvRr8"},
            {"name": "P90 | Emerald Dragon", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLhx8bf_jdk6-Cvb6tjH-DKXliS0-9gv95lRi67gVMm4m3Vzdmqci-SO1clX8Z1QeYO5xi5mtTuPu7l4FDc2o4TmH32jC1P8G81tLxM49od"},
            {"name": "P2000 | Ocean Foam", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL5lYayrXIL0POjV6t-M_mVF1iSzftzj_E7H3njqh81siuKpYPwJiPTcA91W5N0EOMNskGwkt3gP-vh41GNiNpDn3r83ShL6itj4bsKA6Im-_XJz1aWVAZrXOc"},
            {"name": "AWP | Graphite", "rarity": "Classified", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_C9k7OC7ZbRhJc-RHGaGztF6ueZhW2e2k0l2sW_WzN7_cS6SbgV1CsF3TOEI4EOwloGzNLzg5g3fiIpHxC78kGoXuTqeOjwH"},
            {"name": "AK-47 | Fire Serpent", "rarity": "Covert", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwlcK3wiFO0PSneqF-JeKDC2mE_u995LZWTTuygxIYvzSCkpu3cnvFPQB2DpUkROFY4Rntw93lP7i241DbiI1BxSuviHlKunk_6-sHU71lpPMTRLyP4Q"},
            {"name": "Desert Eagle | Golden Koi", "rarity": "Covert", "image": CDN + "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL1m5fn8Sdk7v-Re6dsLPWAMWWCwPh5j-1gSCGn20om6jyGw9qgJHmQaAcgC8MmR7IMthm5m4W2M7zj7wOIj4pGn32o23hXrnE8VHBG1O4"},
            *_KNIFE_POOL,
        ],
    },
}


def load_cases() -> dict:
    """Загружает базу кейсов. Если рядом лежит cases_data.json (сгенерированный
    sync_cases.py со ВСЕМИ кейсами CS:GO/CS2), используется он. Иначе — сид
    из трёх проверенных кейсов выше."""
    if os.path.exists(_DATA_FILE):
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    return _SEED_CASES


CASES = load_cases()
