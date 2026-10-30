# Power & Gas Commitments of Traders

Turns the CFTC's weekly electricity and natural gas Commitments of Traders reports (disaggregated, short format, futures only) into one interactive, mobile-friendly page: an electricity overview, a tab per power region, a natural gas tab (Henry Hub headline + trends, then Henry Hub / Basis / Index / NGL groups), and a searchable table of every contract.

**Live page:** https://optaimumsolutions.github.io/cot-electricity/

## How it updates

`.github/workflows/publish.yml` runs twice a day. It pulls the current releases from
`https://www.cftc.gov/dea/futures/electricity_sf.htm` and `https://www.cftc.gov/dea/futures/nat_gas_sf.htm`,
saves any new week to `data/<market>/<date>.json`, rebuilds the site (one page per week, `index.html` = latest)
and deploys it to GitHub Pages. CFTC publishes Fridays at 3:30 pm ET for positions as of that Tuesday.

## Local use

```
python cot_electricity.py [URL ...] [--backfill N] [--open]   # one self-contained HTML in reports/, for email
python cot_electricity.py --site _site                        # the hosted multi-week site
```

Passing one market's URL also fetches the other market for the same week.
Archive URL pattern: `https://www.cftc.gov/sites/default/files/files/dea/cotarchives/{YYYY}/futures/{electricity_sf|nat_gas_sf}{MMDDYY}.htm`.
