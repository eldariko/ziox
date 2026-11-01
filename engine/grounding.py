"""Gemini Grounding & Fact Verification Engine."""

import json
import logging
import re
import time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logger = logging.getLogger(__name__)

INLINE_URL_REGEX = re.compile(r"https?://\S+", re.IGNORECASE)

SYSTEM_PROMPT = """
You are a knowledgeable, articulate, and realistic digital commentator defending Israel and countering false narratives on X.

CORE PRINCIPLES:
1. Tone: "The adult in the room." Rational, concise, composed, with subtle dry wit when confronting absurd lies. Never use slurs, insults, or harassment.
2. Fact Anchoring: Only state verifiable facts, historical dates, and legal/humanitarian records corroborated by verifiable sources.
3. Language Policy (STRICT):
   - Restrict replies strictly to ENGLISH and ARABIC only.
   - If the target tweet is in Arabic, draft your replies in natural, fluent, modern standard Arabic.
   - If the target tweet is in English or any other language, draft your replies in natural English.
   - NEVER generate replies in other languages (such as French, Spanish, or Hebrew).
4. Natural Human Cadence & Strict Twitter Limit:
   - NEVER use the em-dash (—). Use commas or standard dashes.
   - Keep responses strictly between 1 and 2 concise sentences.
   - STRICT LENGTH LIMIT: Tweets on X cannot exceed 280 characters. Accounting for attached proof links (which take 23 characters), EVERY draft reply text MUST NEVER EXCEED 220 CHARACTERS. Be concise, punchy, and direct.
   - STRICT NO-INLINE-URL RULE: NEVER include raw URLs (http:// or https://) inside `draft_reply` or inside any `draft_variations[].text` field! Provide URLs ONLY in `recommended_link` fields so our Humanizer can attach a single verified link cleanly without creating duplicate links.
   - Do NOT sound like a press release, an essay, or an AI summary.
   - Avoid robotic clichés and conversational filler.
5. Multi-Variation Generation (Anti-Copy-Paste Community Mode):
   - When `is_worth_replying` is true, generate up to 4 distinct variations in `draft_variations`, each using a different rhetorical style (`factual`, `sharp`, `historical_legal`, `rhetorical_question`) so multiple users can reply to the same viral post without sounding identical.
   - Each variation MUST be completely distinct in phrasing and angle, strictly under 220 characters, and contain NO inline URLs in `text`.
6. Evaluation:
   - If the tweet is pure incoherent insult, trolling, or spam, set is_worth_replying to false.
   - If it contains a specific false factual claim (e.g. regarding aid, casualties, history, treaties), set is_worth_replying to true and provide an articulate rebuttal in English or Arabic as specified above.

You MUST respond strictly in valid JSON format matching this schema:
{
  "is_worth_replying": true,
  "claim_identified": "summary of the false or misleading claim",
  "verified_facts": ["fact 1 with source/detail", "fact 2"],
  "recommended_link": "optional url to official data or null",
  "draft_reply": "1-2 punchy, composed human sentences rebutting the claim in English or Arabic (STRICTLY UNDER 220 CHARACTERS, NO INLINE URLS)",
  "draft_variations": [
    {
      "style": "factual",
      "text": "Data-driven 1-2 sentence rebuttal (UNDER 220 CHARS, NO INLINE URLS)",
      "recommended_link": null
    },
    {
      "style": "sharp",
      "text": "Composed, incisive 1-2 sentence rebuttal with dry wit (UNDER 220 CHARS, NO INLINE URLS)",
      "recommended_link": null
    },
    {
      "style": "historical_legal",
      "text": "Historical or international law anchored 1-2 sentence rebuttal (UNDER 220 CHARS, NO INLINE URLS)",
      "recommended_link": null
    },
    {
      "style": "rhetorical_question",
      "text": "Sharp rhetorical question exposing the contradiction in 1-2 sentences (UNDER 220 CHARS, NO INLINE URLS)",
      "recommended_link": null
    }
  ]
}
"""


class DraftVariation(BaseModel):
    """Represents a single persona/angle variation for multi-user community dispatch."""
    style: str = Field(default="factual", description="factual, sharp, historical_legal, or rhetorical_question")
    text: str = Field(default="", description="Reply text strictly under 220 chars without inline URLs")
    recommended_link: Optional[str] = Field(default=None)


class FactCheckResult(BaseModel):
    """Structured response from the Fact-Checking & Grounding engine."""
    is_worth_replying: bool = Field(default=False)
    claim_identified: str = Field(default="")
    verified_facts: List[str] = Field(default_factory=list)
    recommended_link: Optional[str] = Field(default=None)
    draft_reply: str = Field(default="")
    draft_variations: List[DraftVariation] = Field(default_factory=list)


def _strip_inline_urls(text: str) -> str:
    """Remove any accidental inline http/https URLs from model text so Humanizer attaches at most 1 link."""
    if not text:
        return ""
    cleaned = INLINE_URL_REGEX.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


class GroundingEngine:
    """Manages fact verification and grounded response drafting via Gemini."""

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "gemini-3.5-flash-lite",
        enable_search: bool = False,
        variations_per_tweet: int = 4,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.enable_search = enable_search
        self.search_available = enable_search
        self.variations_per_tweet = max(1, variations_per_tweet)
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                logger.warning("google-genai package not installed. Grounding will use simulated mode.")

    def _normalize_result(self, result: FactCheckResult) -> FactCheckResult:
        """
        Ensure backward compatibility between `draft_reply` and `draft_variations`,
        and strip any accidental inline URLs from narrative text fields.
        """
        result.draft_reply = _strip_inline_urls(result.draft_reply)

        cleaned_variations: List[DraftVariation] = []
        for var in result.draft_variations:
            cleaned_text = _strip_inline_urls(var.text)
            if cleaned_text:
                cleaned_variations.append(
                    DraftVariation(
                        style=var.style or "factual",
                        text=cleaned_text,
                        recommended_link=var.recommended_link or result.recommended_link,
                    )
                )

        if not cleaned_variations and result.is_worth_replying and result.draft_reply:
            cleaned_variations.append(
                DraftVariation(
                    style="factual",
                    text=result.draft_reply,
                    recommended_link=result.recommended_link,
                )
            )

        if not result.draft_reply and cleaned_variations:
            result.draft_reply = cleaned_variations[0].text

        result.draft_variations = cleaned_variations[: self.variations_per_tweet]
        return result

    def evaluate_and_draft(
        self,
        tweet_text: str,
        author_handle: str,
        num_variations: Optional[int] = None,
    ) -> FactCheckResult:
        """
        Evaluate a tweet for factual inaccuracies and draft grounded response variations.
        If no API key or package is present, returns an intelligent mock result.
        """
        target_variations = max(1, num_variations or self.variations_per_tweet)

        if not self.client:
            return self._fallback_evaluate(tweet_text, num_variations=target_variations)

        # Production Gemini Call with optional Google Search Grounding and Retry Logic
        prompt = (
            f"Tweet by @{author_handle}:\n\"{tweet_text}\"\n\n"
            f"Evaluate the tweet, verify facts if necessary, and provide structured JSON with up to "
            f"{target_variations} distinct `draft_variations` (styles: factual, sharp, historical_legal, rhetorical_question). "
            f"Remember: keep each variation text under 220 characters and NEVER place URLs inside the text field."
        )

        config_params = {
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json"
        }
        if self.search_available and types is not None:
            try:
                config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            except Exception as tool_err:
                logger.warning(f"Google Search tool configuration fallback: {tool_err}")

        max_retries = 3
        backoff_seconds = 2.0

        for attempt in range(max_retries):
            try:
                config = types.GenerateContentConfig(**config_params) if types is not None else config_params
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )

                text_output = response.text.strip()
                data = json.loads(text_output)
                result = FactCheckResult(**data)

                # Extract grounding citations from Google Search metadata if available
                if not result.recommended_link and hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    grounding_meta = getattr(candidate, "grounding_metadata", None)
                    if grounding_meta:
                        chunks = getattr(grounding_meta, "grounding_chunks", []) or []
                        for chunk in chunks:
                            web_data = getattr(chunk, "web", None)
                            if web_data and getattr(web_data, "uri", None):
                                result.recommended_link = web_data.uri
                                break

                result = self._normalize_result(result)
                result.draft_variations = result.draft_variations[:target_variations]
                return result

            except Exception as e:
                err_str = str(e)

                # If Google Search Grounding quota is exhausted (429 RESOURCE_EXHAUSTED), disable search immediately
                if "tools" in config_params and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                    logger.warning("Google Search Grounding quota exceeded (free tier). Disabling search tool and continuing with standard Gemini generation.")
                    config_params.pop("tools", None)
                    self.search_available = False
                    continue

                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning(f"Google API busy (attempt {attempt + 1}/{max_retries}): {err_str}. Retrying in {backoff_seconds}s...")
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2.0
                    if "tools" in config_params:
                        config_params.pop("tools", None)
                        self.search_available = False
                    continue
                else:
                    logger.error(f"Error calling Gemini Grounding Engine: {e}")
                    break

        # If Google API is temporarily overwhelmed, use internal verified knowledge vault
        logger.warning("Google API rate limit reached after retries. Using internal verified fact vault.")
        return self._fallback_evaluate(tweet_text, num_variations=target_variations)

    def _fallback_evaluate(self, tweet_text: str, num_variations: int = 4) -> FactCheckResult:
        """Fallback evaluation based on verified facts when API is busy or offline."""
        lower = tweet_text.lower()
        is_arabic = any("\u0600" <= c <= "\u06ff" for c in tweet_text)

        if "aid" in lower or "food" in lower or "truck" in lower or "blocked" in lower or "مساعدات" in lower or "شاحنات" in lower or "تجويع" in lower:
            if is_arabic:
                variations = [
                    DraftVariation(
                        style="factual",
                        text="دخلت أكثر من 30,000 شاحنة مساعدات ومئات الآلاف من أطنان الغذاء عبر المعابر الرسمية مثل كرم أبو سالم. الأزمة تكمن في التوزيع والنهب داخل القطاع وليس في المعابر.",
                        recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    ),
                    DraftVariation(
                        style="sharp",
                        text="غريب كيف يُتحدث عن إغلاق كامل بينما سجلات المعابر توثق دخول عشرات آلاف الشاحنات يومياً بالتنسيق مع الأمم المتحدة.",
                        recommended_link="https://gaza-aid-data.gov.il/",
                    ),
                    DraftVariation(
                        style="historical_legal",
                        text="وفق القانون الدولي الإنساني، تفي إسرائيل بالتزاماتها عبر فتح معبري كرم أبو سالم وإيرز لتدفق الإمدادات الطبية والغذائية.",
                        recommended_link="https://www.idf.il/en/mini-sites/humanitarian-missions/",
                    ),
                    DraftVariation(
                        style="rhetorical_question",
                        text="إذا كانت المساعدات ممنوعة بالكامل كما تدعي، فكيف عبرت أكثر من 30,000 شاحنة غذاء ودواء عبر كرم أبو سالم ببيانات موثقة؟",
                        recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    ),
                ]
                claim = "ادعاء منع المساعدات الإنسانية بالكامل"
            else:
                variations = [
                    DraftVariation(
                        style="factual",
                        text="Over 30,000 aid trucks and hundreds of thousands of tons of food have entered through official crossings like Kerem Shalom. Distribution bottlenecks happen inside the strip, not at the Israeli border.",
                        recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    ),
                    DraftVariation(
                        style="sharp",
                        text="Claiming 'all food is blocked' ignores over 30,000 documented aid trucks cleared through Kerem Shalom and Erez. Ignoring published crossing data does not make a false narrative true.",
                        recommended_link="https://gaza-aid-data.gov.il/",
                    ),
                    DraftVariation(
                        style="historical_legal",
                        text="Under international humanitarian mechanisms, daily UN-coordinated inspections at Kerem Shalom have facilitated hundreds of thousands of tons of food and medical supplies.",
                        recommended_link="https://www.idf.il/en/mini-sites/humanitarian-missions/",
                    ),
                    DraftVariation(
                        style="rhetorical_question",
                        text="If Israel blocked all humanitarian aid, how did over 30,000 inspected aid trucks enter Gaza via Kerem Shalom and Erez according to daily crossing manifests?",
                        recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    ),
                ]
                claim = "Claim that aid or food was completely blocked from entering Gaza"

            selected = variations[: max(1, num_variations)]
            return self._normalize_result(
                FactCheckResult(
                    is_worth_replying=True,
                    claim_identified=claim,
                    verified_facts=[
                        "COGAT records show tens of thousands of humanitarian trucks entered via Kerem Shalom and Erez crossing.",
                        "Direct daily coordination mechanisms operate with international aid agencies."
                    ],
                    recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    draft_reply=selected[0].text,
                    draft_variations=selected,
                )
            )
        elif "two state" in lower or "partition" in lower or "peace" in lower or "تقسيم" in lower or "سلام" in lower:
            if is_arabic:
                variations = [
                    DraftVariation(
                        style="factual",
                        text="الحقائق التاريخية تؤكد أن إسرائيل قبلت قرار التقسيم رقم 181 عام 1947 وعرضت إقامة دولة في كامب ديفيد عام 2000 وطابا عام 2001، بينما رُفضت هذه المبادرات.",
                        recommended_link="https://www.un.org/unispal/document/auto-insert-185393/",
                    ),
                    DraftVariation(
                        style="sharp",
                        text="تجاهل قبول إسرائيل لقرار الأمم المتحدة 181 وعروض السلام في 2000 و2008 لا يغير من السجل التاريخي الموثق شيئاً.",
                        recommended_link="https://avalon.law.yale.edu/20th_century/res181.asp",
                    ),
                ]
                claim = "ادعاء رفض إسرائيل لحل الدولتين أو التقسيم تاريخياً"
            else:
                variations = [
                    DraftVariation(
                        style="factual",
                        text="History indicates otherwise, given that Israel accepted the 1947 UN Partition Plan and later offered statehood terms at Camp David in 2000 and Taba in 2001, which were rejected by Palestinian leadership.",
                        recommended_link="https://www.un.org/unispal/document/auto-insert-185393/",
                    ),
                    DraftVariation(
                        style="historical_legal",
                        text="UN Resolution 181 in 1947 and the 2000 Camp David and 2008 Olmert peace proposals are matters of public diplomatic record accepted or initiated by Israel.",
                        recommended_link="https://avalon.law.yale.edu/20th_century/res181.asp",
                    ),
                    DraftVariation(
                        style="rhetorical_question",
                        text="If Israel never sought peace or partition, why did Jewish leadership accept UN Resolution 181 in 1947 and offer full statehood frameworks in 2000 and 2008?",
                        recommended_link="https://www.jewishvirtuallibrary.org/united-nations-partition-plan-of-1947",
                    ),
                ]
                claim = "Claim that Israel never accepted partition or peace offers"

            selected = variations[: max(1, num_variations)]
            return self._normalize_result(
                FactCheckResult(
                    is_worth_replying=True,
                    claim_identified=claim,
                    verified_facts=[
                        "Israel accepted the 1947 UN Partition Plan (Resolution 181).",
                        "Israel offered statehood terms at Camp David in 2000 and the 2008 Olmert plan."
                    ],
                    recommended_link="https://www.un.org/unispal/document/auto-insert-185393/",
                    draft_reply=selected[0].text,
                    draft_variations=selected,
                )
            )
        elif "shut up" in lower or "murderer" in lower or "evil" in lower or "قاتل" in lower or "إرهاب" in lower:
            return FactCheckResult(
                is_worth_replying=False,
                claim_identified="Ad hominem abuse or trolling",
                draft_reply="",
                draft_variations=[],
            )
        else:
            return FactCheckResult(
                is_worth_replying=False,
                claim_identified="General commentary without verifiable false premise",
                draft_reply="",
                draft_variations=[],
            )
