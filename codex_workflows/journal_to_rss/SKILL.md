# Journal Name to RSS Feed

Use this workflow when a user only knows journal or publisher names and needs RSS/Atom feed URLs for `config/app.yml`.

## Goal

Find official RSS/Atom feed URLs for journals, verify that they are likely usable, and return YAML entries that can be added under `feeds:` in `config/app.yml`.

## Instructions for Codex

1. Ask the user for the journal names if they were not provided.
2. Search the web for each journal's official RSS, Atom, alerts, current issue feed, latest articles feed, or table-of-contents feed.
3. Prefer official publisher or journal domains over third-party aggregators.
4. For ScienceDirect journals, prefer URLs like:
   `https://rss.sciencedirect.com/publication/science/{ISSN_WITHOUT_DASH}`
5. For Wiley journals, prefer URLs like:
   `https://onlinelibrary.wiley.com/action/showFeed?type=etoc&feed=rss&jc={JOURNAL_CODE_OR_EISSN}`
6. For Nature Portfolio journals, check whether the journal has a short-code RSS URL like:
   `https://www.nature.com/{journal_code}.rss`
7. For Springer journals, check whether a journal-id search RSS URL is available.
8. For arXiv categories, use the arXiv API query format already shown in `config/app.yml`.
9. Verify each candidate by opening it or checking that it returns XML/RSS/Atom-like content.
10. Return concise results with sources and a ready-to-paste YAML snippet.

## Output Format

```yaml
feeds:
  - name: "Journal Name"
    url: "https://example.com/feed.rss"
```

Also include:

- `verified`: yes/no
- `source`: official page URL used to identify the feed
- `notes`: any caveat, such as access blocks, redirects, or no official feed found

## Prompt Users Can Copy

```text
I am using the rss-ai-summary-share project. I only know these journal names:

- Journal A
- Journal B

Please search for official RSS or Atom feed URLs for them. Prefer publisher-owned feeds, verify the feed content when possible, and give me YAML entries that I can add under feeds: in config/app.yml. If no official feed exists, suggest the safest alternative and explain the caveat.
```
