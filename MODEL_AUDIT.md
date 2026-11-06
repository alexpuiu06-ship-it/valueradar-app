# ValueRadar — Auditul modelului (6 noiembrie 2026)

**Status: experimental, fără dovezi de avantaj profitabil.** Fără cote live și fără model de arbitri sau de formații confirmate.

## Date observate în prima execuție
- 3.935 meciuri istorice pentru goluri și rezultate, în cele cinci ligi.
- 452 meciuri cu cartonașe / cornere / faulturi (90 PL, 109 La Liga, 100 Serie A, 72 Bundesliga, 81 Ligue 1).
- Pentru unele meciuri, media contextuală are doar 3–5 meciuri pe echipă pentru partea acasă/deplasare.
- Sursele gratuite folosite în acest proiect pot fi întârziate sau incomplete; drepturile furnizorilor originali se aplică.

## Testare cronologică — out-of-sample, preliminară

| Piață | N predicții | Brier model | Brier referință | Îmbunătățire | Interval aproximativ 95% pentru diferență |
|---|---:|---:|---:|---:|---|
| Galbene, peste 4,5 | 109 | 0,22529 | 0,23691 | +0,01162 | −0,00219 ... +0,02543 |
| Cornere, peste 9,5 | 109 | 0,24372 | 0,24667 | +0,00295 | −0,00661 ... +0,01251 |
| Goluri, peste 2,5 | 803 | 0,24232 | 0,24524 | +0,00292 | −0,00226 ... +0,00810 |
| Faulturi, peste 23,5 | 109 | 0,22534 | 0,23139 | +0,00605 | −0,00765 ... +0,01976 |

Intervalele sunt aproximări normale pe diferențe de scor pentru observațiile din test, nu intervale perfect robuste pentru dependențele dintre meciuri. **Fiecare interval include zero**: dovezi insuficiente pentru superioritate statistică stabilă. Nu există măsurători comparative cu cotele oferite de bookmakeri.

## Ce a fost corectat
- Calcularea orei locale România din convenția UTC+01:00 a feedului de program.
- Excluderea meciurilor deja începute, inclusiv în ziua curentă.
- Validare suplimentară: scor logaritmic, comparație cu modelul de referință, interval aproximativ al diferenței și calibrare în grupe.
- Etichete de încredere foarte scăzută pentru eșantioane mici.
- Afișarea ultimei date a statisticilor, separat de ora executării fluxului.

## Ce lipsește pentru următoarea etapă
1. Mai multe sezoane cu statistici fiabile pentru galbene și cornere, cu drepturi de reutilizare clare.
2. Controlul calității și al identității echipelor între sezoane.
3. Arbitri, formații, accidentări și stil tactic: testate prin ablație și numai când datele există.
4. Baza de cote pre-match pentru fiecare operator și piață, cu timestamp și aceleași reguli de decontare.
5. Backtesting de cotă și test prospectiv pentru EV / closing line value. **Nicio combinație nu este recomandată înainte de acestea.**

Criteriul de promovare al modelului nu este „bife verzi în GitHub”, ci calibrare stabilă și valoare pozitivă demonstrată pe date noi, după costuri și incertitudine.
