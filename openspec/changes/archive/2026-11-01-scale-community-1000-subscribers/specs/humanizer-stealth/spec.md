# Spec Delta

## ADDED Requirements

### Requirement: Configurable Link-to-Linkless Variation Mix
The humanizer MUST support a configurable `no_link_variation_ratio` (between `0.0` and `1.0`) when diversifying reply variations across a subscriber cohort so that a designated proportion of variations are formatted as pure text without an attached URL while the remaining variations rotate across distinct whitelisted proof URLs.

#### Scenario: Applying linkless ratio across a cohort batch
- **WHEN** `diversify_links_for_variations` processes 10 variations with `no_link_variation_ratio = 0.4`
- **THEN** 4 variations are sanitized as pure text with `link = None` and no trailing URL, and 6 variations receive diversified proof URLs from the whitelisted source pool.
