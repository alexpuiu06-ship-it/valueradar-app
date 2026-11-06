# ValueRadar — motor statistic experimental

Dashboard automat pentru Premier League, La Liga, Serie A, Bundesliga și Ligue 1.

**Atenție:** probabilitățile nu au fost validate ca profitabile. Nu există încă scanner de cote la cele șase case românești și nu se plasează pariuri.

## Cum îl activezi
1. GitHub → repository → **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Actions → ValueRadar / actualizare date → Run workflow** (dacă nu pornește la publicarea codului).
3. Accesează linkul publicat în **Settings → Pages** după o execuție reușită.

Actualizare la aproximativ patru ore, în limita disponibilității GitHub Actions și a surselor.

## Surse
- [OpenFootball football.json](https://github.com/openfootball/football.json): date public domain CC0 (rezultate/program), pot întârzia.
- [open-matchday](https://github.com/oladeeayo/open-matchday): date gratuite pentru uz necomercial, pot fi incomplete sau întârziate; drepturile furnizorilor originali se aplică.

Modelul experimental nu afișează probabilități dacă nu are suficiente observații. Codul este public; nu publica parole, chei API ori date private.
