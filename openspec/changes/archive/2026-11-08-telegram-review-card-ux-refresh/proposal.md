# Proposal: Telegram Review Card UX Refresh

## Why

The current Telegram review cards present raw diagnostic numbers (`[LOW_TRACTION | Score: 19.8]`), unformatted multi-fact lines separated by pipes (` | `), and lack visual hierarchy. For mobile volunteers responding during breaking events or advocacy campaigns, this dense "wall of text" increases cognitive friction and delays action.

Adopting Option A ("Scannable, Action-First & Tap-to-Copy UX") introduces clear visual sectioning (`━━━━━━━━━━━━━━━━━━`), Telegram native `<blockquote>` styling for external tweet snippets, structured bulleted facts (`•`), and standard `<code>` blocks for one-tap copying on mobile clients.

## What Changes

- **Visual Hierarchy & Header**: Modernize `TelegramDispatcher.format_review_card` to lead with a clean branded alert header (`🎯 <b>zioX Review Alert</b>`) separated by visual divider lines (`━━━━━━━━━━━━━━━━━━`), omitting internal raw virality scores from the volunteer-facing view while highlighting the target author (`👤 <b>יעד:</b> @<author>`).
- **Native Blockquotes for Snippets**: Wrap quoted original tweet text inside Telegram's native `<blockquote>"..."</blockquote>` tags so it renders with Telegram's stylized vertical quotation bar.
- **Dedicated Claim Flagging**: Display the flagged narrative distortion with dedicated emoji and styling (`⚠️ <b>ההטיה שזוהתה:</b> <claim>`).
- **Structured Facts List**: Render cited verified facts as distinct vertical bullet items (`• <fact>`), eliminating crowded single-line pipe concatenations (` | `).
- **One-Tap Copyable Reply**: Wrap the proposed reply in `<code>...</code>` block formatting labeled `💡 <b>תגובה מוצעת</b> (העתקה בלחיצה):` so users can tap anywhere on the text block to instantly copy the reply into their clipboard on iOS/Android Telegram clients.
- **HTML Safety**: Maintain strict `html.escape()` sanitization across all interpolated parameters to prevent parse errors or injection attacks.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `telegram-dispatcher`: Update `Telegram Notification Dispatching` requirement to specify the scannable, blockquote-styled, bulleted facts, and tap-to-copy HTML card format.

## Impact

- **Affected Code**: `engine/telegram_dispatcher.py` (`format_review_card`), `tests/test_telegram_dispatcher.py` (updating card assertion checks), `scripts/test_telegram.py` (sample preview verification).
- **Hosting / Cost / Risk**: Zero additional cost (standard Telegram Bot API text payloads), no additional network calls or rate limit impact. Zero account ban risk as messages are sent to private Telegram chats or volunteer groups, not to X.
