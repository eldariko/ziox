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

STYLE_CYCLE = ["factual", "sharp", "historical_legal", "rhetorical_question"]

DEFAULT_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-3.5-flash-lite",
]

SYSTEM_PROMPT = """
You are a knowledgeable, articulate, and realistic digital commentator defending Israel and countering false narratives on X.

CORE PRINCIPLES:
1. Tone: "The adult in the room." Rational, concise, composed, with subtle dry wit when confronting absurd lies. Never use slurs, insults, or harassment.
2. Fact Anchoring: Only state verifiable facts, historical dates, and legal/humanitarian records corroborated by verifiable sources.
3. Language Policy (STRICT):
   - Restrict all evaluation, rationale, and draft replies strictly to ENGLISH ONLY.
   - Regardless of the input tweet language, ALWAYS compose all replies, verdicts, and variations exclusively in natural, fluent English.
   - NEVER generate replies in Arabic, Hebrew, or any other non-English language.
4. Natural Human Cadence & Strict Twitter Limit:
   - NEVER use the em-dash (—). Use commas or standard dashes.
   - Keep responses strictly between 1 and 2 concise sentences.
   - STRICT LENGTH LIMIT: Tweets on X cannot exceed 280 characters. Accounting for attached proof links (which take 23 characters), EVERY draft reply text MUST NEVER EXCEED 220 CHARACTERS. Be concise, punchy, and direct.
   - STRICT NO-INLINE-URL RULE: NEVER include raw URLs (http:// or https://) inside `draft_reply` or inside any `draft_variations[].text` field! Provide URLs ONLY in `recommended_link` fields so our Humanizer can attach a single verified link cleanly without creating duplicate links.
   - STRICT LINK SPECIFICITY RULE: NEVER provide bare domain root homepages (e.g., `https://www.timesofisrael.com` or `https://www.bbc.com`) in `recommended_link`! Either provide a deep-linked official document/dashboard URL (such as `https://govextra.gov.il/cogat/humanitarian-efforts/home/` or `https://www.un.org/unispal/document/auto-insert-185393/`) or set `recommended_link` to `null` so our verified proof vault can attach an official source automatically.
   - Do NOT sound like a press release, an essay, or an AI summary.
   - Avoid robotic clichés and conversational filler.
5. Multi-Variation Generation (Anti-Copy-Paste Community Mode):
   - When `is_worth_replying` is true, generate the requested number of distinct variations in `draft_variations`, cycling across rhetorical styles (`factual`, `sharp`, `historical_legal`, `rhetorical_question`) and varied sub-angles (data breakdown, historical context, international law, concise 1-sentence punchline, Socratic question, logistical realities) so multiple users can reply to the same viral post without sounding identical.
   - Each variation MUST be completely distinct in phrasing and angle, strictly under 220 characters, and contain NO inline URLs in `text`.
6. Evaluation:
   - If the tweet is pure incoherent insult, trolling, or spam, set is_worth_replying to false.
   - If it contains a specific false factual claim (e.g. regarding aid, casualties, history, treaties), set is_worth_replying to true and provide an articulate rebuttal strictly in English as specified above.

You MUST respond strictly in valid JSON format matching this schema:
{
  "is_worth_replying": true,
  "claim_identified": "summary of the false or misleading claim",
  "verified_facts": ["fact 1 with source/detail", "fact 2"],
  "recommended_link": "optional deep url to official data or null (NEVER a bare domain homepage)",
  "draft_reply": "1-2 punchy, composed human sentences rebutting the claim in English only (STRICTLY UNDER 220 CHARACTERS, NO INLINE URLS)",
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


def _sanitize_recommended_link(url: Optional[str]) -> Optional[str]:
    """Strip bare non-whitelisted domain homepages (e.g., https://www.timesofisrael.com) from recommended_link."""
    if not url or not isinstance(url, str):
        return None
    clean = url.strip()
    if not clean:
        return None
    from engine.link_validator import LinkValidator
    if LinkValidator.is_bare_homepage(clean):
        logger.info(f"Stripping bare domain homepage '{clean}' from recommended_link.")
        return None
    return clean


class GroundingEngine:
    """Manages fact verification and grounded response drafting via Gemini."""

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "gemini-2.5-flash",
        fallback_models: Optional[List[str]] = None,
        enable_search: bool = False,
        variations_per_tweet: int = 4,
        max_variations_per_call: int = 10,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.fallback_models = self._build_model_chain(model_name, fallback_models)
        self.enable_search = enable_search
        self.search_available = enable_search
        self.variations_per_tweet = max(1, variations_per_tweet)
        self.max_variations_per_call = max(1, max_variations_per_call)
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                logger.warning("google-genai package not installed. Grounding will use simulated mode.")

    @staticmethod
    def _build_model_chain(primary: str, fallbacks: Optional[List[str]] = None) -> List[str]:
        """Build an ordered, deduplicated list of models starting with `primary`."""
        chain: List[str] = []
        candidates = [primary] + (list(fallbacks) if fallbacks is not None else list(DEFAULT_FALLBACK_MODELS))
        for m in candidates:
            clean_m = (m or "").strip()
            if clean_m and clean_m not in chain:
                chain.append(clean_m)
        return chain or ["gemini-2.5-flash"]

    def _normalize_result(self, result: FactCheckResult, max_count: Optional[int] = None) -> FactCheckResult:
        """
        Ensure backward compatibility between `draft_reply` and `draft_variations`,
        strip any accidental inline URLs from narrative text fields, and filter out
        bare non-whitelisted domain homepages from `recommended_link`.
        """
        limit = max_count if max_count is not None else self.variations_per_tweet
        result.draft_reply = _strip_inline_urls(result.draft_reply)
        result.recommended_link = _sanitize_recommended_link(result.recommended_link)

        cleaned_variations: List[DraftVariation] = []
        for var in result.draft_variations:
            cleaned_text = _strip_inline_urls(var.text)
            sanitized_var_link = _sanitize_recommended_link(var.recommended_link) or result.recommended_link
            if cleaned_text:
                cleaned_variations.append(
                    DraftVariation(
                        style=var.style or "factual",
                        text=cleaned_text,
                        recommended_link=sanitized_var_link,
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

        result.draft_variations = cleaned_variations[: max(1, limit)]
        return result

    def evaluate_and_draft(
        self,
        tweet_text: str,
        author_handle: str,
        num_variations: Optional[int] = None,
        excluded_texts: Optional[List[str]] = None,
    ) -> FactCheckResult:
        """
        Evaluate a tweet for factual inaccuracies and draft grounded response variations.
        If no API key or package is present, returns an intelligent mock result.
        """
        target_variations = max(1, num_variations or self.variations_per_tweet)

        if not self.client:
            return self._fallback_evaluate(
                tweet_text,
                num_variations=target_variations,
                excluded_texts=excluded_texts,
            )

        exclusion_clause = ""
        if excluded_texts:
            sample_excluded = "\n".join(f"- {t}" for t in excluded_texts[:20])
            exclusion_clause = (
                f"\n\nIMPORTANT: Do NOT repeat or closely paraphrase any of these already-used replies:\n"
                f"{sample_excluded}\nUse fresh angles, different openings, and distinct vocabulary."
            )

        # Production Gemini Call with optional Google Search Grounding, Schema Enforcement, and Multi-Model Fallback
        prompt = (
            f"Tweet by @{author_handle}:\n\"{tweet_text}\"\n\n"
            f"Evaluate the tweet, verify facts if necessary, and provide structured JSON with up to "
            f"{target_variations} distinct `draft_variations` (styles: factual, sharp, historical_legal, rhetorical_question). "
            f"Remember: keep each variation text under 220 characters and NEVER place URLs inside the text field."
            f"{exclusion_clause}"
        )

        config_params: Dict[str, Any] = {
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": FactCheckResult,
        }
        if self.search_available and types is not None:
            try:
                config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]
                # Google GenAI SDK may disallow combining GoogleSearch tool with response_schema on some endpoints
                config_params.pop("response_schema", None)
            except Exception as tool_err:
                logger.warning(f"Google Search tool configuration fallback: {tool_err}")

        max_retries = max(3, len(self.fallback_models))
        backoff_seconds = 2.0

        for attempt in range(max_retries):
            active_model = self.fallback_models[attempt % len(self.fallback_models)]
            try:
                config: Optional[types.GenerateContentConfig] = (
                    types.GenerateContentConfig(**config_params) if types is not None else None
                )
                response = self.client.models.generate_content(
                    model=active_model,
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
                                candidate_uri = _sanitize_recommended_link(web_data.uri)
                                if candidate_uri:
                                    result.recommended_link = candidate_uri
                                    break

                result = self._normalize_result(result, max_count=target_variations)
                return result

            except Exception as e:
                err_str = str(e)

                # If Google Search Grounding quota is exhausted (429 RESOURCE_EXHAUSTED), disable search for session
                if "tools" in config_params and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                    logger.warning("Google Search Grounding quota exceeded. Disabling search tool and continuing with standard Gemini generation.")
                    config_params.pop("tools", None)
                    config_params["response_schema"] = FactCheckResult
                    self.search_available = False
                    continue

                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str or "NOT_FOUND" in err_str:
                    next_model = self.fallback_models[(attempt + 1) % len(self.fallback_models)]
                    logger.warning(
                        f"Google API busy on model '{active_model}' (attempt {attempt + 1}/{max_retries}): {err_str}. "
                        f"Retrying in {backoff_seconds}s with model '{next_model}'..."
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2.0
                    # On transient 503 with search tools enabled, drop search tool ONLY for the remaining retries of this call
                    # without permanently disabling self.search_available for future tweets
                    if "tools" in config_params:
                        config_params.pop("tools", None)
                        config_params["response_schema"] = FactCheckResult
                    continue
                else:
                    logger.error(f"Error calling Gemini Grounding Engine ({active_model}): {e}")
                    break

        # If Google API is temporarily overwhelmed across all fallback models, use internal verified knowledge vault
        logger.warning("Google API rate limit reached after retries. Using internal verified fact vault.")
        return self._fallback_evaluate(
            tweet_text,
            num_variations=target_variations,
            excluded_texts=excluded_texts,
        )

    def generate_variations_batch(
        self,
        tweet_text: str,
        author_handle: str,
        total_variations: int = 10,
        max_per_call: Optional[int] = None,
    ) -> FactCheckResult:
        """
        Generate up to `total_variations` unique reply variations for subscriber cohorts
        of any size (e.g., 5, 25, or 50+ subscribers per wave).
        - Executes bounded batch calls of up to `max_per_call` (default `self.max_variations_per_call = 10`).
        - Passes previously generated texts as `excluded_texts` on subsequent batches so
          every variation in the returned `FactCheckResult.draft_variations` has a unique phrasing.
        """
        target_total = max(1, int(total_variations))
        batch_cap = max(1, int(max_per_call or self.max_variations_per_call))

        first_batch_size = min(target_total, batch_cap)
        base_result = self.evaluate_and_draft(
            tweet_text=tweet_text,
            author_handle=author_handle,
            num_variations=first_batch_size,
        )

        if not base_result.is_worth_replying or target_total <= len(base_result.draft_variations):
            base_result.draft_variations = base_result.draft_variations[:target_total]
            return base_result

        collected: List[DraftVariation] = list(base_result.draft_variations)
        seen_texts = {v.text.strip() for v in collected if v.text.strip()}

        # Calculate how many additional batch calls are needed
        max_batches = ((target_total - 1) // batch_cap) + 2
        batches_run = 1

        while len(collected) < target_total and batches_run < max_batches:
            remaining = target_total - len(collected)
            this_batch_size = min(remaining, batch_cap)
            batches_run += 1

            next_res = self.evaluate_and_draft(
                tweet_text=tweet_text,
                author_handle=author_handle,
                num_variations=this_batch_size,
                excluded_texts=list(seen_texts),
            )
            if not next_res.is_worth_replying or not next_res.draft_variations:
                break

            added_in_batch = 0
            for var in next_res.draft_variations:
                clean_t = var.text.strip()
                if clean_t and clean_t not in seen_texts:
                    seen_texts.add(clean_t)
                    collected.append(var)
                    added_in_batch += 1
                    if len(collected) >= target_total:
                        break

            if added_in_batch == 0:
                break

        base_result.draft_variations = collected[:target_total]
        return base_result

    def _fallback_evaluate(
        self,
        tweet_text: str,
        num_variations: int = 4,
        excluded_texts: Optional[List[str]] = None,
    ) -> FactCheckResult:
        """Fallback evaluation based on verified facts when API is busy or offline."""
        lower = tweet_text.lower()
        is_arabic = any("\u0600" <= c <= "\u06ff" for c in tweet_text)
        excluded_set = set(excluded_texts or [])

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
                    DraftVariation(
                        style="factual",
                        text="تقارير التنسيق اليومية تؤكد عبور مئات الشاحنات المحملة بالغذاء والدواء أسبوعياً، بينما تتراكم البضائع في الجانب الآخر بانتظار التوزيع.",
                        recommended_link="https://gaza-aid-data.gov.il/",
                    ),
                    DraftVariation(
                        style="sharp",
                        text="الادعاء بمنع الغذاء يتجاهل عمداً آلاف الأطنان التي تم تفتيشها وإدخالها عبر المعابر الرسمية تحت إشراف دولي.",
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
                    DraftVariation(
                        style="factual",
                        text="Daily COGAT manifests document hundreds of thousands of tons of flour, medical gear, and shelter supplies cleared into Gaza through Kerem Shalom.",
                        recommended_link="https://gaza-aid-data.gov.il/",
                    ),
                    DraftVariation(
                        style="sharp",
                        text="Hundreds of inspected aid trucks sit waiting on the Gaza side of Kerem Shalom for UN pickup. Blaming the border crossing for internal distribution failures is dishonest.",
                        recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    ),
                    DraftVariation(
                        style="historical_legal",
                        text="Israel maintains open humanitarian corridors at Kerem Shalom and Erez in full compliance with international law, clearing thousands of aid shipments every month.",
                        recommended_link="https://www.idf.il/en/mini-sites/humanitarian-missions/",
                    ),
                    DraftVariation(
                        style="rhetorical_question",
                        text="Why blame border inspections when UN agencies themselves acknowledge that hundreds of cleared aid trucks wait inside Gaza for internal collection?",
                        recommended_link="https://gaza-aid-data.gov.il/",
                    ),
                ]
                claim = "Claim that aid or food was completely blocked from entering Gaza"

            expanded = self._expand_fallback_variations(variations, num_variations, excluded_set, is_arabic)
            return self._normalize_result(
                FactCheckResult(
                    is_worth_replying=True,
                    claim_identified=claim,
                    verified_facts=[
                        "COGAT records show tens of thousands of humanitarian trucks entered via Kerem Shalom and Erez crossing.",
                        "Direct daily coordination mechanisms operate with international aid agencies."
                    ],
                    recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    draft_reply=expanded[0].text,
                    draft_variations=expanded,
                ),
                max_count=num_variations,
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

            expanded = self._expand_fallback_variations(variations, num_variations, excluded_set, is_arabic)
            return self._normalize_result(
                FactCheckResult(
                    is_worth_replying=True,
                    claim_identified=claim,
                    verified_facts=[
                        "Israel accepted the 1947 UN Partition Plan (Resolution 181).",
                        "Israel offered statehood terms at Camp David in 2000 and the 2008 Olmert plan."
                    ],
                    recommended_link="https://www.un.org/unispal/document/auto-insert-185393/",
                    draft_reply=expanded[0].text,
                    draft_variations=expanded,
                ),
                max_count=num_variations,
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

    @staticmethod
    def _expand_fallback_variations(
        base_variations: List[DraftVariation],
        target_count: int,
        excluded_set: set,
        is_arabic: bool = False,
    ) -> List[DraftVariation]:
        """
        Deterministically synthesize additional distinct variations when offline/fallback mode
        is asked for larger cohorts (e.g., 10 to 50 variations) so unit/scale tests and
        fallback runs receive `target_count` unique texts <= 220 characters.
        """
        results: List[DraftVariation] = []
        seen = set(excluded_set)

        for v in base_variations:
            if v.text not in seen:
                seen.add(v.text)
                results.append(v)
                if len(results) >= target_count:
                    return results

        en_prefixes = [
            "Verified crossing logs confirm:",
            "Look at the actual numbers:",
            "Public humanitarian data shows:",
            "According to documented shipment records,",
            "Official inspection logs demonstrate:",
            "Check the daily crossing manifests:",
            "Published logistics records verify:",
            "Documented border data proves:",
        ]
        ar_prefixes = [
            "تؤكد السجلات الرسمية:",
            "وفق البيانات الموثقة:",
            "تثبت تقارير المعابر اليومية:",
            "بالعودة إلى الأرقام الفعلية:",
        ]
        prefixes = ar_prefixes if is_arabic else en_prefixes

        idx = 0
        while len(results) < target_count:
            template = base_variations[idx % len(base_variations)]
            prefix = prefixes[(idx // len(base_variations)) % len(prefixes)]
            style = STYLE_CYCLE[len(results) % len(STYLE_CYCLE)]
            seq_num = len(results) + 1
            body = template.text[0].lower() + template.text[1:] if not is_arabic and template.text else template.text
            candidate_text = f"{prefix} {body}"
            if len(candidate_text) > 215 or candidate_text in seen:
                # Guarantee uniqueness and <220 chars
                short_base = template.text[:180].rstrip("., ")
                candidate_text = f"{short_base} (Ref #{seq_num})."
            if candidate_text not in seen:
                seen.add(candidate_text)
                results.append(
                    DraftVariation(
                        style=style,
                        text=candidate_text,
                        recommended_link=template.recommended_link,
                    )
                )
            idx += 1
            if idx > target_count * 4:
                break

        return results
