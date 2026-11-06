# ValueRadar — explicația exactă a modelului

**Versiunea formulei operaționale: weighted_opponent_model_v1.** Corecțiile de identitate și import din auditul din 6 noiembrie 2026 modifică intrările, fără a promova altă formulă. Predicțiile deja arhivate rămân neschimbate. Documentul descrie calculul, nu dovedește profitabilitatea.

## 1. Date folosite
- OpenFootball football.json: goluri și rezultate din cele două sezoane precedente (2024/25 și 2025/26 la data acestui audit).
- open-matchday: sezonul curent (2026/27 la data auditului), rezultate/program și, unde există, cartonașe, cornere și faulturi.
- Numai meciuri **anterioare partidei** și din același campionat.
- În modelul actual NU intră: arbitru, formații confirmate, accidentări, presing, informații tactice ori cote locale.

Importul verifică schema, sezonul, numerele întregi nenegative și identitățile.
Nu înlocuiește valori lipsă cu zero. Aliasurile sunt explicite, fără potrivire
aproximativă. Duplicatele compatibile se unesc; evenimentele cu rezultate
conflictuale sunt izolate integral. Rezultatele viitoare nu intră în istoric.
URL-ul, momentul citirii și SHA-256 sunt păstrate în raportul surselor.
Disponibilitatea pe GitHub nu garantează corectitudinea ori disponibilitatea
istorică a informației înaintea fiecărui meci din backtest.

Ora programului folosește convenția **UTC+01:00 fix** declarată în
[dicționarul sursei](https://github.com/oladeeayo/open-matchday/blob/master/DATA_DICTIONARY.md),
nu un fus cu schimbare sezonieră. Se păstrează separat ora UTC, data și ora
României; la trecerea peste miezul nopții se schimbă și data afișată. O oră
necunoscută nu este inventată și nu poate demonstra o ofertă pre-match.

**Eșantion minim:** 35 meciuri în ligă pentru cele mai multe piețe (70 pentru goluri) și 3 meciuri relevante ale fiecărei echipe. Sub 8 meciuri relevante/echipă sau 150 meciuri/liga, încrederea este foarte scăzută. Aceste praguri sunt reguli de protecție inițiale, nu praguri validate științific.

## 2. Ponderarea cronologică
Ponderea unui meci cu d zile vechime: **w = 2^(-d/185)**. Meciurile de acum 185 zile au jumătate din ponderea celor de acum. Media echipei este media ponderată cu aceste valori.

## 3. Regularizarea eșantionului
O medie calculată pe puține meciuri este trasă spre media ligii:

**media_regularizată = (media_echipă × n_efectiv + 7 × media_ligii) / (n_efectiv + 7)**

n_efectiv este suma ponderilor, nu numărul brut de meciuri. Cele 7 pseudo-meciuri reprezintă un parametru de pornire, nu o valoare optimizată deja.

Această sumă reprezintă masa ponderilor folosită de regularizare. Nu este
numărul efectiv Kish și nu justifică singură un interval statistic de încredere.

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

Fiecare piață fără estimare are un motiv și numerele disponibile față de
pragurile cerute. Pentru estimări se arată data celei mai noi observații și
factorii absenți. **Incertitudinea probabilității unui meci nu este încă
cuantificată**: nu fabricăm intervale din numărul de meciuri și nu confundăm
variabilitatea scorurilor cu eroarea probabilității. Calitatea eșantionului
este o regulă de protecție, nu o probabilitate de corectitudine.

Toate valorile provin chiar din funcția Python care calculează probabilitatea. Nu sunt explicații inventate după rezultat.

## 7. Cum îmbunătățim modelul, fără a-l strica
1. Păstrăm actuala versiune ca **baseline** și nu rescriem predicțiile deja salvate.
2. Schimbăm o singură componentă: recență, prior, adversar, arbitru ori distribuție.
3. Comparam Brier, log-loss și calibrarea pe aceleași meciuri nefolosite la dezvoltare, în ordine cronologică.
4. Testăm apoi prospectiv. Verificăm explicit diferența dintre probabilitățile noastre și cotele disponibile în România.
5. Dacă îmbunătățirea este neconcludentă, nu o promovăm în producție.

## 7a. Comparația și calibrarea implementate în audit

`calibration.py` compară Poisson, Elo Davidson, un amestec al celor două și
versiunile ajustate prin temperatură. Frontierele sunt comune celor cinci ligi
și împart zile întregi: 55% pentru începutul antrenării, 15% pentru selecție,
10% pentru calibrare și 20% pentru evaluarea finală, raportate la datele unice,
nu la numărul de meciuri. Antrenarea se extinde cronologic; în evaluare sunt
permise rezultatele zilelor anterioare, fără a reajusta hiperparametrii.

Amestecul folosește `q = α × p_Poisson + (1−α) × p_Elo`. Calibrarea folosește
`q_k = p_k^(1/T) / Σ_j p_j^(1/T)`. Candidatul Elo și α sunt alese numai pe
validare; T numai pe fereastra ulterioară de calibrare. Temperatura 1 păstrează
distribuția; valori peste 1 o apropie de uniformă. Grilele și regulile sunt în
[RESEARCH_PROTOCOL.md](RESEARCH_PROTOCOL.md).

Raportul include log-loss, Brier mediat pe cele trei clase, ECE pe clase în
cinci grupe și rezultate pe fiecare ligă, pe aceleași partide. Intervalele
pentru scoruri și diferențe folosesc bootstrap pereche pe săptămâni ISO,
cu seed fix. Intervalele Wilson ale frecvențelor din grupe sunt descriptive
și presupun independență; niciunul nu este intervalul probabilității unui
meci viitor. Dependențele persistente dintre echipe rămân o limitare.

Istoricul a fost consultat anterior. Acesta este un nou audit exploratoriu,
nu un holdout prospectiv neatins. Niciun model calibrat nu este promovat
automat. Reperul cotelor fără marjă rămâne indisponibil când nu există cote
istorice complete și aliniate înaintea startului; apropierea de un snapshot
actual nu ține locul evaluării pe rezultate.

## 7b. Jurnalul și barierele cotelor

Decontarea `observed_results_v1` verifică și concordanța orei arhivate cu ora
rezultatului, plus perioada minimă de două ore după cel mai târziu start
cunoscut. Se păstrează o dovadă a valorilor observate și a surselor. Acestea
nu verifică regulile de decontare ale unui operator. Un rezultat corectat
ulterior intră în carantină pentru scoruri; predicția și decontarea originală
nu sunt rescrise. Lipsa temporară a sursei nu șterge o dovadă arhivată validă.
Raportul distinge rezultatele lipsă de statisticile lipsă și de conflicte.

Jurnalul păstrează prima predicție, ora creării și, pentru înregistrările noi,
startul UTC și versiunea metodei. Nu se trunchiază automat și nu se resetează
la o eroare de citire. Înregistrările vechi fără dovadă de publicare înaintea
startului rămân arhivate și sunt excluse din evaluarea prospectivă.

Scannerul potrivește exact identitățile canonice, competiția și ora de start.
Distribuțiile complete ale aceleiași case se păstrează în același snapshot;
nu se combină cote din momente diferite. Refresh-ul diagnosticului nu
actualizează timestamp-ul cotei. Erorile, lipsa datelor, bugetul necunoscut
sau prospețimea insuficientă închid comparația curentă.

Nu există încă o implementare de verificare independentă a unui feed RO
și a unui avantaj prospectiv după incertitudine. Prin urmare toate
recomandările value și calculul ROI din observații sunt blocate, inclusiv
când un JSON declară booleeni de tip „verificat”. Lista publică este goală.
Vezi [PROVIDER_COVERAGE.md](PROVIDER_COVERAGE.md).

## 7c. Protecția operațională a prospețimii

Ora rulării nu este data ultimei partide din istoric. Pentru analizele curente,
se verifică separat sursa rezultatelor din sezonul curent și vechimea
statisticilor fiecărei ligi/piețe. O sursă curentă lipsă sau un istoric mai
vechi de 21 de zile blochează afișarea probabilităților curente și comparația
cu cote. Datele lipsă nu sunt înlocuite cu rezultate fictive, nici vara.
Pragul de 21 de zile este o regulă conservatoare de funcționare, nu un prag
optimizat pe rezultate. Formula istorică și scorurile de cercetare nu se schimbă.

Importul de producție și rapoartele recalculate folosesc aceeași fotografie
capturată, iar publicarea verifică atât JSON-ul, cât și HTML-ul/scripturile
servite. Dublurile canonice din jurnal opresc salvarea înaintea oricărei
modificări. Vezi [OPERATIONS.md](OPERATIONS.md).

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
