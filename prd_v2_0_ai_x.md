# מסמך דרישות מוצר וארכיטקטורה מעודכן (PRD v2.0)

## פרויקט: AI Advocacy, Fact-Checking & Engagement Agent for X (Twitter)

---

## 1. ביקורת עצמית והשלמת פערים (Gap Analysis & Validation)

בבחינה חוזרת של הדרישות המקוריות אל מול מסמך ה-PRD הראשוני, אותרו ארבעה פערים מהותיים שתוקנו והוטמעו במלואם בגרסה זו:

1. **ניהול שרשור והמשך שיחה (Thread Continuity):**
   * *הפער:* ה-PRD הקודם פסל מענה לאותו משתמש בטווח של 24 שעות. הדבר מנע מהבוט להמשיך לנהל שיחה אם ענו לו.
   * *התיקון:* הוספת מודול ניהול שיחה (Conversation State Machine) המאפשר המשך מענה ענייני בשרשור (עד 2–3 סבבים), כולל מנגנון ניתוק מגע אם הצד השני עובר להטרדה או לטרולינג.
2. **צירוף לינקים ומדיה (Links & Media Attachment):**
   * *הפער:* ה-PRD התמקד בטקסט בלבד ולא כלל שיתוף קישורים רשמיים או תמונות להוכחת עובדות.
   * *התיקון:* הרחבת מודול הניסוח והביצוע לתמיכה במאגר מקורות מהימנים (Whitelisted Fact Links) וצירוף תמונות/אינפוגרפיקות דרך ה-API.
3. **זיהוי פוסטים בעלי פוטנציאל התפוצצות (Viral Momentum Detection):**
   * *הפער:* הסינון התבסס רק על רף סטטי (למשל: מעל 50 לייקים), מה שהחמיץ ציוצים חדשים שנמצאים בעלייה מהירה.
   * *התיקון:* אלגוריתם מומנטום המחשב קצב מעורבות ביחס לזמן פרסום ($\text{Velocity} = \frac{\text{Engagements}}{\Delta t}$).
4. **זמינות מתמדת מול תקרת פעילות:**
   * *הפער:* הרצה חד-יומית לא מאפשרת מענה מהיר בשיחות חמות.
   * *התיקון:* סריקות תכופות (כל שעתיים-שלוש) עם תקציב יומי קפדני (תגובה אחת ביום / 20–30 בחודש) ותור עדיפויות מבוסס איכות.

---

## 2. מטרות הפרויקט ויעדים

1. **הסברה מבוססת עובדות:** מענה חד, מלומד, ענייני ומבוסס מקורות המפריך טענות כוזבות ומחזק את הצד הישראלי ברשת X.
2. **חיקוי התנהגות אנושית מלאה (Stealth Mode):** הימנעות מוחלטת מתבניות AI (ללא Em-Dash `—`, ללא כדורי פתיחה רובוטיים, תגובות קצרות, שילוב שגיאות הקלדה מזעריות במכוון).
3. **מולטי-שפתיות:** זיהוי שפת הציוץ ומענה בשפת המקור (אנגלית, צרפתית, ספרדית, ערבית או עברית).
4. **נפח מבוקר וחסכוני:** 20–30 תגובות בחודש, הרצה במסגרת Free Tier (עלות צפויה: 0.00$).

---

## 3. ארכיטקטורת מערכת (System Architecture)

```
[Cron Trigger: כל שעתיים / ידני]
                │
                ▼
   [1. Ingestion & Monitoring] ─── קריאה ל-Zernio / מילות מפתח + פיד
                │
                ▼
   [2. Viral Momentum & Filter] ── סינון לפי קצב צמיחה + מניעת כפילויות (SQLite)
                │
                ▼
   [3. Thread State & Context] ── בדיקה: האם זה ציוץ חדש או תגובה לבוט שלנו?
                │
                ▼
   [4. Gemini 1.5 Grounding Engine] ── בדיקת עובדות בזמן אמת בגוגל + החלטת כדאיות
                │
                ▼
   [5. Humanizer & Media Builder] ── ניסוח טבעי + הצמדת לינק/תמונה רלוונטיים
                │
                ▼
   [6. Execution & Safety Audit] ── מצב Dry-Run / Live דרך Zernio + עדכון DB
```

---

## 4. מודולים פונקציונליים מורחבים

### מודול 1: ניטור ואיסוף מידע (Ingestion & Momentum Engine)
* **חיפוש ממוקד:** מילות מפתח מוגדרות (`Israel`, `Gaza`, `IDF`, `Zionism`, `Hostages`, `Middle East`).
* **סריקת שיחות קיימות:** קריאת שרשורים שבהם משתמשים הגיבו לבוט שלנו כדי לאפשר המשכיות.
* **ציון מומנטום (Virality Score):**
  $$S = \frac{\text{Likes} \times 1.0 + \text{Retweets} \times 2.0 + \text{Replies} \times 1.5}{\text{Age in Minutes} + 10}$$
  ציוץ מקבל עדיפות אם $S > \text{Threshold}$ או אם מדובר בחשבון בעל השפעה גבוהה.

### מודול 2: ניהול מצב שרשור (Thread State Machine)
* הבוט מסוגל לנהל דיאלוג מתמשך:
  * **סבב 1 (Root Reply):** הפרכה ראשונית של הטענה השגויה בציוץ המקורי.
  * **סבב 2 (Counter Reply):** אם המשתמש מגיב בצורה עניינית או מעלה טענה נוספת – הבוט משיב פעם נוספת עם חיזוק עובדתי.
  * **סבב 3 ואילך (Disengage Rule):** עצירה אוטומטית למניעת לולאות אינסופיות ולמניעת "מריבות טוויטר" עקרות.
* **Stop-Word & Toxicity Detection:** אם המענה מכיל קללות אישיות, נאצות או טרולינג – המערכת מסמנת את השרשור כסגור ומפסיקה להגיב.

### מודול 3: מנוע אימות עובדות (Reasoning & Grounding)
* מופעל באמצעות **Gemini 1.5 Pro / Flash** עם **Google Search Grounding מובנה**.
* פלט מובנה (Structured JSON):
  ```json
  {
    "is_worth_replying": true,
    "claim_identified": "טענה ספציפית שהועלתה",
    "verified_facts": ["עובדה 1 כולל מקור", "עובדה 2"],
    "recommended_link": "https://...",
    "sentiment": "critical_factual",
    "should_attach_media": false
  }
  ```

### מודול 4: מנוע ניסוח אנושי (Humanizer & Media Module)
* **אורך:** 1–3 משפטים חדים בלבד.
* **מדיניות לינקים ותמונות:**
  * לינק מצורף רק כאשר יש צורך ישיר בהוכחה חותכת (למשל: דו"ח או"ם, מסמך היסטורי, כתבה מאומתת).
  * תמונות/מסמכים נבחרים מתוך תיקיית נכסים מקומית מאומתת (`/assets/proofs/`) ומצורפים באמצעות ה-Media ID המתאים.
* **כללי אנטי-בוט קשיחים:**
  * מחיקת Em-Dashes (`—`).
  * איסור על מילות קישור רובוטיות ("It's crucial to understand", "Delving into", "Moreover").
  * התאמה לשפת המקור.

---

## 5. סכמת בסיס הנתונים המעודכנת (SQLite Schema)

```sql
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_root_id TEXT UNIQUE NOT NULL,
    user_handle TEXT NOT NULL,
    current_turn INTEGER DEFAULT 1,
    max_turns INTEGER DEFAULT 2,
    status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE', 'COMPLETED', 'DROPPED_TOXIC'
    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processed_tweets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT UNIQUE NOT NULL,
    parent_tweet_id TEXT,
    author_handle TEXT NOT NULL,
    tweet_text TEXT NOT NULL,
    reply_generated TEXT,
    link_attached TEXT,
    media_attached TEXT,
    was_published BOOLEAN DEFAULT 0,
    virality_score REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_tweet_id) REFERENCES processed_tweets(tweet_id)
);

CREATE TABLE IF NOT EXISTS bot_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tweets_scanned INTEGER DEFAULT 0,
    replies_sent INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT
);
```

---

## 6. System Prompt רשמי למודל

```
You are a knowledgeable, articulate, and realistic digital commentator defending Israel and countering false narratives on X.

CORE PRINCIPLES:
1. Tone: "The adult in the room." Rational, concise, composed, with subtle dry wit when confronting absurd lies. Never use slurs, insults, or harassment.
2. Fact Anchoring: Only state verifiable facts, historical dates, and legal facts corroborated by Google Search.
3. Natural Human Cadence:
   - NEVER use the em-dash (—). Use commas or standard dashes.
   - Keep responses between 1 and 3 sentences.
   - Do NOT sound like a press release or an essay.
   - Reply in the EXACT language of the target tweet (English, Hebrew, French, Spanish, etc.).
4. Thread Context:
   - If this is a reply to an ongoing thread, acknowledge the user's specific objection before clarifying the facts.
   - If the counter-party is visibly trolling or insulting, advise not to engage.
```