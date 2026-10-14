"""Gemini Grounding & Fact Verification Engine."""

import json
import logging
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

SYSTEM_PROMPT = """
You are a knowledgeable, articulate, and realistic digital commentator defending Israel and countering false narratives on X.

CORE PRINCIPLES:
1. Tone: "The adult in the room." Rational, concise, composed, with subtle dry wit when confronting absurd lies. Never use slurs, insults, or harassment.
2. Fact Anchoring: Only state verifiable facts, historical dates, and legal/humanitarian records corroborated by verifiable sources.
3. Natural Human Cadence:
   - NEVER use the em-dash (—). Use commas or standard dashes.
   - Keep responses strictly between 1 and 3 sentences.
   - Do NOT sound like a press release, an essay, or an AI summary.
   - Reply in the EXACT language of the target tweet (English, Hebrew, French, Spanish, etc.).
4. Evaluation:
   - If the tweet is pure incoherent insult, trolling, or spam, set is_worth_replying to false.
   - If it contains a specific false factual claim (e.g. regarding aid, casualties, history, treaties), set is_worth_replying to true and provide an articulate rebuttal.

You MUST respond strictly in valid JSON format matching this schema:
{
  "is_worth_replying": true,
  "claim_identified": "summary of the false or misleading claim",
  "verified_facts": ["fact 1 with source/detail", "fact 2"],
  "recommended_link": "optional url to official data or null",
  "draft_reply": "1-3 punchy, composed human sentences rebutting the claim in the target tweet's language"
}
"""


class FactCheckResult(BaseModel):
    """Structured response from the Fact-Checking & Grounding engine."""
    is_worth_replying: bool = Field(default=False)
    claim_identified: str = Field(default="")
    verified_facts: List[str] = Field(default_factory=list)
    recommended_link: Optional[str] = Field(default=None)
    draft_reply: str = Field(default="")


class GroundingEngine:
    """Manages fact verification and grounded response drafting via Gemini."""

    def __init__(self, api_key: str = "", model_name: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except ImportError:
                logger.warning("google-genai package not installed. Grounding will use simulated mode.")

    def evaluate_and_draft(self, tweet_text: str, author_handle: str) -> FactCheckResult:
        """
        Evaluate a tweet for factual inaccuracies and draft a grounded response.
        If no API key or package is present, returns an intelligent mock result.
        """
        if not self.client:
            # Fallback mock evaluation for local testing
            if "blocked all food" in tweet_text.lower() or "humanitarian aid" in tweet_text.lower():
                return FactCheckResult(
                    is_worth_replying=True,
                    claim_identified="Claim that all aid and food was blocked",
                    verified_facts=[
                        "COGAT records show tens of thousands of humanitarian trucks entered via Kerem Shalom and Erez crossing.",
                        "Direct coordination mechanisms operate daily with UN agencies."
                    ],
                    recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                    draft_reply="Over 30,000 aid trucks and hundreds of thousands of tons of food have entered through official crossings like Kerem Shalom. Aid distribution bottlenecks inside the strip happen on the ground, not at the Israeli border."
                )
            elif "shut up" in tweet_text.lower() or "murderers" in tweet_text.lower():
                return FactCheckResult(
                    is_worth_replying=False,
                    claim_identified="Ad hominem abuse",
                    draft_reply=""
                )
            else:
                return FactCheckResult(
                    is_worth_replying=False,
                    claim_identified="General commentary without verifiable false premise",
                    draft_reply=""
                )

        # Production Gemini Call with Google Search Grounding and Retry Logic
        prompt = f"Tweet by @{author_handle}:\n\"{tweet_text}\"\n\nEvaluate the tweet, verify facts via Google Search if necessary, and provide structured JSON."

        config_params = {
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json"
        }
        if types is not None:
            try:
                config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            except Exception as tool_err:
                logger.warning(f"Google Search tool configuration fallback: {tool_err}")

        max_retries = 3
        backoff_seconds = 2.0
        last_error = None

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

                return result

            except Exception as e:
                err_str = str(e)
                last_error = err_str
                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning(f"Google API busy (attempt {attempt + 1}/{max_retries}): {err_str}. Retrying in {backoff_seconds}s...")
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2.0
                    if "tools" in config_params and attempt >= 1:
                        config_params.pop("tools", None)
                    continue
                else:
                    logger.error(f"Error calling Gemini Grounding Engine: {e}")
                    break

        # If Google API is temporarily overwhelmed, use internal verified knowledge vault
        logger.warning(f"Google API rate limit reached after retries. Using internal verified fact vault.")
        return self._fallback_evaluate(tweet_text)

    def _fallback_evaluate(self, tweet_text: str) -> FactCheckResult:
        """Fallback evaluation based on verified facts when API is busy or offline."""
        lower = tweet_text.lower()
        if "aid" in lower or "food" in lower or "truck" in lower or "blocked" in lower:
            return FactCheckResult(
                is_worth_replying=True,
                claim_identified="Claim that aid or food was completely blocked from entering Gaza",
                verified_facts=[
                    "COGAT records show tens of thousands of humanitarian trucks entered via Kerem Shalom and Erez crossing.",
                    "Direct daily coordination mechanisms operate with international aid agencies."
                ],
                recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                draft_reply="Over 30,000 aid trucks and hundreds of thousands of tons of food have entered through official crossings like Kerem Shalom. Aid distribution bottlenecks inside the strip happen on the ground, not at the Israeli border."
            )
        elif "two state" in lower or "partition" in lower or "peace" in lower:
            return FactCheckResult(
                is_worth_replying=True,
                claim_identified="Claim that Israel never accepted partition or peace offers",
                verified_facts=[
                    "Israel accepted the 1947 UN Partition Plan (Resolution 181).",
                    "Israel offered statehood terms at Camp David in 2000 and the 2008 Olmert plan."
                ],
                recommended_link="https://www.un.org/unispal/document/auto-insert-179838/",
                draft_reply="History indicates otherwise, given that Israel accepted the 1947 UN Partition Plan and later offered statehood terms at Camp David in 2000 and Taba in 2001, which were rejected by Palestinian leadership."
            )
        elif "shut up" in lower or "murderer" in lower or "evil" in lower:
            return FactCheckResult(
                is_worth_replying=False,
                claim_identified="Ad hominem abuse or trolling",
                draft_reply=""
            )
        else:
            return FactCheckResult(
                is_worth_replying=False,
                claim_identified="General commentary without verifiable false premise",
                draft_reply=""
            )
