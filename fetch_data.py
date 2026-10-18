#!/usr/bin/env python3
"""Hämtar dagliga slutkurser för S&P 500 och skriver data.json som sidan läser.

Aktielista (i prioritetsordning):
  1. CSV med S&P 500-medlemmar (github.com/datasets/s-and-p-500-companies)
  2. Wikipedia-tabellen "List of S&P 500 companies"
  3. En inbyggd lista med 49 stora aktier (om båda ovan misslyckas)

Kurskälla (den första som fungerar används):
  Tiingo (om TIINGO_API_KEY finns) -> Yahoo Finance -> Stooq

Användning:
  python3 fetch_data.py --out data.json
  python3 fetch_data.py --out data.json --days 800 --limit 30     # snabbtest
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

# Reservlista (ticker, namn, sektor) om indexlistan inte kan hämtas.
FALLBACK = [
    ("AAPL", "Apple", "Teknik"), ("MSFT", "Microsoft", "Teknik"), ("NVDA", "NVIDIA", "Teknik"),
    ("AMZN", "Amazon", "Konsument"), ("GOOGL", "Alphabet", "Kommunikation"),
    ("META", "Meta Platforms", "Kommunikation"), ("TSLA", "Tesla", "Konsument"),
    ("AVGO", "Broadcom", "Teknik"), ("JPM", "JPMorgan Chase", "Finans"), ("V", "Visa", "Finans"),
    ("LLY", "Eli Lilly", "Hälsa"), ("COST", "Costco", "Dagligvaror"),
    ("NFLX", "Netflix", "Kommunikation"), ("AMD", "AMD", "Teknik"), ("CRM", "Salesforce", "Teknik"),
    ("XOM", "Exxon Mobil", "Energi"), ("UNH", "UnitedHealth", "Hälsa"), ("PLTR", "Palantir", "Teknik"),
    ("ORCL", "Oracle", "Teknik"), ("ADBE", "Adobe", "Teknik"), ("WMT", "Walmart", "Dagligvaror"),
    ("MA", "Mastercard", "Finans"), ("HD", "Home Depot", "Konsument"),
    ("PG", "Procter & Gamble", "Dagligvaror"), ("JNJ", "Johnson & Johnson", "Hälsa"),
    ("BAC", "Bank of America", "Finans"), ("KO", "Coca-Cola", "Dagligvaror"),
    ("PEP", "PepsiCo", "Dagligvaror"), ("MRK", "Merck", "Hälsa"), ("ABBV", "AbbVie", "Hälsa"),
    ("CVX", "Chevron", "Energi"), ("TMO", "Thermo Fisher", "Hälsa"), ("CSCO", "Cisco", "Teknik"),
    ("MCD", "McDonald's", "Konsument"), ("DIS", "Disney", "Kommunikation"), ("INTC", "Intel", "Teknik"),
    ("QCOM", "Qualcomm", "Teknik"), ("TXN", "Texas Instruments", "Teknik"), ("NKE", "Nike", "Konsument"),
    ("PYPL", "PayPal", "Finans"), ("UBER", "Uber", "Industri"), ("SNOW", "Snowflake", "Teknik"),
    ("COIN", "Coinbase", "Finans"), ("BA", "Boeing", "Industri"), ("GS", "Goldman Sachs", "Finans"),
    ("WFC", "Wells Fargo", "Finans"), ("CAT", "Caterpillar", "Industri"), ("IBM", "IBM", "Teknik"),
    ("MU", "Micron", "Teknik"),
]

SECTOR_SV = {
    "information technology": "Teknik",
    "communication services": "Kommunikation",
    "consumer discretionary": "Konsument",
    "consumer staples": "Dagligvaror",
    "health care": "Hälsa",
    "financials": "Finans",
    "energy": "Energi",
    "industrials": "Industri",
    "materials": "Material",
    "utilities": "Försörjning",
    "real estate": "Fastigheter",
}

INDEX_TICKER = "SPY"
MIN_ROWS = 300          # modellen behöver minst ~260 handelsdagar
UA = {"User-Agent": "Mozilla/5.0 (valora-analytics data job)"}
CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def http_get(url, tries=3, wait=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(60)          # rate limit: vänta en stund
            elif e.code in (400, 401, 403, 404):
                break
            else:
                time.sleep(wait * (i + 1))
        except Exception as e:           # nätverksfel
            last = e
            time.sleep(wait * (i + 1))
    raise RuntimeError(f"misslyckades hämta {url.split('?')[0]}: {last}")


# ---------- aktielista ----------

def sector_sv(s):
    s = (s or "").strip()
    return SECTOR_SV.get(s.lower(), s or "Övrigt")


def universe_csv():
    rows = list(csv.DictReader(io.StringIO(http_get(CSV_URL))))
    out = []
    for r in rows:
        tk = (r.get("Symbol") or "").strip()
        name = (r.get("Security") or r.get("Name") or tk).strip()
        if tk:
            out.append((tk, name, sector_sv(r.get("GICS Sector") or r.get("Sector"))))
    return out


def universe_wiki():
    html = http_get(WIKI_URL)
    table = html.split('id="constituents"', 1)[1].split("</table>", 1)[0]
    strip = lambda x: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).replace("&amp;", "&").strip()
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) >= 3 and strip(tds[0]):
            out.append((strip(tds[0]), strip(tds[1]), sector_sv(strip(tds[2]))))
    return out


def get_universe():
    for label, fn in (("CSV", universe_csv), ("Wikipedia", universe_wiki)):
        try:
            u = fn()
            if len(u) >= 400:
                seen, res = set(), []
                for t in u:
                    if t[0] not in seen:
                        seen.add(t[0])
                        res.append(t)
                print(f"Aktielista: {len(res)} aktier ({label})")
                return res
            print(f"  {label}: för få rader ({len(u)})", file=sys.stderr)
        except Exception as e:
            print(f"  {label} fungerade inte: {e}", file=sys.stderr)
    print(f"VARNING: använder reservlistan med {len(FALLBACK)} aktier", file=sys.stderr)
    return list(FALLBACK)


# ---------- kurskällor ----------

def stooq(ticker, start):
    sym = ticker.lower().replace(".", "-") + ".us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d&d1={start:%Y%m%d}&d2={date.today():%Y%m%d}"
    text = http_get(url)
    if "Date" not in text.split("\n", 1)[0]:
        raise RuntimeError(f"oväntat svar från Stooq för {ticker}: {text[:60]!r}")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            out[row["Date"]] = float(row["Close"])
        except (KeyError, ValueError):
            continue
    return out


def tiingo(ticker, start, key):
    sym = ticker.replace(".", "-")
    url = (f"https://api.tiingo.com/tiingo/daily/{sym}/prices"
           f"?startDate={start:%Y-%m-%d}&token={key}")
    rows = json.loads(http_get(url))
    return {r["date"][:10]: float(r["adjClose"]) for r in rows if r.get("adjClose")}


def yahoo(ticker, start):
    sym = ticker.replace(".", "-")
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    p2 = int(time.time()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
    res = json.loads(http_get(url))["chart"]["result"][0]
    off = res.get("meta", {}).get("gmtoffset", 0) or 0
    ts = res.get("timestamp") or []
    ind = res["indicators"]
    closes = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, closes):
        if c is not None and c > 0:
            out[datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d")] = float(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data.json")
    ap.add_argument("--days", type=int, default=800, help="antal handelsdagar att spara")
    ap.add_argument("--limit", type=int, default=0, help="(test) hämta bara de N första aktierna")
    a = ap.parse_args()

    key = os.environ.get("TIINGO_API_KEY", "").strip()
    start = date.today() - timedelta(days=int(a.days * 1.5) + 10)

    universe = get_universe()
    if a.limit:
        universe = universe[:a.limit]
    min_stocks = max(30, int(0.8 * len(universe))) if not a.limit else 1

    # Källor i prioritetsordning; den första som levererar index-data används för allt.
    providers = []
    if key:
        providers.append(("Tiingo", lambda t: tiingo(t, start, key), 1.5))
    providers.append(("Yahoo", lambda t: yahoo(t, start), 0.3))
    providers.append(("Stooq", lambda t: stooq(t, start), 0.0))

    idx = None
    for source, fetch, pause in providers:
        print(f"Provar källa: {source}")
        try:
            idx = fetch(INDEX_TICKER)
            if len(idx) >= MIN_ROWS:
                break
            print(f"  för lite data från {source} ({len(idx)} rader)", file=sys.stderr)
        except Exception as e:
            print(f"  {source} fungerade inte: {e}", file=sys.stderr)
        idx = None
    if idx is None:
        sys.exit("Ingen datakälla fungerade – avbryter utan att skriva.")
    print(f"Källa: {source}, från {start}")
    cal = sorted(idx)[-a.days:]                      # gemensam handelskalender

    stocks, failed = [], []
    for n, (tk, name, sector) in enumerate(universe, 1):
        try:
            time.sleep(pause)
            px = fetch(tk)
            if len(px) < MIN_ROWS:
                raise RuntimeError(f"bara {len(px)} rader")
            series, last = [], None
            for d in cal:
                last = px.get(d, last)               # fyll hål med föregående kurs
                series.append(last)
            first = next((v for v in series if v is not None), None)
            series = [first if v is None else v for v in series]
            if first is None or any(v <= 0 for v in series):
                raise RuntimeError("ogiltiga kurser")
            stocks.append({"k": tk, "n": name, "s": sector, "p": [round(v, 3) for v in series]})
        except Exception as e:
            failed.append(tk)
            print(f"  FEL {tk}: {e}", file=sys.stderr)
        if n % 50 == 0:
            print(f"  {n}/{len(universe)} klara ({len(stocks)} ok)", flush=True)

    if len(stocks) < min_stocks:
        sys.exit(f"Bara {len(stocks)} aktier hämtades (krav {min_stocks}) – data.json lämnas orörd.")

    idx_series, last = [], None
    for d in cal:
        last = idx.get(d, last)
        idx_series.append(last)

    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": cal[-1],
        "source": source,
        "dates": cal,
        "index": [round(v, 3) for v in idx_series],
        "stocks": stocks,
        "failed": failed,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    size = os.path.getsize(a.out) / 1e6
    print(f"Skrev {a.out}: {len(stocks)} aktier, {len(cal)} dagar, {size:.1f} MB, senaste {cal[-1]}"
          + (f", saknas: {len(failed)} st" if failed else ""))


if __name__ == "__main__":
    main()
