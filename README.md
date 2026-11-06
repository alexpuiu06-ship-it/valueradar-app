# ValueRadar — analiză fotbalistică experimentală

Dashboard automat pentru Premier League, La Liga, Serie A, Bundesliga și Ligue 1.

**Nu există pariuri value verificate.** Probabilitățile nu au fost validate ca profitabile. Cotele internaționale sunt observații de diagnostic; feedurile exacte ale celor șase operatori RO nu sunt confirmate. Aplicația nu plasează pariuri.

Dashboardul explică datele, formulele, eșantioanele și incertitudinea fiecărei
analize. Datele expirate sau imposibil de încărcat blochează comparațiile
curente. Jurnalul păstrează predicțiile originale; versiunile noi ale
pipeline-ului se arhivează separat. Laboratorul compară Poisson, Elo și
calibrarea, fără promovare automată în producție.

- [Metodologia și formulele](ANALYSIS_METHODOLOGY.md)
- [Protocolul comparației și limitele evaluării](RESEARCH_PROTOCOL.md)
- [Acoperirea reală a operatorilor RO](PROVIDER_COVERAGE.md)
- [Raportul auditului și verificările](AUDIT_REPORT.md)
- [Funcționarea și publicarea](OPERATIONS.md)

## Cum îl activezi
1. GitHub → repository → **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Actions → ValueRadar / actualizare date → Run workflow**, pe `main` (dacă nu pornește la publicarea codului). Opțiunea de scanare a cotelor este implicit dezactivată; activarea ei consumă credite API.
3. Accesează linkul publicat în **Settings → Pages** după o execuție reușită.

Actualizare la aproximativ patru ore, în limita disponibilității GitHub Actions și a surselor.

Workflow-ul de teste rulează și pe branch-uri/PR-uri, cu import real, teste
Python și browser, fără cheia de cote și fără publicare. Un singur workflow
de producție salvează și publică toate rapoartele împreună; refuză să
suprascrie un main modificat între timp. Rulările separate de cercetare
produc doar artefacte, fără să modifice repository-ul sau site-ul.

## Verificare locală

Necesită Python 3.12 și Node.js 22. Codul Python de producție folosește numai
biblioteca standard. Pentru browser, dependența Playwright este fixată în lockfile.

```bash
python scripts/check_syntax.py
python -m unittest discover -s tests -v
bash scripts/lint_workflows.sh
npm ci
npx playwright install --with-deps chromium
npm test
```

Importul de mai jos citește sursele publice reale, fără API-ul de cote:

```bash
python runner.py
python performance.py
python calibration.py
python model_lab.py
python elo_challenger.py
python scripts/validate_outputs.py
python -m http.server 8765 --bind 127.0.0.1 --directory docs
```

Comenzile actualizează JSON-urile locale din `docs/`; folosiți un checkout
separat pentru cercetare. Un jurnal ilizibil oprește importul, în loc să fie
înlocuit. Nu publicați `.env`, chei API sau dumpuri ale mediului.

Pentru repetarea cercetării fără rețea se poate folosi
`python calibration.py --snapshot work/intrari.json`. Fișierul trebuie să
conțină `history` și, opțional, `as_of`, `observations`, `forecasts`; datele
trebuie să provină dintr-un import real păstrat anterior. Verificați amprenta
din raport când comparați două rulări.

## Surse
- [OpenFootball football.json](https://github.com/openfootball/football.json): date public domain CC0 (rezultate/program), pot întârzia.
- [open-matchday](https://github.com/oladeeayo/open-matchday): date gratuite pentru uz necomercial, pot fi incomplete sau întârziate; drepturile furnizorilor originali se aplică.

Modelul experimental nu afișează probabilități dacă nu are suficiente observații. Codul este public; nu publica parole, chei API ori date private.
