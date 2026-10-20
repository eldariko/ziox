# Virality Momentum Scoring

## Purpose
Calculate engagement velocity and classify tweets into priority tiers to identify high-impact, rapidly escalating conversations before they peak.

## Requirements

### Requirement: Velocity Score Calculation
The system MUST calculate virality momentum using weighted engagements divided by tweet age with a smoothing offset:
$$\text{Score} = \frac{\text{Likes} \times 1.0 + \text{Retweets} \times 2.0 + \text{Replies} \times 1.5}{\Delta t_{\text{minutes}} + 10}$$

#### Scenario: Score emerging tweet
- **WHEN** a 20-minute-old tweet has 100 likes, 50 retweets, and 20 replies
- **THEN** the virality score is calculated as $\frac{100 + 100 + 30}{30} = 7.67$.

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
