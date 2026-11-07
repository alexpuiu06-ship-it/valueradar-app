> Arhivă de context anterioară închiderii; referințele relative sunt ajustate pentru acest director. Starea curentă este în [CODEX_HANDOFF.md](../CODEX_HANDOFF.md).

# ValueRadar — context de predare către Codex (6 noiembrie 2026)

**Continuare implementată:** consultați [AUDIT_REPORT.md](../AUDIT_REPORT.md),
[RESEARCH_PROTOCOL.md](../RESEARCH_PROTOCOL.md) și metodologia actualizată.
Secțiunile de mai jos păstrează starea inițială a predării. Pipeline-ul nou
`validated_identity_v2` corectează identități/date și arhivează predicții
separate de cele vechi; nu promovează automat Elo sau un model calibrat.

Pentru continuarea operațională citiți și [OPERATIONS.md](../OPERATIONS.md).
Continuarea din 7 noiembrie adaugă istoricul agregat RO pe 90 de zile și un
raport de decontare cu dovezi, conflicte și întârzieri. Nu se completează
zile fictive și nu se rescriu predicțiile ori decontările arhivate. Noua
eligibilitate este aplicată și scorurilor prospective/reperului de piață.
Sursele curente verificate au rezultate numai până la 1–2 noiembrie; rezultate
mai noi nu trebuie inventate pentru a produce decontări. Vezi raportul
operațional și cozile de așteptare din aplicație.
**Decizia curentă a proprietarului: rămânem momentan cu monitorizarea gratuită.**
Evaluarea comercială și solicitarea de demo sunt amânate; nu contactați
furnizorul și nu activați un abonament plătit pe baza plafonului discutat anterior.
PropLine continuă monitorizarea zilnică. Cotele OddsPapi rămân o probă manuală;
scorurile finale pot fi verificate săptămânal, maximum 12 cereri din planul
gratuit per rulare, numai pentru evaluarea predicțiilor arhivate. Observațiile
validate sunt separate de antrenare/calibrare retrospectivă, iar conflictele
rămân în carantină. Tema comercială se reia numai dacă proprietarul o redeschide.
Evaluarea reală a surselor RO și limitele observate sunt în
[PROVIDER_ALTERNATIVES.md](../PROVIDER_ALTERNATIVES.md). PROPLINE_API_KEY este
configurată; probele autentificate au acoperire parțială. Monitorul agregat
nu reprezintă integrare de prețuri RO confirmate și nu deblochează value.
ODDSPAPI_API_KEY este și ea configurată și testată. Proba gratuită, consumul
și limitele sunt în [ODDSPAPI_EVALUATION.md](../ODDSPAPI_EVALUATION.md).
Primul PR a fost integrat și publicat; corecțiile suplimentare unifică
producția într-un singur writer și blochează istoricul vechi sau ambiguu.

## Scopul proprietarului
Utilizatorul nu programează. Dorește un **produs practic, sigur și ușor de folosit** pentru cele cinci ligi majore europene, care să compare estimări pentru 1X2, goluri, galbene, cornere și faulturi cu cote de la operatorii **Superbet, Betano, Unibet, MrBit, NetBet și Casa Pariurilor**. Scopul este detectarea de value betting **numai când există dovezi reale**, nu estimări prezentate înșelător ca avantaje de profit. Nu promite rezultate perfecte, probabilități exacte sau profit.

**Continuă implementarea, nu doar planificarea.** Rezolvă întâi bug-urile P0, rulează teste relevante, documentează ce ai schimbat și cere intervenția utilizatorului doar pentru decizii importante, costuri, chei sau autorizații. Nu plasa pariuri.

## Repository și site
- Repository: https://github.com/alexpuiu06-ship-it/valueradar-app
- Branch: `main`; repo public.
- Site: https://alexpuiu06-ship-it.github.io/valueradar-app/
- Codex să citească **fișierele reale din repository**, nu să se bazeze doar pe acest document; istoria conversației ChatGPT nu este importată automat în Codex.
- Cheia `ODDS_API_KEY` este configurată ca GitHub Actions Secret. **Nu o citi, copia, tipări sau introduce în client/public repo.**

## Starea reală verificată
- `runner.py`: import automat din OpenFootball și open-matchday; model explicabil cu medii ponderate, recență cu timp de înjumătățire 185 zile, shrinkage de 7 pseudo-meciuri, efect adversar, Poisson/binomială negativă, 1X2 Poisson independent.
- `docs/latest.json`: circa 200 meciuri viitoare la ultima verificare, cu `explanation` per piață și metodă. Datele pot deveni vechi; folosește timestamp-uri.
- `odds_scanner.py`: The Odds API v4 (regiune UK, piața h2h), colectare reală 1X2, deduplicare/potrivire nume, limită de consum și diagnostic față de mediana pieței. Prima scanare reală: 96 evenimente, 62 potriviri, 2.394 cote comparate și 495/500 credite rămase atunci. **Nu este feed confirmat pentru cele șase operatori români**. Nu presupune că Unibet UK înseamnă Unibet RO.
- `docs/odds_diagnostics.json`: 59 meciuri cu consens, 32 cu diferență model–piață >=10 puncte procentuale la ultima scanare. Semnalele value/EV excesive sunt blocate; `docs/odds_watchlist.json` nu trebuie să afișeze selecții neverificate.
- `performance.py`: audit paper-only, cu prag de verificare strict înainte de semnale de profit. `docs/forecast_log.json`: estimări înghețate prospectiv, ulterior decontate.
- `model_lab.py` și `docs/model_lab.json`: compară recență 185/90 zile, pseudo-meciuri 7/15 și cu/fără adversar, pe partiții cronologice. Varianta fără adversar a avut un log-loss puțin mai bun pentru 1X2, dar nu a fost promovată.
- `elo_challenger.py` și `docs/elo_challenger.json`: candidat Elo dinamic testat cronologic. La ultima rulare: 685 de partide holdout; câștig mediu log-loss față de Poisson ~0,01711, interval aproximativ 95% [-0,00276, 0,03699], deci nu este concludent. Pe 59 de meciuri cu consens, medie a celei mai mari abateri: Poisson ~12,5 pp vs Elo ~7,1 pp; 32 vs 19 cu abatere >=10 pp. **Apropierea de piață NU demonstrează superioritate reală sau profit**.
- `docs/index.html`, `docs/odds_ui.js`, `docs/model_lab_ui.js`, `docs/elo_ui.js`: dashboard, explicația „Cum a calculat?”, comparație cote manuală, laborator și comparație Elo. Verifică în browser încărcarea reală și starea publicării.
- `ANALYSIS_METHODOLOGY.md`, `MODEL_AUDIT.md`, `ACTIVARE_FARA_PROGRAMARE.md`: documentația deja existentă.
- GitHub Actions: `.github/workflows/valueradar.yml` importă și publică; `check.yml` face teste; `model_lab.yml` și `elo.yml` fac research separat. Repo a avut conflicte de push și blocaje Pages; s-au introdus retry-uri, cancel deployment și recuperare prin `pages_recover.yml`. **Evită multe commit-uri individuale în succesiune**: declanșează/cancel-ează joburi și poate bloca Pages. Preferă branch, lot de modificări, o singură PR/merge după teste.

## Probleme prioritare (ordine strictă)
1. **P0 — Validarea sistemului end-to-end.** Reproduce local tests, parse JS și Python, inspectează ieșirile JSON, rulează browser smoke/E2E pentru panouri și date; verifică și fluxul GitHub Pages cu ultima versiune. Testează timeout/fail-closed, conexiune lipsă și date vechi, fără consum inutil de credite API.
2. **P0 — Corectitudinea bazei de date.** Verifică că datele/ora, convenția fusului orar UTC+01:00 din sursa programului, identitatea echipelor și anotimpurile competiționale sunt corecte. Verifică dacă setul de holdout nu conține același meci, date viitoare sau scurgeri de informații. Unele serii istorice conțin doar goluri.
3. **P0 — Semnale neînșelătoare.** Cotele externe pot fi afișate doar ca observații. Nu marca profit/value real fără: preț exact verificat la operator RO, timestamp proaspăt, aceeași piață/linie/regulă de decontare, model calibrat și rezultate prospective. Nu produce pariuri automat.
4. **P1 — Cercetare reproductibilă a modelului.** Compară modelul actual vs Elo, baseline piață no-vig, variantă ensemble calibrată; folosește rolling/expanding-origin, holdout cronologic, log-loss/Brier/calibrare, și analiză pe ligi. Preînregistrează deciziile și evită tuning pe holdout.
5. **P1 — Piața locală.** Verifică legitim acoperirea unui furnizor pentru Superbet RO, Betano RO, Unibet RO, MrBit RO, NetBet RO, Casa Pariurilor, pe piețele țintă. Nu presupune acces automat doar pentru că site-ul lor este public; respectă termeni, licențe și costurile. Cere acordul utilizatorului înainte de plan plătit.
6. **P2 — Extinde calitatea datelor pentru galbene/cornere/faulturi, arbitri doar dacă există surse/licențe adecvate.** Testează contribuția ca ablație, nu adăuga factori fictivi.
7. **P2 — Observabilitate și UX.** Arată prospețimea datelor, eșantionul real, sursele, eroarea probabilităților și motivul exact pentru care un meci a fost respins. Monitorizează pipeline-ul, nu raporta „verde” când deploy-ul a eșuat.

## Criterii de acceptare
- Teste unitare și E2E trecute fără a expune secretul API.
- Import real și parsare robustă fără înlocuiri inventate.
- Valori 1X2 normalizate la 1, condiții de validare demonstrate și calcule reproductibile.
- Raport clar de comparație și calibrare, defalcat pe ligi, cu număr efectiv de meciuri și intervale de incertitudine.
- Prin default, valoare/ROI **nevalidate** → dashboard afișează „Nu există pariuri value verificate”.
- Actualizare GitHub Actions fără concurență blocantă; deployment verificat.
- Documentație simplă în limba română pentru utilizator și rezumat la final: ce s-a schimbat, ce s-a testat, ce încă nu știm și ce decizie, dacă există, trebuie luată de utilizator.

## Important: ce NU trebuie să faci
- Nu transforma câteva diferențe mari de la bookmaker în „oportunități cu profit”.
- Nu alege varianta Elo doar pentru că seamănă mai mult cu piața într-un singur snapshot.
- Nu pretinde că predictibilitatea sportului poate deveni perfectă.
- Nu integra scraping neautorizat sau servicii cu plată fără acord.
- Nu înlocui outputurile cronologice / jurnalul prospectiv cu predicții refăcute după rezultate.
