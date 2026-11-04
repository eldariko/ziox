/**
 * Serverless Cloudflare Worker Telegram Webhook for zioX.
 *
 * Zero-dependency ES Module Worker that handles Telegram commands
 * (/start, /help, /ready, /stop, /style, /lang, /limit, /quota) and
 * inline keyboard callbacks (set_style:*, set_lang:*, set_limit:*,
 * menu:*, ready:confirm, ack:<tweet_id>) in real time (24/7) by talking
 * directly to Turso Cloud's HTTP /v2/pipeline API.
 *
 * Required Cloudflare Worker Secrets / Variables:
 *   - TELEGRAM_BOT_TOKEN      (Secret)
 *   - TURSO_DATABASE_URL      (Secret or Variable, e.g. libsql://... or https://...)
 *   - TURSO_AUTH_TOKEN        (Secret)
 *   - TELEGRAM_WEBHOOK_SECRET (Optional Secret for X-Telegram-Bot-Api-Secret-Token verification)
 *   - TELEGRAM_CHAT_ID        (Optional Variable: comma-separated admin chat IDs)
 *   - MAX_USER_DAILY_LIMIT    (Optional Variable: default "5")
 */

const VALID_STYLES = new Set(["any", "factual", "sharp", "historical_legal", "rhetorical_question"]);
const VALID_LANGS = new Set(["en", "ar", "both"]);

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function getStyleKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "🎯 Factual (עובדתי)", callback_data: "set_style:factual" },
        { text: "⚡ Sharp (עוקצני/חד)", callback_data: "set_style:sharp" },
      ],
      [
        { text: "📜 Historical/Legal (משפטי)", callback_data: "set_style:historical_legal" },
        { text: "❓ Rhetorical (רטורי)", callback_data: "set_style:rhetorical_question" },
      ],
      [{ text: "🎲 Any (ללא העדפה)", callback_data: "set_style:any" }],
      [{ text: "🔙 תפריט ראשי", callback_data: "menu:main" }],
    ],
  };
}

function getLangKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "🇬🇧 English (אנגלית - ברירת מחדל)", callback_data: "set_lang:en" }],
      [{ text: "🇸🇦 Arabic (ערבית בלבד)", callback_data: "set_lang:ar" }],
      [{ text: "🌐 Both (שתי השפות)", callback_data: "set_lang:both" }],
      [{ text: "🔙 תפריט ראשי", callback_data: "menu:main" }],
    ],
  };
}

function getLimitKeyboard(maxUserDailyLimit = 5) {
  const row = [];
  for (let i = 1; i <= maxUserDailyLimit; i++) {
    row.push({ text: `${i} ביום`, callback_data: `set_limit:${i}` });
  }
  return {
    inline_keyboard: [row, [{ text: "🔙 תפריט ראשי", callback_data: "menu:main" }]],
  };
}

function getMainMenuKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "✅ אני מוכן להגיב", callback_data: "ready:confirm" }],
      [
        { text: "🎨 סגנון תגובה (/style)", callback_data: "menu:style" },
        { text: "🌐 שפת פוסטים (/lang)", callback_data: "menu:lang" },
      ],
      [
        { text: "📊 מכסה יומית (/limit)", callback_data: "menu:limit" },
        { text: "📈 סטטוס ומכסה (/quota)", callback_data: "menu:quota" },
      ],
      [{ text: "🛑 השהיית מנוי (/stop)", callback_data: "menu:stop" }],
    ],
  };
}

function normalizeTursoUrl(rawUrl) {
  let clean = String(rawUrl || "").trim();
  if (clean.startsWith("libsql://")) {
    clean = "https://" + clean.slice("libsql://".length);
  } else if (clean.startsWith("wss://")) {
    clean = "https://" + clean.slice("wss://".length);
  } else if (clean.startsWith("ws://")) {
    clean = "http://" + clean.slice("ws://".length);
  } else if (clean && !clean.startsWith("http://") && !clean.startsWith("https://")) {
    clean = "https://" + clean;
  }
  return clean.replace(/\/+$/, "") + "/v2/pipeline";
}

function toProtoValue(val) {
  if (val === null || val === undefined) {
    return { type: "null" };
  }
  if (typeof val === "boolean") {
    return { type: "integer", value: val ? "1" : "0" };
  }
  if (typeof val === "number" && Number.isInteger(val)) {
    return { type: "integer", value: String(val) };
  }
  if (typeof val === "number") {
    return { type: "float", value: val };
  }
  return { type: "text", value: String(val) };
}

function fromProtoValue(cell) {
  if (!cell || typeof cell !== "object") return cell;
  if (cell.type === "null") return null;
  if (cell.type === "integer") return parseInt(cell.value || "0", 10);
  if (cell.type === "float") return parseFloat(cell.value || "0");
  return cell.value ?? "";
}

async function tursoExecute(env, sql, args = []) {
  const pipelineUrl = normalizeTursoUrl(env.TURSO_DATABASE_URL);
  const protoArgs = args.map(toProtoValue);
  const payload = {
    requests: [
      {
        type: "execute",
        stmt: { sql, args: protoArgs },
      },
      { type: "close" },
    ],
  };
  const headers = { "Content-Type": "application/json" };
  if (env.TURSO_AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${env.TURSO_AUTH_TOKEN}`;
  }
  const resp = await fetch(pipelineUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Turso HTTP error ${resp.status}: ${errText}`);
  }
  const data = await resp.json();
  const first = (data.results || [])[0];
  if (!first) return { rows: [], rowsAffected: 0 };
  if (first.type === "error") {
    throw new Error(`Turso SQL error: ${JSON.stringify(first.error)}`);
  }
  const resObj = (first.response && first.response.result) || {};
  const cols = (resObj.cols || []).map((c) => c.name || "");
  const rows = (resObj.rows || []).map((rawRow) => {
    const obj = {};
    rawRow.forEach((cell, idx) => {
      obj[cols[idx]] = fromProtoValue(cell);
    });
    return obj;
  });
  return {
    rows,
    rowsAffected: resObj.affected_row_count || 0,
  };
}

async function sendTelegramMessage(env, chatId, textHtml, replyMarkup = null) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const payload = {
    chat_id: String(chatId),
    text: textHtml,
    parse_mode: "HTML",
    disable_web_page_preview: true,
  };
  if (replyMarkup) {
    payload.reply_markup = replyMarkup;
  }
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.status === 403) {
    await tursoExecute(
      env,
      "UPDATE subscribers SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
      [String(chatId)]
    );
  }
  return resp.ok;
}

async function answerCallbackQuery(env, callbackQueryId, text = "") {
  if (!callbackQueryId) return;
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`;
  const payload = { callback_query_id: String(callbackQueryId) };
  if (text) payload.text = text;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function getSubscriber(env, chatId) {
  const res = await tursoExecute(env, "SELECT * FROM subscribers WHERE chat_id = ?", [String(chatId)]);
  return res.rows[0] || null;
}

async function upsertSubscriber(env, chatId, username, isAdmin, defaultDailyLimit = 3) {
  const tier = isAdmin ? "admin" : "free";
  const limit = isAdmin ? 100 : defaultDailyLimit;
  await tursoExecute(
    env,
    `INSERT INTO subscribers (
      chat_id, username, tier, daily_limit, preferred_style,
      preferred_lang, ready_confirmed, active, updated_at
    ) VALUES (?, ?, ?, ?, 'any', 'en', 1, 1, CURRENT_TIMESTAMP)
    ON CONFLICT(chat_id) DO UPDATE SET
      username = CASE WHEN excluded.username != '' THEN excluded.username ELSE subscribers.username END,
      ready_confirmed = 1,
      active = 1,
      updated_at = CURRENT_TIMESTAMP`,
    [String(chatId), String(username || ""), tier, limit]
  );
}

async function ensureSubscriberExists(env, chatId, username, isAdmin, defaultDailyLimit = 3) {
  const existing = await getSubscriber(env, chatId);
  if (!existing) {
    await upsertSubscriber(env, chatId, username, isAdmin, defaultDailyLimit);
  }
}

async function updateDailyLimit(env, chatId, requestedLimit, maxCeiling = 5) {
  const sub = await getSubscriber(env, chatId);
  const tier = (sub && sub.tier) || "free";
  const effectiveCeiling = tier === "admin" ? 100 : tier === "pro" ? Math.max(15, maxCeiling) : maxCeiling;
  const clamped = Math.max(1, Math.min(parseInt(requestedLimit, 10) || 1, effectiveCeiling));
  await tursoExecute(
    env,
    "UPDATE subscribers SET daily_limit = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
    [clamped, String(chatId)]
  );
  return clamped;
}

async function formatQuotaHtml(env, chatId, defaultDailyLimit = 3) {
  const sub = await getSubscriber(env, chatId);
  const countRes = await tursoExecute(
    env,
    "SELECT COUNT(*) as count FROM dispatches WHERE chat_id = ? AND date(dispatched_at) = date('now')",
    [String(chatId)]
  );
  const todayUsed = (countRes.rows[0] && countRes.rows[0].count) || 0;
  const dLimit = sub && sub.daily_limit ? sub.daily_limit : defaultDailyLimit;
  const pStyle = (sub && sub.preferred_style) || "any";
  const pLang = (sub && sub.preferred_lang) || "en";
  const totalConf = (sub && sub.total_confirmed_replies) || 0;

  return (
    "📊 <b>סטטוס המנוי שלך ב-zioX:</b>\n" +
    `• <b>פוסטים היום:</b> <code>${todayUsed} / ${dLimit}</code>\n` +
    `• <b>תגובות שאושרו ב-X:</b> <code>${totalConf}</code>\n` +
    `• <b>סגנון מועדף:</b> <code>${escapeHtml(pStyle)}</code>\n` +
    `• <b>שפה מועדפת:</b> <code>${escapeHtml(pLang)}</code>`
  );
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("zioX Telegram Webhook Worker is active.", { status: 200 });
    }

    // 1. Verify optional Telegram secret token header
    if (env.TELEGRAM_WEBHOOK_SECRET) {
      const headerSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
      if (headerSecret !== env.TELEGRAM_WEBHOOK_SECRET) {
        return new Response("Unauthorized", { status: 401 });
      }
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const adminIds = new Set(
      String(env.TELEGRAM_CHAT_ID || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    );
    const maxUserDailyLimit = parseInt(env.MAX_USER_DAILY_LIMIT || "5", 10) || 5;
    const defaultDailyLimit = 3;

    try {
      // A. Handle Inline Button Callback Queries
      if (update.callback_query) {
        const cb = update.callback_query;
        const cbId = String(cb.id || "").trim();
        const cbData = String(cb.data || "").trim();
        const cbChat = (cb.message && cb.message.chat) || cb.from || {};
        const cbChatId = String(cbChat.id || "").trim();
        const cbUsername =
          (cb.from && cb.from.username) || cbChat.username || cbChat.first_name || "";

        if (cbChatId) {
          const isAdmin = adminIds.has(cbChatId);
          await ensureSubscriberExists(env, cbChatId, cbUsername, isAdmin, defaultDailyLimit);

          if (cbData === "ready:confirm") {
            await tursoExecute(
              env,
              `UPDATE subscribers
               SET ready_confirmed = 1, active = 1, consecutive_unconfirmed = 0, updated_at = CURRENT_TIMESTAMP
               WHERE chat_id = ?`,
              [cbChatId]
            );
            await answerCallbackQuery(env, cbId, "✅ מוכנותך אושרה! תקבל פוסטים בסבב הקרוב.");
            const readyHtml =
              "🚀 <b>מעולה! החשבון שלך פעיל ומוכן לקבלת פוסטים.</b>\n" +
              "בכל פעם שתקבל פוסט ותגיב עליו ב-X, לחץ על הכפתור <b>✅ הגבתי ב-X</b> בכרטיס כדי להמשיך לקבל פוסטים.";
            await sendTelegramMessage(env, cbChatId, readyHtml, getMainMenuKeyboard());
          } else if (cbData.startsWith("set_style:")) {
            const reqStyle = cbData.slice("set_style:".length).trim().toLowerCase();
            if (VALID_STYLES.has(reqStyle)) {
              await tursoExecute(
                env,
                "UPDATE subscribers SET preferred_style = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                [reqStyle, cbChatId]
              );
              await answerCallbackQuery(env, cbId, `✅ סגנון עודכן ל-${reqStyle}`);
              const styleHtml =
                `🎨 <b>סגנון התגובות שלך עודכן ל-<code>${escapeHtml(reqStyle)}</code>!</b>\n` +
                "בסבבים הבאים נתעדף עבורך וריאציות בסגנון זה.\n" +
                "תוכל לשנות סגנון בכל עת:";
              await sendTelegramMessage(env, cbChatId, styleHtml, getStyleKeyboard());
            }
          } else if (cbData.startsWith("set_lang:")) {
            const reqLang = cbData.slice("set_lang:".length).trim().toLowerCase();
            if (VALID_LANGS.has(reqLang)) {
              await tursoExecute(
                env,
                "UPDATE subscribers SET preferred_lang = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                [reqLang, cbChatId]
              );
              await answerCallbackQuery(env, cbId, `✅ שפה עודכנה ל-${reqLang}`);
              const langDesc =
                reqLang === "en" ? "אנגלית בלבד" : reqLang === "ar" ? "ערבית בלבד" : "שתי השפות";
              const langHtml =
                `🌐 <b>שפת הפוסטים שלך עודכנה ל-<code>${escapeHtml(reqLang)}</code> (${langDesc})!</b>\n` +
                "תוכל לשנות שפה בכל עת:";
              await sendTelegramMessage(env, cbChatId, langHtml, getLangKeyboard());
            }
          } else if (cbData.startsWith("set_limit:")) {
            const limitStr = cbData.slice("set_limit:".length).trim();
            if (/^\d+$/.test(limitStr)) {
              const effLimit = await updateDailyLimit(env, cbChatId, parseInt(limitStr, 10), maxUserDailyLimit);
              await answerCallbackQuery(env, cbId, `✅ מכסה עודכנה ל-${effLimit}`);
              const limitHtml =
                `📊 <b>המכסה היומית שלך עודכנה ל-<code>${effLimit}</code> פוסטים ביום!</b>\n` +
                "תוכל לעדכן בכל עת:";
              await sendTelegramMessage(env, cbChatId, limitHtml, getLimitKeyboard(maxUserDailyLimit));
            }
          } else if (cbData === "menu:style") {
            await answerCallbackQuery(env, cbId);
            const styleHtml =
              "🎨 <b>בחירת סגנון תגובה ב-zioX:</b>\n" +
              "בחר את סגנון התגובות המועדף עליך באמצעות הכפתורים למטה:";
            await sendTelegramMessage(env, cbChatId, styleHtml, getStyleKeyboard());
          } else if (cbData === "menu:lang") {
            await answerCallbackQuery(env, cbId);
            const langHtml =
              "🌐 <b>בחירת שפת פוסטים ב-zioX:</b>\n" +
              "ברירת המחדל היא <b>אנגלית בלבד</b> (<code>en</code>).\n" +
              "בחר שפה באמצעות הכפתורים למטה:";
            await sendTelegramMessage(env, cbChatId, langHtml, getLangKeyboard());
          } else if (cbData === "menu:limit") {
            await answerCallbackQuery(env, cbId);
            const limitHtml =
              "📊 <b>עדכון מכסה יומית:</b>\n" +
              `בחר את כמות הפוסטים היומית המועדפת עליך (עד ${maxUserDailyLimit} ביום):`;
            await sendTelegramMessage(env, cbChatId, limitHtml, getLimitKeyboard(maxUserDailyLimit));
          } else if (cbData === "menu:quota") {
            await answerCallbackQuery(env, cbId);
            const quotaHtml = await formatQuotaHtml(env, cbChatId, defaultDailyLimit);
            await sendTelegramMessage(env, cbChatId, quotaHtml, getMainMenuKeyboard());
          } else if (cbData === "menu:stop") {
            await tursoExecute(
              env,
              "UPDATE subscribers SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
              [cbChatId]
            );
            await answerCallbackQuery(env, cbId, "🛑 המנוי הושהה");
            const stopHtml =
              "🛑 <b>המנוי שלך ב-zioX הושהה.</b> תוכל לחזור בכל עת באמצעות שליחת <code>/start</code> או <code>/ready</code>.";
            await sendTelegramMessage(env, cbChatId, stopHtml, {
              inline_keyboard: [[{ text: "🚀 הפעל מחדש", callback_data: "ready:confirm" }]],
            });
          } else if (cbData === "menu:main") {
            await answerCallbackQuery(env, cbId);
            const mainHtml =
              "⚙️ <b>תפריט ראשי zioX:</b>\n" +
              "בחר באחת האפשרויות למטה לניהול המנוי וההעדפות שלך:";
            await sendTelegramMessage(env, cbChatId, mainHtml, getMainMenuKeyboard());
          } else if (cbData.startsWith("ack:")) {
            const ackTweetId = cbData.slice("ack:".length).trim();
            if (ackTweetId) {
              const dispRes = await tursoExecute(
                env,
                `UPDATE dispatches
                 SET confirmed = 1, confirmed_at = CURRENT_TIMESTAMP
                 WHERE tweet_id = ? AND chat_id = ? AND COALESCE(confirmed, 0) = 0`,
                [ackTweetId, cbChatId]
              );
              if (dispRes.rowsAffected > 0) {
                await tursoExecute(
                  env,
                  `UPDATE subscribers
                   SET consecutive_unconfirmed = 0,
                       ready_confirmed = 1,
                       active = 1,
                       total_confirmed_replies = COALESCE(total_confirmed_replies, 0) + 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE chat_id = ?`,
                  [cbChatId]
                );
              } else {
                await tursoExecute(
                  env,
                  `UPDATE subscribers
                   SET consecutive_unconfirmed = 0,
                       ready_confirmed = 1,
                       active = 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE chat_id = ?`,
                  [cbChatId]
                );
              }
            }
            await answerCallbackQuery(env, cbId, "👏 תודה! התגובה שלך נרשמה.");
          }
        }
        return new Response("OK", { status: 200 });
      }

      // B. Handle Text Commands
      const msg = update.message || update.edited_message;
      if (msg && msg.chat && msg.text) {
        const chatId = String(msg.chat.id || "").trim();
        const username =
          msg.chat.username || (msg.from && msg.from.username) || msg.chat.first_name || "";
        const text = String(msg.text || "").trim();
        const lowerText = text.toLowerCase();
        const isAdmin = adminIds.has(chatId);

        if (lowerText.startsWith("/start")) {
          await upsertSubscriber(env, chatId, username, isAdmin, defaultDailyLimit);
          const welcomeHtml =
            "✅ <b>נרשמת בהצלחה ל-zioX!</b>\n" +
            "בסבב הסריקה הבא תקבל לכאן הצעות תגובה ייחודיות מבוססות מקורות מאומתים בלחיצה אחת.\n\n" +
            "🌐 <b>שפת ברירת מחדל:</b> אנגלית בלבד (<code>en</code>).\n\n" +
            "🎨 <b>בחירת סגנון אישי:</b> <code>/style</code> (או לחץ על הכפתור למטה)\n" +
            "🌐 <b>בחירת שפה:</b> <code>/lang</code> (או לחץ על הכפתור למטה)\n" +
            "📊 <b>מכסה יומית:</b> <code>/limit</code> (או <code>/quota</code> לבדיקת מצב)\n" +
            "✋ <b>וידוא מוכנות:</b> לחץ על הכפתור <b>✅ אני מוכן להגיב</b> (או שלח <code>/ready</code>)\n" +
            "🛑 להפסקה בכל עת שלח <code>/stop</code>.";
          await sendTelegramMessage(env, chatId, welcomeHtml, getMainMenuKeyboard());
        } else if (lowerText.startsWith("/help")) {
          const helpHtml =
            "📖 <b>מדריך פקודות ותפריט zioX:</b>\n\n" +
            "• <code>/start</code> - הרשמה והפעלת המנוי\n" +
            "• <code>/ready</code> - אישור מוכנות לקבלת פוסטים להגבה\n" +
            "• <code>/style</code> - בחירת סגנון תגובות מועדף\n" +
            "• <code>/lang</code> - בחירת שפת פוסטים (ברירת מחדל: אנגלית <code>en</code>)\n" +
            "• <code>/limit</code> - עדכון מכסה יומית (1 עד 5 פוסטים)\n" +
            "• <code>/quota</code> - בדיקת מצב המכסה וההגדרות שלך\n" +
            "• <code>/stop</code> - השהיית קבלת פוסטים\n\n" +
            "💡 <b>טיפ לשמירה על הפיד האישי:</b>\n" +
            "רוצה להגן על הפיד האישי שלך? פתח חשבון X משני להסברה, חבר אותו באפליקציה ועבור אליו בלחיצה ארוכה על תמונת הפרופיל לפני שמגיבים!\n\n" +
            "👇 <b>ניתן ללחוץ על הכפתורים למטה לניהול מהיר:</b>";
          await sendTelegramMessage(env, chatId, helpHtml, getMainMenuKeyboard());
        } else if (lowerText.startsWith("/ready")) {
          await ensureSubscriberExists(env, chatId, username, isAdmin, defaultDailyLimit);
          await tursoExecute(
            env,
            `UPDATE subscribers
             SET ready_confirmed = 1, active = 1, consecutive_unconfirmed = 0, updated_at = CURRENT_TIMESTAMP
             WHERE chat_id = ?`,
            [chatId]
          );
          const readyHtml =
            "🚀 <b>מוכנותך אושרה!</b> החשבון שלך פעיל ויקבל פוסטים בסבב הקרוב.\n" +
            "זכור ללחוץ על <b>✅ הגבתי ב-X</b> לאחר פרסום תגובה.";
          await sendTelegramMessage(env, chatId, readyHtml, getMainMenuKeyboard());
        } else if (lowerText.startsWith("/stop")) {
          await tursoExecute(
            env,
            "UPDATE subscribers SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
            [chatId]
          );
          const stopHtml =
            "🛑 <b>המנוי שלך ב-zioX הושהה.</b> תוכל לחזור בכל עת באמצעות שליחת <code>/start</code> או <code>/ready</code>.";
          await sendTelegramMessage(env, chatId, stopHtml, {
            inline_keyboard: [[{ text: "🚀 הפעל מחדש", callback_data: "ready:confirm" }]],
          });
        } else if (lowerText.startsWith("/style")) {
          await ensureSubscriberExists(env, chatId, username, isAdmin, defaultDailyLimit);
          const parts = lowerText.split(/\s+/);
          const requestedStyle = parts[1] ? parts[1].trim() : "";
          let styleHtml;
          if (VALID_STYLES.has(requestedStyle)) {
            await tursoExecute(
              env,
              "UPDATE subscribers SET preferred_style = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
              [requestedStyle, chatId]
            );
            styleHtml =
              `🎨 <b>סגנון התגובות שלך עודכן ל-<code>${escapeHtml(requestedStyle)}</code>!</b>\n` +
              "בסבבים הבאים נתעדף עבורך וריאציות בסגנון זה.\n" +
              "תוכל להחליף סגנון בכל עת בכפתורים למטה:";
          } else {
            styleHtml =
              "🎨 <b>בחירת סגנון תגובה ב-zioX:</b>\n" +
              "בחר את הסגנון המועדף עליך באמצעות הכפתורים למטה, או שלח <code>/style &lt;name&gt;</code>:";
          }
          await sendTelegramMessage(env, chatId, styleHtml, getStyleKeyboard());
        } else if (lowerText.startsWith("/lang")) {
          await ensureSubscriberExists(env, chatId, username, isAdmin, defaultDailyLimit);
          const parts = lowerText.split(/\s+/);
          const requestedLang = parts[1] ? parts[1].trim() : "";
          let langHtml;
          if (VALID_LANGS.has(requestedLang)) {
            await tursoExecute(
              env,
              "UPDATE subscribers SET preferred_lang = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
              [requestedLang, chatId]
            );
            const langDesc =
              requestedLang === "en" ? "אנגלית בלבד" : requestedLang === "ar" ? "ערבית בלבד" : "שתי השפות";
            langHtml =
              `🌐 <b>שפת הפוסטים שלך עודכנה ל-<code>${escapeHtml(requestedLang)}</code> (${langDesc})!</b>\n` +
              "תוכל להחליף שפה בכל עת בכפתורים למטה:";
          } else {
            langHtml =
              "🌐 <b>בחירת שפת פוסטים ב-zioX:</b>\n" +
              "ברירת המחדל היא <b>אנגלית בלבד</b> (<code>en</code>).\n" +
              "בחר שפה באמצעות הכפתורים למטה, או שלח <code>/lang &lt;en|ar|both&gt;</code>:";
          }
          await sendTelegramMessage(env, chatId, langHtml, getLangKeyboard());
        } else if (lowerText.startsWith("/limit")) {
          await ensureSubscriberExists(env, chatId, username, isAdmin, defaultDailyLimit);
          const parts = lowerText.split(/\s+/);
          const argNum = parts[1] ? parts[1].trim() : "";
          let limitHtml;
          if (/^\d+$/.test(argNum) && parseInt(argNum, 10) >= 1) {
            const reqVal = parseInt(argNum, 10);
            const effectiveLimit = await updateDailyLimit(env, chatId, reqVal, maxUserDailyLimit);
            if (effectiveLimit < reqVal) {
              limitHtml =
                `📊 <b>המכסה היומית שלך עודכנה ל-<code>${effectiveLimit}</code> פוסטים ביום</b> ` +
                `(התקרה המרכזית המותרת למנוי שלך היא ${effectiveLimit}).\n` +
                "תוכל לעדכן בכל עת בכפתורים למטה:";
            } else {
              limitHtml =
                `📊 <b>המכסה היומית שלך עודכנה ל-<code>${effectiveLimit}</code> פוסטים ביום!</b>\n` +
                "תוכל לעדכן בכל עת בכפתורים למטה:";
            }
          } else {
            limitHtml =
              `ℹ️ <b>עדכון מכסה יומית:</b> שלח <code>/limit &lt;1-${maxUserDailyLimit}&gt;</code> ` +
              "(לדוגמה: <code>/limit 4</code>).\n" +
              "או בחר ישירות באחד הכפתורים למטה:";
          }
          await sendTelegramMessage(env, chatId, limitHtml, getLimitKeyboard(maxUserDailyLimit));
        } else if (lowerText.startsWith("/quota")) {
          const quotaHtml = await formatQuotaHtml(env, chatId, defaultDailyLimit);
          await sendTelegramMessage(env, chatId, quotaHtml, getMainMenuKeyboard());
        }
      }
    } catch (err) {
      console.error("[zioX Webhook Worker Error]", err);
    }

    return new Response("OK", { status: 200 });
  },
};
