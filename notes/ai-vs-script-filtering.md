# AI Filtering vs Script Filtering

Controlled by `ai_filter` in `config.yaml` under `scraper:`.

| | AI Filtering (`ai_filter: true`) | Script Filtering (`ai_filter: false`) |
|---|---|---|
| **How it classifies** | Claude reads the full job description | Keyword match on job title only |
| **Handles ambiguous titles** | Yes — e.g. "Engineer I" gets analyzed | No — falls through to review |
| **Unmatched jobs** | Accepted or filtered based on Claude's judgment | Always flagged for review |
| **Confidence score** | Provided | Not provided |
| **Category** | Claude assigns best-fit category | Keyword match assigns, else `general_swe` |
| **YOE extraction** | Claude + regex fallback | Regex only |
| **Requires API key** | Yes | No |
| **API cost** | Yes, per job that passes keyword filter | None |
| **Speed** | Slower (API call per unmatched job) | Faster |
| **False negatives (missed relevant jobs)** | Low | Higher — unmatched titles go to review not accepted |
| **Review pile size** | Smaller — Claude reduces it | Larger — all ambiguous jobs land here |
