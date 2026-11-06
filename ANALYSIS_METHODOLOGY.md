# ValueRadar — explicația exactă a modelului

**Versiunea metodei: weighted_opponent_model_v1.** Documentul descrie formula existentă, nu dovedește că estimările sunt corecte ori profitabile.

## 1. Date folosite
- OpenFootball football.json: rezultate istorice, goluri, sezoanele 2024/25 și 2025/26.
- open-matchday: sezonul 2026/27, rezultate/program și, unde există, cartonașe, cornere și faulturi.
- Numai meciuri **anterioare partidei** și din același campionat.
- În modelul actual NU intră: arbitru, formații confirmate, accidentări, presing, informații tactice ori cote locale.

**Eșantion minim:** 35 meciuri în ligă pentru cele mai multe piețe (70 pentru goluri) și 3 meciuri relevante ale fiecărei echipe. Sub 8 meciuri relevante/echipă sau 150 meciuri/liga, încrederea este foarte scăzută. Aceste praguri sunt reguli de protecție inițiale, nu praguri validate științific.

## 2. Ponderarea cronologică
Ponderea unui meci cu d zile vechime: **w = 2^(-d/185)**. Meciurile de acum 185 zile au jumătate din ponderea celor de acum. Media echipei este media ponderată cu aceste valori.

## 3. Regularizarea eșantionului
O medie calculată pe puține meciuri este trasă spre media ligii:

**media_regularizată = (media_echipă × n_efectiv + 7 × media_ligii) / (n_efectiv + 7)**

n_efectiv este suma ponderilor, nu numărul brut de meciuri. Cele 7 pseudo-meciuri reprezintă un parametru de pornire, nu o valoare optimizată deja.

## 4. Potrivirea dintre adversari
Estimăm separat:
- Statistica produsă de gazde acasă.
- Statistica permisă adversarului de echipa care acum este oaspete.
- Statistica produsă de oaspeți în deplasare.
- Statistica permisă adversarului de echipa care acum este gazdă.

**lambda_gazde = sqrt(producție_gazde_regularizată × permis_de_oaspeți_regularizat)**

**lambda_oaspeți = sqrt(producție_oaspeți_regularizată × permis_de_gazde_regularizat)**

Valorile sunt limitate la intervalul 0,05 până la 2,4 × media ligii pentru gazde, respectiv oaspeți.

**Total estimat = lambda_gazde + lambda_oaspeți.**

Sunt relații de calcul, nu explicații cauzale dovedite.

## 5. Transformarea în probabilități
- Pentru totaluri (goluri, galbene, cornere, faulturi): distribuție Poisson sau binomială negativă, în funcție de dispersia din ligă.
- Pentru 1X2: două distribuții Poisson **independente** pentru golurile gazdelor și oaspeților, apoi însumarea combinațiilor pentru 1, X și 2.
- Independenta golurilor este o simplificare și poate fi greșită în anumite partide.
- Probabilitățile nu sunt calibrate pe cotele reale ale operatorilor din România.

## 6. Ce prezintă dashboardul
Sub fiecare meci se poate deschide **Cum a calculat ValueRadar?**:
- media ligii și cele patru componente brute;
- eșantioanele efective și regularizarea;
- estimările gazde/oaspeți, totalul, diferența față de medie;
- distribuția folosită, dispersia și limitările;
- data-limită a informațiilor și familiile de surse.

Toate valorile provin chiar din funcția Python care calculează probabilitatea. Nu sunt explicații inventate după rezultat.

## 7. Cum îmbunătățim modelul, fără a-l strica
1. Păstrăm actuala versiune ca **baseline** și nu rescriem predicțiile deja salvate.
2. Schimbăm o singură componentă: recență, prior, adversar, arbitru ori distribuție.
3. Comparam Brier, log-loss și calibrarea pe aceleași meciuri nefolosite la dezvoltare, în ordine cronologică.
4. Testăm apoi prospectiv. Verificăm explicit diferența dintre probabilitățile noastre și cotele disponibile în România.
5. Dacă îmbunătățirea este neconcludentă, nu o promovăm în producție.

## 8. Registrul problemelor

| Prioritate | Problemă | Criteriu de rezolvare |
|---|---|---|
| P0 | Modelul poate indica avantaje neverosimile | Carantină automată, nu recomandări |
| P0 | Conflicte la salvarea în GitHub | GitHub Actions finalizat cu succes |
| P1 | Puține partide cu galbene/cornere/faulturi | Mai multe date cu drepturi clare și test cronologic |
| P1 | Arbitri și tactică lipsesc | Test de ablație: aport demonstrat pe date noi |
| P1 | Lipsesc cotele exacte ale caselor RO | Verificarea aceleiași piețe, linii și reguli |
| P2 | Recență 185 zile și prior 7 meciuri sunt alegeri fixe | Comparare cu variante pe holdout |
| P2 | Model 1X2 independent Poisson | Comparare cu modele Dixon–Coles și piața |

## Cod și date
- runner.py — formule, import, analiza explicabilă și validare.
- odds_scanner.py — cote internaționale reale și diagnostic no-vig.
- performance.py — jurnal de evaluare prospectivă.
- docs/latest.json — fiecare estimare cu traseul calculului.
- docs/odds_diagnostics.json — diferențele între model și piață.
- docs/forecast_log.json — prima predicție salvată pentru verificare ulterioară.

**Nu există încă un avantaj profitabil demonstrat. Nu etichetăm nicio selecție drept value confirmat până la validare.**
