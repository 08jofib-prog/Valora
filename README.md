# Valora Analytics – publicering med riktig data

```
index.html                      sidan (läser data.json, faller tillbaka på demodata om den saknas)
data.json                       skapas automatiskt av jobbet nedan
scripts/fetch_data.py           hämtar dagskurser och skriver data.json
.github/workflows/update-data.yml   kör skriptet varje börsdag efter stängning
```

## Kom igång (ca 15 minuter)

1. **Skapa ett GitHub-konto** (om du saknar ett) och ett nytt repo, t.ex. `valora`. Välj *Public* om du vill använda gratis GitHub Pages.
2. **Ladda upp alla filer** i den här mappen till repot (på github.com: *Add file → Upload files*). Se till att mappen `.github/workflows/` följer med.
3. **Ge jobbet skrivrättighet:** *Settings → Actions → General → Workflow permissions → Read and write permissions → Save*.
4. **Kör datajobbet första gången:** fliken *Actions → Uppdatera kursdata → Run workflow*. Efter någon minut finns `data.json` i repot. Därefter körs det automatiskt mån–fre 22:30 UTC.
5. **Publicera sidan:**
   - **GitHub Pages:** *Settings → Pages → Deploy from a branch → main / (root)*. Du får adressen `https://<användarnamn>.github.io/valora/`.
   - eller **Netlify / Cloudflare Pages:** koppla repot, ingen byggkommando, publiceringsmapp `/`. Sidan uppdateras då automatiskt varje gång `data.json` ändras.
6. **Egen domän (valfritt):** köp domänen och lägg in DNS-posterna som Pages/Netlify/Cloudflare visar. HTTPS ingår.

## Byta datakälla

- Standard är **Stooq** (ingen nyckel). Den kan ändra sina villkor eller blockera automatiska anrop.
- För stabilare, justerade kurser: skapa ett gratis konto på **tiingo.com**, kopiera API-nyckeln och lägg den som secret `TIINGO_API_KEY` (*Settings → Secrets and variables → Actions*). Skriptet använder då Tiingo automatiskt. Gratisnivån har en timgräns, så jobbet tar längre tid (skriptet väntar vid rate limit).
- **Licens:** kontrollera datakällans villkor för att visa kurser för andra användare, särskilt innan du går mot App Store eller tar betalt.

## Köra lokalt

```
python3 scripts/fetch_data.py          # skapar data.json
python3 -m http.server 8000            # öppna http://localhost:8000
```
(Sidan måste öppnas via en webbserver, inte genom att dubbelklicka på filen, annars blockerar webbläsaren `fetch`.)

## Vad händer om något går fel?

- Saknas `data.json` eller är den trasig → sidan visar demodata och märker den som simulerad.
- Hämtas färre än 40 aktier → `data.json` skrivs inte över, så förra dagens data ligger kvar.
- Är datan äldre än 5 dagar visas en varning under rubriken.

## Före lansering

Validera modellen med walk-forward-test på riktig historik innan du marknadsför träffsäkerhet, och kontrollera reglerna kring investeringsråd (Finansinspektionen) om tjänsten ska erbjudas brett eller mot betalning. Friskrivningarna i sidan ska ligga kvar.
