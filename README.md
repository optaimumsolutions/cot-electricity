# Electricity Commitments of Traders

Turns the CFTC's weekly electricity Commitments of Traders report (disaggregated, short format, futures only) into an interactive, mobile-friendly page with tabs per region and charts of who is long and short.

**Live page:** https://optaimumsolutions.github.io/cot-electricity/

## How it updates

`.github/workflows/publish.yml` runs twice a day. It pulls the current release from
`https://www.cftc.gov/dea/futures/electricity_sf.htm`, saves any new week to `data/<date>.json`,
rebuilds the site (one page per week, `index.html` = latest) and deploys it to GitHub Pages.
CFTC publishes Fridays at 3:30 pm ET for positions as of that Tuesday.

## Local use

```
python cot_electricity.py [URL] [--backfill N] [--open]   # one self-contained HTML in reports/, for email
python cot_electricity.py --site _site                    # the hosted multi-week site
```

Archive URL pattern: `https://www.cftc.gov/sites/default/files/files/dea/cotarchives/{YYYY}/futures/electricity_sf{MMDDYY}.htm`.
