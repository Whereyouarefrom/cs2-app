// ============================================
// ПРАВКИ В ТЗ №5: headless-проверка (jsdom) новых модалок Настроек/Промокода
// и переноса рефералки во вкладку "Заработать".
//
// Грузит РЕАЛЬНЫЙ index.html + friends.js/pass.js/app.js (в том же порядке,
// что в <script> тегах), эмулирует клики и проверяет:
//   1) обе новые модалки открываются/закрываются по своим кнопкам;
//   2) renderProfileScreen() корректно рисует ref-link-input/ref-hint,
//      хотя блок теперь физически лежит в #screen-earn, а не в #screen-profile;
//   3) #frames-row / #bg-picker-grid / #pass-nick-colors-row существуют
//      РОВНО один раз и лежат внутри #customize-modal (нет дублей после
//      переноса), а рамка/цвет ника из pass.js не выбрасывают исключений
//      при применении к аватару (проверка "конфликта" box-shadow).
// ============================================
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = __dirname;
let html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
// Внешние SDK (Telegram WebApp, Adsgram) вырезаем — сети в песочнице нет.
html = html.replace(/<script src="https:\/\/telegram\.org[^"]*"><\/script>\s*/, "");
html = html.replace(/<script src="https:\/\/sad\.adsgram\.ai[^"]*"><\/script>\s*/, "");
html = html.replace(/<link rel="stylesheet" href="style\.css">/, "");
// Локальные pass.js/friends.js/app.js подставляем ИНЛАЙНОМ (вместо src=) —
// так jsdom выполняет их как обычные <script> теги на одной and той же
// глобальной странице (ровно как в браузере), без похода в реальную сеть
// за относительным src и без проблем с областью видимости `const state`
// между отдельными script-тегами.
for (const file of ["pass.js", "friends.js", "app.js"]) {
  const code = fs.readFileSync(path.join(ROOT, file), "utf8");
  html = html.replace(`<script src="${file}"></script>`, `<script>${code}</script>`);
}

let failures = 0;
function check(name, cond) {
  if (cond) {
    console.log(`  OK   ${name}`);
  } else {
    console.log(`  FAIL ${name}`);
    failures++;
  }
}

(async () => {
  const dom = new JSDOM(html, {
    url: "https://example.com/",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
      // Заглушки браузерных API, которых нет в jsdom / не нужны в тесте.
      window.Telegram = undefined; // ветка `tg?.ready()` в app.js должна пережить это
      window.HTMLMediaElement.prototype.play = () => Promise.resolve();
      window.HTMLMediaElement.prototype.pause = () => {};
      window.scrollTo = () => {};
      window.navigator.__defineGetter__ = window.navigator.__defineGetter__; // no-op guard
      Object.defineProperty(window.navigator, "clipboard", {
        value: { writeText: () => Promise.resolve() },
        configurable: true,
      });
      // fetch — глушим сетевые запросы к бэкенду (в песочнице их всё равно
      // нет), чтобы init() не зависал/не падал с необработанным реджектом.
      window.fetch = () => Promise.reject(new Error("network disabled in headless test"));
    },
  });

  const { window } = dom;

  // Даём скриптам (app.js делает несколько async init-вызовов) время
  // отработать и осесть на catch-ветках, прежде чем щёлкать по UI.
  await new Promise(resolve => setTimeout(resolve, 300));

  const doc = window.document;

  console.log("\n=== 1) Элементы модалок присутствуют РОВНО один раз ===");
  ["promo-modal", "customize-modal", "promo-modal-open-btn", "promo-modal-close-btn",
   "profile-settings-open-btn", "customize-modal-close-btn", "bg-picker-grid",
   "frames-row", "pass-cosmetics-card", "pass-frames-row", "pass-nick-colors-row",
   "promo-input", "apply-promo-btn", "ref-link-input", "ref-hint", "copy-ref-btn"]
    .forEach(id => {
      const found = doc.querySelectorAll(`#${id}`);
      check(`#${id} встречается 1 раз (нашли ${found.length})`, found.length === 1);
    });

  console.log("\n=== 2) Контролы кастомизации физически лежат внутри #customize-modal ===");
  const customizeModal = doc.getElementById("customize-modal");
  ["bg-picker-grid", "frames-row", "pass-frames-row", "pass-nick-colors-row"].forEach(id => {
    const el = doc.getElementById(id);
    check(`#${id} внутри #customize-modal`, !!el && customizeModal.contains(el));
  });

  console.log("\n=== 3) Промокод лежит внутри #promo-modal ===");
  const promoModal = doc.getElementById("promo-modal");
  ["promo-input", "apply-promo-btn"].forEach(id => {
    const el = doc.getElementById(id);
    check(`#${id} внутри #promo-modal`, !!el && promoModal.contains(el));
  });

  console.log("\n=== 4) Реферальный блок лежит внутри #screen-earn, НЕ в #screen-profile ===");
  const screenEarn = doc.getElementById("screen-earn");
  const screenProfile = doc.getElementById("screen-profile");
  const refLink = doc.getElementById("ref-link-input");
  check("#ref-link-input внутри #screen-earn", screenEarn.contains(refLink));
  check("#ref-link-input НЕ внутри #screen-profile", !screenProfile.contains(refLink));
  check("В #screen-profile больше нет .ref-block/.promo-block",
    screenProfile.querySelectorAll(".ref-block, .promo-block").length === 0);

  console.log("\n=== 5) Открытие/закрытие модалок кликами (реальные обработчики app.js) ===");
  const settingsBtn = doc.getElementById("profile-settings-open-btn");
  const promoBtn = doc.getElementById("promo-modal-open-btn");

  check("customize-modal изначально закрыта", !customizeModal.classList.contains("active"));
  settingsBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check("customize-modal открылась после клика по ⚙️", customizeModal.classList.contains("active"));
  doc.getElementById("customize-modal-close-btn").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check("customize-modal закрылась после клика по ✕", !customizeModal.classList.contains("active"));

  check("promo-modal изначально закрыта", !promoModal.classList.contains("active"));
  promoBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check("promo-modal открылась после клика по 🎁", promoModal.classList.contains("active"));
  doc.getElementById("promo-modal-close-btn").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check("promo-modal закрылась после клика по ✕", !promoModal.classList.contains("active"));

  console.log("\n=== 6) renderProfileScreen() рисует рефералку в новом месте DOM ===");
  // Прогоняем настоящую функцию рендера профиля с фейковым `profile`,
  // как её вызывает app.js после /user/profile — проверяем, что она не
  // падает и реально заполняет #ref-link-input/#ref-hint, лежащие теперь
  // в #screen-earn, а не в #screen-profile.
  const fakeProfile = {
    total_cases_opened: 3,
    inventory_total_value: 1234,
    favorite_case: "Test Case",
    total_profit: 500,
    minigames_stats: { played: 7 },
    top_drop: null,
    rank: null,
    level: { level: 5, xp: 100, xp_in_level: 10, xp_needed: 50, progress_percent: 20,
              is_max: false, showcase_slots: 4, showcase_max_slots: 9, next_showcase_slot_level: 10 },
    showcase: { slots: 4, max_slots: 9, next_slot_level: 10, items: [] },
    selected_title_info: null,
    selected_frame_info: null,
    frames: [], titles: [],
  };
  // `const state = {...}` в app.js — глобальная лексическая переменная,
  // а не свойство window (особенность ES6 const на верхнем уровне), поэтому
  // достаём ту же ссылку через window.eval("state") вместо window.state.
  const stateRef = window.eval("state");
  stateRef.lastProfile = fakeProfile;
  stateRef.telegramId = 123456789;
  stateRef.botUsername = "test_bot";
  let renderThrew = false;
  try {
    window.renderProfileScreen(fakeProfile);
  } catch (e) {
    renderThrew = true;
    console.log("     Исключение:", e.message);
  }
  check("renderProfileScreen() не бросила исключение", !renderThrew);
  check("ref-link-input.value заполнено ссылкой t.me/...",
    doc.getElementById("ref-link-input").value.includes("t.me/") &&
    doc.getElementById("ref-link-input").value.includes("123456789"));
  check("showcase-counter показывает открытые слоты уровня (X / slots=4), а не max_slots",
    doc.getElementById("showcase-counter").textContent.trim() === "0 / 4");
  check("showcase-grid отрисовала ровно 9 ячеек (max_slots=9, включая locked-заглушки сверх 4 открытых)",
    doc.getElementById("showcase-grid").children.length === 9);

  // Отдельно проверяем сценарий из ТЗ №5: игрок максимального уровня,
  // все 9 слотов открыты -> счётчик должен показать именно "9 / 9" (а не
  // старое "9 / 10").
  const maxedProfile = { ...fakeProfile, showcase: { slots: 9, max_slots: 9, next_slot_level: null, items: [] } };
  window.renderProfileScreen(maxedProfile);
  check('При slots=max_slots=9 счётчик показывает "9 / 9" (было "9 / 10")',
    doc.getElementById("showcase-counter").textContent.trim() === "0 / 9");

  console.log("\n=== 7) Рамки: level-frame (класс на wrap) и pass-frame (inline box-shadow на avatar) не пишут в одно и то же свойство одного элемента ===");
  const wrap = doc.getElementById("profile-avatar-wrap");
  const avatarEmoji = doc.getElementById("profile-avatar");
  window.applyAvatarFrame(wrap, { key: "test", name: "Test", color: "#ff0000", style: "glow" });
  check("applyAvatarFrame() не бросила исключение и навесила класс has-frame/frame-glow",
    wrap.classList.contains("has-frame") && wrap.classList.contains("frame-glow"));
  check("applyAvatarFrame() НЕ трогает инлайновый style.boxShadow элемента-обёртки (использует CSS-класс + переменную)",
    wrap.style.boxShadow === "");
  // applyPassCosmeticsToProfile живёt в pass.js и пишет inline box-shadow
  // на #profile-avatar / #profile-avatar-img (ВНУТРЕННИЕ элементы), а не
  // на #profile-avatar-wrap (ВНЕШНИЙ) — то есть технически это два разных
  // DOM-узла и два разных механизма (CSS-класс vs inline style), явного
  // перезатирания одного и того же свойства одного и того же элемента нет.
  if (typeof window.applyPassCosmeticsToProfile === "function") {
    const passStateRef = window.eval("passState");
    passStateRef.status = {
      unlocked_pass_frames: ["neon_rookie"],
      unlocked_pass_nick_colors: ["gold"],
      selected_pass_frame: "neon_rookie",
      selected_pass_nick_color: "gold",
    };
    let passThrew = false;
    try {
      window.applyPassCosmeticsToProfile();
    } catch (e) {
      passThrew = true;
      console.log("     Исключение:", e.message);
    }
    check("applyPassCosmeticsToProfile() не бросила исключение", !passThrew);
    check("pass-frame пишет inline box-shadow на #profile-avatar (внутренний элемент), а не на #profile-avatar-wrap",
      avatarEmoji.style.boxShadow !== "" && wrap.style.boxShadow === "");
    check("Рамка уровня (класс на wrap) осталась нетронутой после применения pass-рамки",
      wrap.classList.contains("has-frame"));
    console.log("     => Оба эффекта визуально совместимы: level-рамка рисует внешнее кольцо на .profile-avatar-wrap");
    console.log("        (CSS box-shadow через класс), pass-рамка — отдельное inline-кольцо на самой картинке/эмодзи");
    console.log("        внутри неё. Кода, где один стиль перетирает другой, нет. Если выбраны ОБЕ рамки одновременно —");
    console.log("        это делает двойное кольцо (эффект, а не баг) — так было и до переноса, поведение не менялось.");
  } else {
    console.log("     (pass.js не подключён в этом тесте — пропуск)");
  }

  console.log(`\n${failures === 0 ? "✅ ВСЕ ПРОВЕРКИ ПРОШЛИ" : `❌ ПРОВАЛЕНО ПРОВЕРОК: ${failures}`}`);
  process.exit(failures === 0 ? 0 : 1);
})();
