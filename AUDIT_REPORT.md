# Audit ValueRadar — 6 noiembrie 2026

**Rezultat:** aplicația păstrează statutul experimental. Nu există pariuri
value verificate și nu se calculează ROI din diferențe nevalidate. Lucrul
este pregătit pe `codex/robust-analysis-audit`, pentru verificare înaintea
oricărei integrări în `main`.

## Date și corecții

Au fost citite integral documentele de predare/metodologie, toate cele cinci
module Python, interfața și cele cinci workflow-uri inițiale.

Importul real a reușit pentru **20/20 surse**, cu **3.935 rezultate** din cele
cinci ligi, din 15 august 2024 până la 2 noiembrie 2026. Programul conține
1.300 meciuri viitoare; snapshotul analizează **200 meciuri în următoarele
30 de zile**, cu 800 estimări de total și distribuțiile 1X2 asociate golurilor.
Nu s-au făcut cereri suplimentare la API-ul cotelor și nu s-au consumat credite.

Sursele reale au fost descărcate o dată și salvate separat în spațiul de lucru,
cu URL, moment și SHA-256. Rapoartele locale folosesc aceste intrări înghețate;
importul din CI verifică separat rețeaua reală. În `latest.json` sunt păstrate
amprentele surselor. Amprenta istoricului eligibil pentru noua cercetare este
`748e17d279274cbd07e42d3a3a316fc971297323ca0ce95b7962a764c809f80d`.
Hash-ul identifică intrarea, fără a garanta păstrarea ei în upstream.

Corecțiile principale:

- Identități explicite între OpenFootball și open-matchday: de exemplu
  `AC Milan`/`Milan`, `FC Internazionale Milano`/`Internazionale`, Brighton,
  Lille, Lens și Rennes. Potrivirea aproximativă a cotelor a fost eliminată.
- Import determinist, schemă/sezon/numere verificate, conflicte izolate,
  rezultate viitoare excluse, program UTC și dată locală România distincte.
- Probabilități normalizate și funcții numerice care refuză NaN, infinit și
  rate negative; tratare stabilă a mediilor mari.
- Explicații din intermediarii reali: formule, surse, intervalul datelor,
  medii brute/regularizate, eșantioane, factori lipsă și motivul respingerii.
  Incertitudinea unui meci este declarată necuantificată, fără intervale fictive.
- Jurnal atomic, fără resetare/trunchiere la erori. Cele **1.000 de predicții
  originale** sunt păstrate integral; **1.000 de predicții noi**, separate prin
  `validated_identity_v2`, sunt arhivate înaintea startului. Evaluarea poate
  fi defalcată pe versiune; agregarea versiunilor este doar descriptivă.

## Comparația modelelor

Protocolul este în [RESEARCH_PROTOCOL.md](RESEARCH_PROTOCOL.md). Partițiile
sunt comune ligilor, pe zile întregi, cu începutul validării la **31 octombrie
2025**, calibrării la **3 februarie 2026** și evaluării finale la **12 aprilie
2026**. Modelele folosesc numai rezultate din zile anterioare fiecărei partide.
Suport comun: **605 partide de validare, 400 de calibrare și 693 de evaluare**.
Fereastra finală conține 756 partide eligibile în istoric; 63 nu au estimări
Poisson comparabile din cauza pragurilor de eșantion. Scorurile pe suportul
comun nu descriu performanța pe meciurile fără estimare.

Selecția numai pe validare a ales `elo_fast`; greutatea Poisson a amestecului
este 0, deci amestecul ales coincide cu Elo. Temperatura aleasă ulterior pe
calibrare este 0,7 pentru Poisson și 1,15 pentru Elo/amestec.

| Model | Log-loss | Brier mediat pe 3 clase | ECE pe clase |
|---|---:|---:|---:|
| Poisson operațional, date corectate | 1,026404 | 0,205137 | 0,039407 |
| Elo selectat pe validare | 1,000988 | 0,198642 | 0,018842 |
| Poisson cu temperatură | 1,018566 | 0,203097 | 0,038687 |
| Elo cu temperatură | 1,002184 | 0,199081 | 0,022990 |
| Frecvențe istorice ale ligii | 1,081505 | 0,218405 | 0,037248 |

Scorurile mai mici sunt mai bune. Câștigul log-loss Elo față de Poisson este
0,025416, cu interval aproximativ 95% **[−0,003717; 0,053414]** prin bootstrap
pereche pe 18 săptămâni ISO, 800 resampling-uri cu seed fix. Pentru Poisson
calibrat, câștigul este 0,007838, interval **[−0,001312; 0,017972]**.
Ambele includ zero: nu există o concluzie stabilă de superioritate.
Calibrarea Elo a fost puțin mai slabă decât Elo brut pe evaluarea finală;
rezultatul nu a fost folosit pentru reajustarea temperaturii.

| Ligă | N evaluare | Log-loss Poisson | Log-loss Elo | Interval câștig Elo |
|---|---:|---:|---:|---|
| Premier League | 145 | 1,056441 | 1,026077 | [0,002015; 0,057271] |
| La Liga | 167 | 1,009953 | 0,983775 | [−0,014630; 0,067836] |
| Serie A | 159 | 1,010851 | 0,960384 | [−0,017566; 0,099072] |
| Bundesliga | 103 | 1,015649 | 1,019584 | [−0,048097; 0,042187] |
| Ligue 1 | 119 | 1,042982 | 1,032730 | [−0,043175; 0,064619] |

Rezultatele pe ligi sunt exploratorii și nu corectează comparațiile multiple.
Istoricul a fost deja consultat în cercetările anterioare; acest audit nu
creează un holdout prospectiv nou. Intervalele pe săptămâni nu modelează toate
dependențele persistente dintre echipe. Rapoartele JSON includ și Brier/ECE
pe ligă, intervale de scor și grupe de calibrare, cu intervale Wilson
descriptive ale frecvențelor. **Niciun candidat nu este promovat.**

## Cote și protecția împotriva semnalelor false

Au fost reauditate **2.200 observații reale existente**: 59 evenimente cu
consens, 32 cu diferență model–piață de cel puțin 10 pp și o piață incompletă
exclusă. Acestea sunt probabilitățile modelului din fotografia istorică a
cotelor, nu probabilitățile curente corectate. Timestampul original este
păstrat; recalcularea raportului nu face cotele proaspete.

Potrivirea cere identități canonice exacte, aceeași competiție și start cu
toleranță de cel mult 60 de secunde. Sunt cerute piețe complete ale aceleiași
case și scanări, timestamp explicit și cote valide. Bugetul lipsă/corupt,
modelul vechi, erorile și lipsa cheii închid scanarea și golesc watchlist-ul.
Contorul local de credite este conservator, dar nu poate garanta persistența
unei rezervări dacă runnerul dispare înainte de salvarea în Git.

Numele casei și booleenii „verificat” nu deblochează recomandări sau profit.
**Semnale confirmate: 0. ROI: indisponibil.** Reperul istoric no-vig cu
proveniență prospectivă completă are **N=0** și este marcat indisponibil;
cotele actuale nu au fost inventate pentru meciurile istorice. Acoperirea
exactă a operatorilor RO rămâne nedemonstrată; vezi
[PROVIDER_COVERAGE.md](PROVIDER_COVERAGE.md).

## Testare și livrare

Verificări locale finale: **92 teste Python**, cele șase self-testuri de
module, sintaxă pentru 15 fișiere Python și 5 JavaScript, actionlint și
verificarea contractelor JSON trecute. Suita completă de browser are 40 de
cazuri, inclusiv separarea scorurilor prospective pe versiune.

Testele Python verifică identități, sezoane, duplicate/conflicte, data-limită,
formule, jurnal/versionare, cronologia Elo, izolarea selecției și calibrării,
cote incomplete/vechi, bugete și erori, booleeni falsificați și salvarea în Git
cu refuzul unei revizii depășite. Comparația numerică independentă cu SciPy,
pe 1.000 de cazuri, a confirmat Poisson/binomială negativă/1X2 în limitele
rotunjirii; au fost verificate separat medii de până la 100.000 pentru totaluri.

Testele Playwright rulează pe Chromium desktop și mobil: filtre, explicații,
toate meciurile în selector, cote introduse manual, panouri de cercetare,
offline, timeout de 8 secunde, încărcare lentă, refresh eșuat, timestamps
invalide/viitoare/vechi, date locale, XSS și lipsa depășirii orizontale.
Verificarea JSON confirmă 200 meciuri/800 estimări, normalizarea, lipsa
selecțiilor value și păstrarea tuturor înregistrărilor originale.

CI rulează pe branch-uri/PR-uri: Python, sintaxă JS, actionlint cu versiune și
checksum fixate, browser și import real cu artefacte. Acest CI are token doar
pentru citire, nu primește cheia cotelor și nu publică. Workflow-urile care
scriu în `main` folosesc același grup de concurență, fișiere permise explicit
și verificarea reviziei inițiale. Nu mai există resetare la `main` urmată de
copierea tuturor JSON-urilor. Publicarea verifică și snapshotul servit public;
recuperarea Pages cere explicit deploymentul exact, aflat încă în așteptare.

Site-ul public existent a fost verificat separat în browser: HTTP 200,
200 carduri, panourile existente și zero erori JavaScript. Publicarea inițială
[42268463347](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42268463347)
s-a încheiat cu succes. **Aceasta este versiunea de pe `main`; schimbările
branch-ului nu au fost integrate sau publicate în producție.** Rezultatele CI
pentru noua revizie sunt atașate PR-ului și pot fi consultate în
[Actions pe branch](https://github.com/alexpuiu06-ship-it/valueradar-app/actions?query=branch%3Acodex%2Frobust-analysis-audit).

## Probleme rămase și pasul următor

Lipsesc confirmarea feedurilor și regulilor operatorilor RO, evaluarea
prospectivă suficientă a noii versiuni și intervalele probabilităților
individuale. Sursele publice pot întârzia sau conține greșeli; arbitrii,
formațiile, accidentările și contextul tactic nu intră în model. Nu s-au
adăugat factori inexistenți sau servicii cu plată.

Următorul pas este verificarea PR-ului și a artefactelor CI, apoi integrarea
controlată și verificarea publicării noii versiuni. Colectarea prospectivă
continuă fără recomandări value; o integrare comercială de cote ar necesita
separat dovada acoperirii, drepturi de folosire și acord pentru eventuale costuri.
