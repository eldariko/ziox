# Virality Momentum Scoring

## Purpose
Calculate engagement velocity and classify tweets into priority tiers to identify high-impact, rapidly escalating conversations before they peak.

## Requirements

### Requirement: Velocity Score Calculation
The system MUST calculate virality momentum using a hybrid formula that combines instantaneous velocity ($\frac{\text{Weighted Engagements}}{\Delta t_{\text{minutes}} + 10}$) with sustained viral impact for tweets up to 24 hours old (1,440 minutes), ensuring that high-engagement viral posts between 2 and 24 hours old are not prematurely discarded by linear minute decay.

#### Scenario: Score emerging tweet
- **WHEN** a 20-minute-old tweet has 100 likes, 50 retweets, and 20 replies
- **THEN** the instantaneous velocity score is calculated as $\frac{100 + 100 + 30}{30} = 7.67$.

#### Scenario: Score sustained viral tweet at 11 to 20 hours old
- **WHEN** an 11-hour-old (660 minutes) or 20-hour-old (1,200 minutes) tweet has accumulated strong viral engagement (e.g., 500 likes, 150 retweets, and 60 replies)
- **THEN** the hybrid virality score evaluates to at least `5.0` (`VIRAL_EMERGING` or higher) rather than falling below the threshold due to linear minute division.

### Requirement: Actionable Priority Tiers
The system MUST categorize tweets into momentum tiers based on calculated velocity:
- `VIRAL_EXPLOSIVE` (score >= 20.0)
- `VIRAL_HIGH` (score >= 10.0)
- `VIRAL_EMERGING` (score >= 5.0)
- `LOW_TRACTION` (score < 5.0)

#### Scenario: Classify explosive tweet
- **WHEN** a tweet's virality score is 25.4
- **THEN** the system classifies its tier as `VIRAL_EXPLOSIVE`.

### Requirement: Threshold Filtering
The system MUST allow filtering candidates against a configurable minimum virality threshold before queuing or generating responses.

#### Scenario: Candidate below threshold
- **WHEN** a tweet has a score of 3.2 and the configured threshold is 5.0
- **THEN** `is_viral_candidate` returns false.
