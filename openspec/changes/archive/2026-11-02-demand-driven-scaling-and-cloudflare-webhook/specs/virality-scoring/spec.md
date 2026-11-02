# Spec Delta

## MODIFIED Requirements

### Requirement: Velocity Score Calculation
The system MUST calculate virality momentum using a hybrid formula that combines instantaneous velocity ($\frac{\text{Weighted Engagements}}{\Delta t_{\text{minutes}} + 10}$) with sustained viral impact for tweets up to 24 hours old (1,440 minutes), ensuring that high-engagement viral posts between 2 and 24 hours old are not prematurely discarded by linear minute decay.

#### Scenario: Score emerging tweet
- **WHEN** a 20-minute-old tweet has 100 likes, 50 retweets, and 20 replies
- **THEN** the instantaneous velocity score is calculated as $\frac{100 + 100 + 30}{30} = 7.67$.

#### Scenario: Score sustained viral tweet at 11 to 20 hours old
- **WHEN** an 11-hour-old (660 minutes) or 20-hour-old (1,200 minutes) tweet has accumulated strong viral engagement (e.g., 500 likes, 150 retweets, and 60 replies)
- **THEN** the hybrid virality score evaluates to at least `5.0` (`VIRAL_EMERGING` or higher) rather than falling below the threshold due to linear minute division.
