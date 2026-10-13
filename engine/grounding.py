"""Gemini Grounding & Fact Verification Engine."""

import json
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

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

    def __init__(self, api_key: str = "", model_name: str = "gemini-2.5-flash"):
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

        try:
            prompt = f"Tweet by @{author_handle}:\n\"{tweet_text}\"\n\nEvaluate the tweet and provide structured JSON."
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "response_mime_type": "application/json"
                }
            )

            text_output = response.text.strip()
            # Parse JSON
            data = json.loads(text_output)
            return FactCheckResult(**data)
        except Exception as e:
            logger.error(f"Error calling Gemini Grounding Engine: {e}")
            return FactCheckResult(
                is_worth_replying=False,
                claim_identified=f"Error evaluating claim: {str(e)}",
                draft_reply=""
            )
