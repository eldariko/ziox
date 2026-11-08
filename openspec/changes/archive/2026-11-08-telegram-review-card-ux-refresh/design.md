# Design: Telegram Review Card UX Refresh

## Context

See `proposal.md` for motivation. Currently, `TelegramDispatcher.format_review_card` generates HTML messages sent via Telegram Bot API `sendMessage` (`parse_mode="HTML"`). While Telegram Bot API supports HTML tags like `<b>`, `<i>`, `<code>`, and `<blockquote>`, the current implementation formats all elements in a single dense block with unstyled facts and visible raw pipeline scores.

## Goals / Non-Goals

**Goals:**
- Implement Option A structure: Clean header, clear separation dividers, native Telegram `<blockquote>` for original tweets, structured bullet points for facts, and tap-to-copy `<code>` block for the proposed reply.
- Ensure 100% strict `html.escape` coverage on all injected strings so special characters (`&`, `<`, `>`, `"`) never break Telegram's HTML parser.
- Keep the card compact and readable on small mobile screens (e.g. limiting snippet length gracefully to 200 characters with ellipsis).
- Maintain backward compatibility with the existing `dispatch_review` signature and all unit tests.

**Non-Goals:**
- Modifying Telegram interactive keyboards or callback handling.
- Changing Cloudflare Worker logic (the worker does not generate candidate review cards; it only handles inbound commands/callbacks).
- Adding rich media/image generation to Telegram review cards.

## Decisions

### Decision 1: Use Native Telegram `<blockquote>` for Quoted Tweets
- **Rationale**: Telegram introduced official `<blockquote>` support in recent Bot API updates. On all mobile and desktop clients, `<blockquote>` displays a distinct colored vertical bar and indented italicized text, making it instantly recognizable as external quote material distinct from zioX analysis.
- **Alternatives Considered**: Using plain italics (`<i>"..."</i>`) which blends in with regular text and offers no visual border.

### Decision 2: Vertical Bullet Points for Cited Facts
- **Rationale**: The previous format used ` | ` to join multiple facts into a single continuous sentence. Converting this to `• <fact>` across separate lines creates scannable, bite-sized evidence that users can digest in under 3 seconds.
- **Alternatives Considered**: Markdown numbered lists or bolding each fact inline. Bulleted vertical lines (`\n• `) offer the cleanest visual presentation in mobile Telegram chats.

### Decision 3: Tap-to-Copy `<code>` Wrapping for the Reply Draft
- **Rationale**: On Telegram mobile apps (iOS & Android), tapping text enclosed in `<code>` or `<pre>` automatically copies the contents directly to the device clipboard without requiring text selection handles.
- **Alternatives Considered**: Providing a third inline button for copy (unsupported by Telegram Bot API without a Web App modal) or plain text requiring manual highlighting.

## Risks / Trade-offs

- **[Risk] Telegram HTML Parse Error on Unescaped Characters**: If user handles or tweet text contain unescaped XML/HTML entities, Telegram returns `400 Bad Request: can't parse entities`.
  - **Mitigation**: All interpolated variables (`author_handle`, `tweet_text`, `claim_flagged`, `verified_facts`, `draft_reply`) must pass through `html.escape()`.
- **[Risk] Long Fact Lists Exceeding 4096 Telegram Message Limit**:
  - **Mitigation**: Facts are already generated in concise arrays (usually 1-3 items) by the Grounding engine, and the tweet snippet is capped at 200 chars. Total card length remains safely below 1,000 characters.
