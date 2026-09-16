import requests
from bs4 import BeautifulSoup
from datetime import date

API_URL = "https://www.centralbank.ae/umbraco/Surface/Exchange/GetExchangeRateAllCurrencyDate"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://www.centralbank.ae/en/forex-eibor/exchange-rates/",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
}

target = date(2026, 4, 13)
date_str = target.strftime("%Y-%m-%d")

session = requests.Session()
session.headers.update(headers)
session.get("https://centralbank.ae/en/forex-eibor/exchange-rates/", timeout=30)

resp = session.post(f"{API_URL}?dateTime={date_str}", timeout=30)

soup = BeautifulSoup(resp.text, "html.parser")

for tr in soup.find_all("tr"):
    cells = tr.find_all("td")
    if len(cells) >= 3:
        currency = cells[1].get_text(strip=True)
        rate_text = cells[2].get_text(strip=True)
        if "Euro" in currency:
            print(f"{target} | EUR = {rate_text} AED")
