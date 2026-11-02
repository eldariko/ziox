# Spec Delta

## ADDED Requirements

### Requirement: Combined Top and Latest Search with Maximum Age Window
The system MUST query both X's `Top` and `Latest` search tabs when scanning for candidate tweets, deduplicate results by tweet ID, and filter out tweets older than a configurable maximum age window (`max_tweet_age_hours`, default `24` hours) so that high-traction viral posts from the past 24 hours are captured alongside breaking posts.

#### Scenario: Blend Top and Latest search results within 24-hour window
- **WHEN** the radar scans a consolidated search query with `max_tweet_age_hours = 24`
- **THEN** the provider retrieves results from both `Top` and `Latest`, merges unique tweets, retains viral tweets up to 24 hours old (including 11-hour and 20-hour viral posts), and excludes stale posts older than 24 hours.
