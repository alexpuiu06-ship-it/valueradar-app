# ValueRadar — activare cote reale (fără programare)

## Situația actuală
- Dashboardul, importul de date, predicția 1X2, validarea cronologică și jurnalul prospectiv sunt instalate.
- Motorul de cote The Odds API v4 este instalat și testat pe răspunsuri de test controlate.
- Pentru **cote reale automate**, utilizatorul trebuie să obțină propria cheie API și să o introducă în **GitHub Actions Secrets**.
- **Important:** The Odds API nu confirmă acoperirea celor șase versiuni românești. Prima integrare monitorizează regiunea **UK**, pre-match 1X2, doar ca validare tehnică și cercetare. Nu include neapărat piața România.

## Activare simplă (o singură dată)

1. Intră la https://the-odds-api.com/ și creează un cont cu planul gratuit.
2. Copiază cheia API din contul tău. **Nu o publica în GitHub și nu o trimite în chat.**
3. Deschide https://github.com/alexpuiu06-ship-it/valueradar-app/settings/secrets/actions/new
4. La **Name** scrie exact `ODDS_API_KEY`.
5. La **Secret** inserează cheia. Apasă **Add secret**.
6. Intră la https://github.com/alexpuiu06-ship-it/valueradar-app/actions/workflows/valueradar.yml
7. Apasă **Run workflow** (pe branch-ul `main`). **Nu repeta apăsarea des:** consumă credite API la fiecare rulare care accesează cotele.
8. Deschide dashboardul: https://alexpuiu06-ship-it.github.io/valueradar-app/

După activare, scannerul este configurat să verifice automat **de două ori pe zi** (08:13 și 16:13 UTC, cu posibile întârzieri GitHub Actions). Modelul statistic de bază continuă să se actualizeze aproximativ la patru ore.

## Buget și protecția datelor
- Scannerul interoghează cel mult 5 ligi, piața `h2h`, o singură regiune.
- Cost estimat pentru lună de 30 zile: până la 300 credite (5 ligi × 2 scanări × 30 zile).
- Protecție internă: plafon de 400 credite lunar și rezervă pentru a evita epuizarea cheii.
- Creditul real consumat depinde de răspunsurile API-ului; vezi `docs/odds_budget.json`.
- Cheia se citește **numai** dintr-un GitHub Secret. Nu este copiată niciodată în paginile publice.
- Se păstrează mostre istorice de **comparații derivate**, nu un flux revândut de cote.

## Cum interpretezi rezultatul
- `odds_status.json`: statusul conectării, ultima scanare, cota de credite, numărul de meciuri potrivite.
- `odds_watchlist.json`: diferențe matematice pozitive de preț, **nu** pariuri value validate.
- `odds_observations.json`: istoric limitat de comparații, pentru evaluări ulterioare.
- Dacă nu sunt meciuri potrivite ori quote-urile sunt învechite, scannerul nu afișează recomandări inventate.

## Cum verifici o cotă Superbet/Betano etc. chiar acum
În ValueRadar, secțiunea **Compară manual o cotă** îți permite să alegi meciul, casa, 1/X/2 și prețul. Sistemul calculează pragul matematic și EV orientativ pe baza probabilității modelului. Nu validează oferta automat.

## Limitări care trebuie rezolvate înainte de o decizie cu bani reali
1. Verificarea exactă a cotelor pentru Superbet RO, Betano RO, Unibet RO, MrBit RO, NetBet RO și Casa Pariurilor, printr-un furnizor permis.
2. Compatibilitatea regulilor de decontare, fusului orar și a piețelor.
3. Istoric amplu și calibrare stabilă pentru cartonașe, cornere, faulturi și 1X2.
4. Backtesting pe cote reale, evaluare prospectivă și măsurarea closing-line value.
5. Excluderea automată a selecțiilor cu incertitudine mare.
6. Respectarea condițiilor legale locale și a regulilor operatorilor. 18+.

Codul **nu** plasează pariuri automat și **nu** promite profit.
