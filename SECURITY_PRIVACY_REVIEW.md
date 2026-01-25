## Security and Privacy Review

This document summarizes the security and privacy review for the enhanced route planning system.

### Data Collected
- **User preferences:** discipline, typical distance, surfaces, avoided areas.
- **Route history:** distances, elevations, feedback, timestamps.
- **Conversation context:** recent entities and clarification state.
- **System logs:** error and performance logs (no raw API keys).

### Data Retention
- **User preferences:** retained until user deletion request.
- **Route history:** retained up to 12 months for personalization.
- **Evaluation logs:** retained up to 90 days for model tuning.
- **Operational logs:** retained up to 30 days.
- **Knowledge chunks:** non-user data retained long-term.

Retention periods can be adjusted via configuration and database cleanup jobs.

### API Key Handling
- API keys loaded via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ORS_API_KEY`, `TRAILFORKS_API_KEY`).
- Keys are not stored in the database or logged.
- Feature flags allow disabling external API usage.

### External API Compliance
- Trailforks and OpenRouteService are optional and can be disabled.
- Requests are limited to necessary data and cached to reduce repeated calls.
- Ensure API usage aligns with provider terms and quotas.

### Security Controls
- No plaintext secrets in source code.
- Feature flags provide safe rollback for experimental features.
- Database access through application layer; no direct client exposure.

### Privacy Considerations
- Avoid storing raw chat transcripts unless required for support.
- Prefer aggregated metrics over raw user data for analytics.
- Provide a clear user deletion flow for preferences and history.

### Follow-up Actions
- Periodic dependency audit (weekly or per release).
- Add automated secret scanning in CI.
- Review retention policies quarterly.
