// ============================================
// CS2 Case Simulator — Frontend Logic
// ============================================

const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const API_BASE = "https://cs2-app.onrender.com/api"; // замени на реальный адрес FastAPI
const ADSGRAM_BLOCK_ID = "your_adsgram_block_id"; // подставь свой Block ID из adsgram.ai

const state = {
  telegramId: tg?.initDataUnsafe?.user?.id || 123456789, // фолбэк для теста вне Telegram
  username: tg?.initDataUnsafe?.user?.first_name || "Игрок",
  balance: 0,
  isVip: false,
  cases: [],
  inventory: [],
  casesOpenedSinceAd: 0,
  currentCase: null,
  pendingDrop: null,
};

// ============================================
// Утилиты
// ============================================
function fmt(n) {
  return "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function rarityClass(rarity) {
  return "r-" + rarity.replace(" ", "-");
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Ошибка запроса" }));
    throw new Error(err.detail || "Ошибка запроса");
  }
  return res.json();
}

function playSound(id) {
  const el = document.getElementById(id);
  if (el && el.src) { el.currentTime = 0; el.play().catch(() => {}); }
}

// ============================================
// Навигация по табам
// ============================================
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchScreen(btn.dataset.screen));
});

function switchScreen(name) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`screen-${name}`).classList.add("active");
  document.querySelector(`.tab-btn[data-screen="${name}"]`).classList.add("active");

  if (name === "inventory") loadInventory();
  if (name === "profile") loadProfile();
  if (name === "minigames") populateUpgradeSelect();
}

// ============================================
// Загрузка кейсов
// ============================================
async function loadCases() {
  try {
    const data = await apiGet("/cases");
    state.cases = data.cases;
    renderCases();
  } catch (e) {
    console.error("Ошибка загрузки кейсов:", e);
  }
}

function renderCases() {
  const grid = document.getElementById("cases-grid");
  grid.innerHTML = "";
  state.cases.forEach(c => {
    const card = document.createElement("div");
    card.className = "case-card";
    card.innerHTML = `
      <img src="${c.image}" alt="${c.name}" loading="lazy">
      <div class="case-card-name">${c.name}</div>
      <div class="case-card-price">${fmt(c.price)}</div>
    `;
    card.addEventListener("click", () => openCaseModal(c));
    grid.appendChild(card);
  });
}

// ============================================
// Модалка кейса
// ============================================
function openCaseModal(caseData) {
  state.currentCase = caseData;

  document.getElementById("modal-case-image").src = caseData.image;
  document.getElementById("modal-case-name").textContent = caseData.name;
  document.getElementById("modal-case-price").textContent = fmt(caseData.price);

  const preview = document.getElementById("modal-items-preview");
  preview.innerHTML = "";
  caseData.items.slice(0, 6).forEach(item => {
    const el = document.createElement("div");
    el.className = `preview-item ${rarityClass(item.rarity)}`;
    el.innerHTML = `
      <img src="${skinImageUrl(item.name)}" alt="${item.name}" loading="lazy">
      <div class="preview-item-name">${item.name}</div>
    `;
    preview.appendChild(el);
  });

  document.getElementById("roulette-wrapper").style.display = "none";
  document.getElementById("case-modal").classList.add("active");
}

document.getElementById("case-modal-close").addEventListener("click", () => {
  document.getElementById("case-modal").classList.remove("active");
});

// Заглушка генерации CDN-ссылки скина (в реальном проекте — маппинг имя -> hash Steam CDN)
function skinImageUrl(skinName) {
  const seed = encodeURIComponent(skinName);
  return `https://community.cloudflare.steamstatic.com/economy/image/placeholder/${seed}`;
}

// ============================================
// Открытие кейса + анимация рулетки
// ============================================
document.getElementById("open-case-btn").addEventListener("click", async () => {
  if (!state.currentCase) return;

  if (state.balance < state.currentCase.price) {
    tg?.showAlert?.("Недостаточно баланса. Посмотри рекламу на вкладке «Заработать»!");
    return;
  }

  try {
    const result = await apiPost("/open-case", {
      telegram_id: state.telegramId,
      case_key: state.currentCase.key,
    });

    state.balance = result.new_balance;
    updateBalanceDisplay();
    state.pendingDrop = result.drop;

    runRouletteAnimation(state.currentCase, result.drop);

    state.casesOpenedSinceAd++;
    maybeShowInterstitial();
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

function runRouletteAnimation(caseData, drop) {
  const wrapper = document.getElementById("roulette-wrapper");
  const track = document.getElementById("roulette-track");
  wrapper.style.display = "block";
  track.innerHTML = "";
  track.style.transition = "none";
  track.style.transform = "translateX(0)";

  // Собираем длинную ленту случайных предметов + выпавший в конце на нужной позиции
  const REEL_LENGTH = 40;
  const WINNING_INDEX = 32; // где остановится указатель

  const pool = caseData.items;
  const reel = [];
  for (let i = 0; i < REEL_LENGTH; i++) {
    if (i === WINNING_INDEX) {
      reel.push(drop);
    } else {
      reel.push(pool[Math.floor(Math.random() * pool.length)]);
    }
  }

  reel.forEach(item => {
    const el = document.createElement("div");
    el.className = `roulette-item ${rarityClass(item.rarity)}`;
    el.innerHTML = `
      <img src="${skinImageUrl(item.name)}" alt="${item.name}">
      <span>${item.name}</span>
    `;
    track.appendChild(el);
  });

  const itemWidth = 102; // 90px width + 2*6px margin
  const wrapperWidth = wrapper.offsetWidth;
  const targetOffset = WINNING_INDEX * itemWidth - wrapperWidth / 2 + itemWidth / 2;
  // небольшой случайный сдвиг внутри карточки для естественности
  const jitter = (Math.random() - 0.5) * 40;

  requestAnimationFrame(() => {
    track.style.transition = "transform 4.2s cubic-bezier(0.12, 0.85, 0.15, 1)";
    track.style.transform = `translateX(-${targetOffset + jitter}px)`;
    playSound("sound-spin");
  });

  setTimeout(() => {
    playSound("sound-win");
    showWinModal(drop);
  }, 4400);
}

// ============================================
// Окно победы
// ============================================
function showWinModal(drop) {
  document.getElementById("case-modal").classList.remove("active");

  document.getElementById("win-item-image").src = skinImageUrl(drop.name);
  document.getElementById("win-item-name").textContent =
    drop.name + (drop.stattrak ? " (StatTrak™)" : "");
  document.getElementById("win-item-price").textContent = fmt(drop.price);

  const card = document.getElementById("win-item-card");
  const rarityVarMap = {
    "Consumer": "--rarity-consumer",
    "Industrial": "--rarity-industrial",
    "Mil-Spec": "--rarity-milspec",
    "Restricted": "--rarity-restricted",
    "Classified": "--rarity-classified",
    "Covert": "--rarity-covert",
    "Knife": "--rarity-knife",
  };
  const varName = rarityVarMap[drop.rarity] || "--rarity-covert";
  card.style.borderColor = getComputedStyle(document.documentElement).getPropertyValue(varName) || "#eb4b4b";

  document.getElementById("win-modal").classList.add("active");
}

document.getElementById("win-keep-btn").addEventListener("click", () => {
  document.getElementById("win-modal").classList.remove("active");
  state.pendingDrop = null;
  loadProfile();
});

document.getElementById("win-sell-btn").addEventListener("click", async () => {
  if (!state.pendingDrop) return;
  try {
    const result = await apiPost("/sell-skin", {
      telegram_id: state.telegramId,
      inventory_id: state.pendingDrop.id,
    });
    state.balance = result.new_balance;
    updateBalanceDisplay();
  } catch (e) {
    tg?.showAlert?.(e.message);
  } finally {
    document.getElementById("win-modal").classList.remove("active");
    state.pendingDrop = null;
  }
});

// ============================================
// Инвентарь
// ============================================
async function loadInventory() {
  try {
    const data = await apiGet(`/inventory?telegram_id=${state.telegramId}`);
    state.inventory = data.inventory;
    renderInventory();
  } catch (e) {
    console.error("Ошибка загрузки инвентаря:", e);
  }
}

function renderInventory() {
  const grid = document.getElementById("inventory-grid");
  const empty = document.getElementById("inventory-empty");

  if (!state.inventory.length) {
    grid.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  grid.innerHTML = "";
  state.inventory.forEach(item => {
    const card = document.createElement("div");
    card.className = "inventory-card";
    card.innerHTML = `
      <img src="${skinImageUrl(item.name)}" alt="${item.name}">
      <div class="inventory-card-name">${item.name}</div>
      <div class="rarity-bar ${rarityClass(item.rarity)}"></div>
      <div class="inventory-card-price">${fmt(item.price)}</div>
      <button class="sell-btn" data-id="${item.id}">Продать</button>
    `;
    grid.appendChild(card);
  });

  grid.querySelectorAll(".sell-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.id);
      try {
        const result = await apiPost("/sell-skin", {
          telegram_id: state.telegramId,
          inventory_id: id,
        });
        state.balance = result.new_balance;
        state.inventory = state.inventory.filter(i => i.id !== id);
        updateBalanceDisplay();
        renderInventory();
      } catch (e) {
        tg?.showAlert?.(e.message);
      }
    });
  });
}

// ============================================
// Профиль
// ============================================
async function loadProfile() {
  try {
    const profile = await apiGet(`/user/profile?telegram_id=${state.telegramId}`);

    state.balance = profile.balance;
    state.isVip = profile.is_vip;
    updateBalanceDisplay();

    document.getElementById("profile-name").textContent = state.username;
    document.getElementById("stat-cases").textContent = profile.total_cases_opened;
    document.getElementById("stat-inventory-value").textContent = fmt(profile.inventory_total_value);
    document.getElementById("stat-favorite").textContent = profile.favorite_case || "—";
    document.getElementById("stat-top-drop").textContent =
      profile.most_expensive_item ? profile.most_expensive_item.name : "—";

    const botUsername = "your_bot_username"; // подставь реальный юзернейм бота
    document.getElementById("ref-link-input").value =
      `https://t.me/${botUsername}?start=ref_${state.telegramId}`;
  } catch (e) {
    console.error("Ошибка загрузки профиля:", e);
  }
}

document.getElementById("copy-ref-btn").addEventListener("click", () => {
  const input = document.getElementById("ref-link-input");
  input.select();
  navigator.clipboard?.writeText(input.value);
  tg?.showAlert?.("Ссылка скопирована!");
});

document.getElementById("apply-promo-btn").addEventListener("click", async () => {
  const code = document.getElementById("promo-input").value.trim();
  if (!code) return;
  try {
    const result = await apiPost("/promo", { telegram_id: state.telegramId, code });
    tg?.showAlert?.(result.message);
    loadProfile();
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// Обновление баланса в UI
// ============================================
function updateBalanceDisplay() {
  document.getElementById("balance-value").textContent = fmt(state.balance).replace("$", "");
  document.getElementById("vip-pill").style.display = state.isVip ? "block" : "none";
}

// ============================================
// Adsgram: баннер + rewarded видео
// ============================================
document.getElementById("ad-banner-close").addEventListener("click", () => {
  document.getElementById("ad-banner").style.display = "none";
});

document.getElementById("watch-ad-btn").addEventListener("click", async () => {
  try {
    // Реальная интеграция: window.Adsgram.init({ blockId: ADSGRAM_BLOCK_ID }).show()
    await showAdsgramRewarded();

    const result = await apiPost("/ad-reward", {
      telegram_id: state.telegramId,
    });

    state.balance = result.new_balance;
    updateBalanceDisplay();
    tg?.showAlert?.(`+$${result.reward.toLocaleString()} начислено за просмотр!`);
  } catch (e) {
    tg?.showAlert?.(e.message || "Реклама недоступна, попробуйте позже.");
  }
});

function showAdsgramRewarded() {
  return new Promise((resolve, reject) => {
    if (window.Adsgram) {
      window.Adsgram.init({ blockId: ADSGRAM_BLOCK_ID })
        .show()
        .then(resolve)
        .catch(reject);
    } else {
      // Фолбэк для теста без реального SDK
      setTimeout(resolve, 1500);
    }
  });
}

// Interstitial каждые 100-250 открытых кейсов
function maybeShowInterstitial() {
  const threshold = 100 + Math.floor(Math.random() * 150);
  if (state.casesOpenedSinceAd < threshold) return;

  state.casesOpenedSinceAd = 0;
  const overlay = document.getElementById("interstitial-overlay");
  const timerEl = document.getElementById("interstitial-timer");
  overlay.classList.add("active");

  let seconds = 5;
  timerEl.textContent = seconds;
  const interval = setInterval(() => {
    seconds--;
    timerEl.textContent = seconds;
    if (seconds <= 0) {
      clearInterval(interval);
      overlay.classList.remove("active");
    }
  }, 1000);
}

// ============================================
// МИНИ-ИГРА: UPGRADE
// ============================================
function calcUpgradeChance(multiplier) {
  const targetHouseEdge = 0.85;
  let chance = targetHouseEdge / multiplier;
  return Math.max(0.01, Math.min(0.80, chance));
}

function populateUpgradeSelect() {
  const select = document.getElementById("upgrade-item-select");
  select.innerHTML = "";

  if (!state.inventory.length) {
    select.innerHTML = `<option value="">Инвентарь пуст</option>`;
    return;
  }

  state.inventory.forEach(item => {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = `${item.name} — ${fmt(item.price)}`;
    select.appendChild(opt);
  });
}

const upgradeSlider = document.getElementById("upgrade-multiplier-slider");
upgradeSlider.addEventListener("input", () => {
  const mult = parseFloat(upgradeSlider.value);
  document.getElementById("upgrade-multiplier-value").textContent = mult.toFixed(1) + "x";
  const chance = calcUpgradeChance(mult) * 100;
  document.getElementById("upgrade-chance-preview").textContent = chance.toFixed(0) + "%";
});

document.getElementById("upgrade-play-btn").addEventListener("click", async () => {
  const itemId = document.getElementById("upgrade-item-select").value;
  const multiplier = parseFloat(upgradeSlider.value);

  if (!itemId) {
    tg?.showAlert?.("Выбери предмет для улучшения");
    return;
  }

  try {
    const result = await apiPost("/minigames/upgrade", {
      telegram_id: state.telegramId,
      inventory_id: Number(itemId),
      target_multiplier: multiplier,
    });

    playSound(result.result === "win" ? "sound-win" : "sound-lose");

    if (result.result === "win") {
      tg?.showAlert?.(`🎉 Успех! Новая цена: ${fmt(result.new_price)}`);
    } else {
      tg?.showAlert?.(`💥 Неудача. Предмет сгорел.`);
    }

    state.inventory = state.inventory.filter(i => i.id !== Number(itemId));
    populateUpgradeSelect();
    renderInventory();
    loadProfile();
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// МИНИ-ИГРА: CRASH / DICE
// ============================================
const crashSlider = document.getElementById("crash-target-slider");
crashSlider.addEventListener("input", () => {
  document.getElementById("crash-target-value").textContent =
    parseFloat(crashSlider.value).toFixed(1) + "x";
});

document.getElementById("crash-play-btn").addEventListener("click", async () => {
  const betAmount = parseFloat(document.getElementById("crash-bet-input").value);
  const cashoutAt = parseFloat(crashSlider.value);

  if (!betAmount || betAmount <= 0) {
    tg?.showAlert?.("Укажи корректную ставку");
    return;
  }
  if (betAmount > state.balance) {
    tg?.showAlert?.("Недостаточно баланса");
    return;
  }

  try {
    const result = await apiPost("/minigames/crash", {
      telegram_id: state.telegramId,
      bet_amount: betAmount,
      cashout_at: cashoutAt,
    });

    state.balance = result.new_balance;
    updateBalanceDisplay();

    const resultBox = document.getElementById("crash-result");
    resultBox.style.display = "block";

    if (result.result === "win") {
      resultBox.className = "crash-result win";
      resultBox.textContent = `🚀 Краш на ${result.crash_point}x — забрал на ${result.cashout_at}x! Выигрыш: ${fmt(result.winnings)}`;
      playSound("sound-win");
    } else {
      resultBox.className = "crash-result lose";
      resultBox.textContent = `💥 Краш на ${result.crash_point}x — не успел забрать вовремя.`;
      playSound("sound-lose");
    }
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// VIP покупка / Розыгрыши — переход в бота
// ============================================
document.getElementById("buy-vip-btn").addEventListener("click", () => {
  tg?.sendData?.(JSON.stringify({ action: "open_vip_purchase" }));
  tg?.showAlert?.("Открой чат с ботом, чтобы оформить VIP через Telegram Stars.");
});

document.getElementById("open-giveaways").addEventListener("click", () => {
  tg?.showAlert?.("Раздел розыгрышей скоро появится здесь!");
});

// ============================================
// Инициализация приложения
// ============================================
(async function init() {
  await loadCases();
  await loadProfile();
  await loadInventory();
})();
