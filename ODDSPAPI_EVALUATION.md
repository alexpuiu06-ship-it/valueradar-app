# OddsPapi — probă reală, 6 noiembrie 2026

Cheia ODDSPAPI_API_KEY este configurată în GitHub Actions Secrets și a fost
acceptată. Contul are limita de 250 cereri/lună, fotbalul și identificatorii
exacți `superbet.ro` și `betano.ro`. Niciun abonament nu a fost cumpărat.

## Rezultat și limite

[Proba celor cinci ligi](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42289553050)
a verificat catalogul competițiilor și definiția 1X2: fotbal, rezultat final,
fără handicap ori jucător, trei rezultate distincte. A găsit 29 de meciuri
neambigue care se potriveau cu modelul. A cerut cotele pentru **un singur
meci din fiecare ligă**, ales determinist dintre cele eligibile. Nu a testat
toate cele 29 de meciuri și nu măsoară întreaga ofertă a furnizorului.

La **20:35:03–20:35:14 UTC**, niciuna dintre cele zece combinații meci/casă
testate nu a trecut toate verificările de structură și activitate. Superbet
avea 1X2 lipsă sau inactiv; Betano avea colectarea marcată inactivă ori casa
suspendată. Statusul general a rămas `incomplete_quote_validation`.

[Reverificarea Premier League](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42289803370)
de la **20:36:51 UTC** separă exact cauzele:

| Diagnostic | Superbet RO | Betano RO |
|---|---:|---:|
| Colectarea casei activă, declarată de furnizor | Da | Nu |
| Casa suspendată | Nu | Nu |
| Piețe primite, orice tip | 317 | 209 |
| Piețe marcate active, orice tip | 15 | 209 |
| Piața 1X2 identificată în răspuns | Da | Da |
| Piața 1X2 marcată activă | Nu | Da |
| 1X2 acceptat după toate verificările | Nu | Nu |

O piață Betano marcată activă nu anulează indicatorul că furnizorul nu mai
colectează activ acea casă. O listare în catalog sau un cont cu acces nu
constituie confirmare a unei cote actuale. Aceste rezultate nu demonstrează
absența tuturor ofertelor RO, dar nu susțin promovarea acestui feed.

## Timestamp și protecții

Documentația definește `changedAt` ca ultima schimbare înregistrată de preț,
iar `bookmakerChangedAt` ca ultima schimbare raportată de bookmaker. Niciunul
nu este automat ultima livrare verificată. Codul poate număra schimbările
de preț pe intervale de vârstă, dar păstrează permanent
`delivery_freshness_verified=false`, `operator_prices_independently_verified=false`
și `verified_value=false`.

Contul brut poate include cheia API; nu este salvat sau tipărit. Se extrag
numai limita, consumul și booleeni pentru fotbal/cele două case. URL-ul
autentificat nu ajunge în loguri, redirecturile sunt refuzate, iar erorile au
coduri dintr-o listă fixă. Nu sunt salvate prețuri, selecții, răspunsuri brute,
identificatori ai contului, pariuri sau ROI.

Sunt acceptate numai identități/kickoff compatibile cu modelul, stare explicit
pre-match, piață completă, selecții active și principale, cote numerice valide
și marjă plauzibilă. Dublurile și orice schimbare de identitate/start între
lista meciurilor și răspunsul cotelor sunt respinse. Verificările se repetă
la primirea răspunsului pentru a exclude un meci început în timpul cererii.

## Consum și operare

`/account` este necontorizat. Cataloagele, lista meciurilor și cotele sunt
contorizate inclusiv la erori. Prima probă s-a oprit la limita inițială de
dimensiune a catalogului; descărcarea catalogului global are acum o limită
separată de 32 MiB, iar răspunsurile cu cote rămân limitate la 5 MB.

Proba completă folosește cel mult **12 cereri contorizate**; o singură ligă
folosește cel mult patru. Se păstrează rezervă de zece cereri și nu există
retry automat. Cele trei probe au consumat în total **18/250**, cu **232 rămase**
confirmate de cont după acea probă de cote. Monitorizarea zilnică RO folosește
PropLine și plafonul său separat. Verificarea suplimentară de scoruri de mai
jos are un consum separat în același cont gratuit OddsPapi.

Workflow-ul existent „evaluare gratuita feed RO” permite alegerea furnizorului.
Pentru OddsPapi, „All leagues” este un singur job serial, astfel încât cele
două cataloage sunt cerute o singură dată. Numai pasul furnizorului ales primește
cheia sa. Rapoartele agregate sunt păstrate ca artefacte pentru verificare.

## Următorul pas

### Diagnostic separat pentru scoruri finale

Opțiunea manuală `OddsPapi scores` verifică cel mult cinci meciuri cu
predicții 1X2 arhivate înainte de start, din versiunea curentă a pipeline-ului.
Diagnosticul nu scrie în aplicație și nu decontează predicții. Folosește cel
mult 12 cereri contorizate și două verificări necontorizate ale contului;
refuză orice plan care nu confirmă limita gratuită de 250 și păstrează zece
cereri în rezervă. Nu are retry.

Potrivirea cere aceeași ligă, echipe în aceeași ordine și kickoff la cel mult
60 secunde. Starea trebuie să fie explicit `Finished` sau `Ended`, împreună
cu un cod terminal; documentația celor două endpoint-uri diferă asupra
codurilor numerice, deci un număr singur nu este dovadă. Identitatea și starea
sunt reverificate după citirea scorului. Dublurile sunt respinse integral.

Ghidul oficial de fotbal definește `scores.periods.fulltime` ca scorul la 90
minute. `result` poate include prelungiri și nu este substituit. Cheile
numerice din exemplul vechi al endpoint-ului nu au semnificație documentată
suficient și sunt respinse. Un meci recent, un scor invalid ori fără dovadă
de final rămâne incomplet. Rapoartele conțin cel mult cinci observații despre
meciurile arhivate, nu feedul brut, cote sau informații de cont. Validarea
parțială nu primește status de validare completă. Nu confirmă reguli de
decontare ale operatorilor sau profit.

[Prima probă reală de scoruri](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42315106673),
la 7 noiembrie, 01:56–01:57 ora României, a verificat cinci meciuri arhivate.
Patru au trecut controalele de identitate/final/scor la 90 minute; al cincilea
nu s-a potrivit fără ambiguități. Statusul a rămas incomplet. Consumul a fost
10 cereri contorizate, de la 18 la 28 utilizate, cu 222/250 rămase după probă.
Acesta este un eșantion mic, nu o măsură a acoperirii întregului sezon.

[Reverificarea cu dovadă completă](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42316200928)
de la **02:07 ora României** a confirmat aceleași patru meciuri. Perechea
Toulouse–Strasbourg nu a fost identificată în fereastra extinsă de descoperire;
nu s-a forțat o potrivire. Proba a rămas incompletă, cu încă zece cereri,
38/250 utilizate și 212 rămase. Metadatele finalului, identitățile participanților,
reverificarea și amprentele observațiilor au trecut contractele locale.

[Rularea de producție](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42317213394)
a calificat aceleași patru meciuri și a evaluat opt predicții arhivate,
separat pentru 1X2/goluri. A consumat zece cereri: **48/250 utilizate,
202 rămase** la 02:18 ora României. Republicarea Pages a refolosit artefactul;
nu a interogat din nou furnizorul. Cotele RO, value și ROI rămân nevalidate.

Writer-ul de producție poate folosi numai observațiile individuale validate
pentru evaluarea predicțiilor curente 1X2/goluri. Dovada completă este parte
din decontarea predicției; nu se distribuie un produs separat de scoruri sau
răspunsul furnizorului. Termenii interzic redistribuirea ca produs de sine
stătător și cer verificarea datelor; această integrare este limitată la
analiza predicțiilor proprii. Nu se declară verificare independentă la operator.

Verificarea de producție este săptămânală, prin același writer, cel mult
12 cereri/rulare și 60 într-o lună cu cinci duminici, plus probele manuale
controlate. Contul gratuit, dreptul la fotbal și rezerva sunt reverificate.
Nu antrenează modelul și nu completează statistici de cartonașe/cornere/faulturi.
Regulile, dovezile arhivate și tratarea corecțiilor sunt în [OPERATIONS.md](OPERATIONS.md).

PropLine rămâne monitorizat gratuit, cu acoperire parțială declarată. Nici
PropLine, nici eșantionul OddsPapi nu justifică un feed RO complet sau un semnal
value. Înaintea unei alternative plătite sunt necesare o probă pe piețele și
casele exacte, prețul total cu taxe și dreptul de afișare/păstrare a datelor
în aplicația publică. Plata nu înlocuiește această verificare.

## Surse oficiale

- [Cereri și cotă](https://oddspapi.io/en/docs/requests-and-quota)
- [Cont](https://oddspapi.io/en/docs/get-account)
- [Competiții](https://oddspapi.io/en/docs/get-tournaments)
- [Catalogul piețelor](https://oddspapi.io/en/docs/get-markets)
- [Meciuri](https://oddspapi.io/en/docs/get-fixtures)
- [Cote și semnificația câmpurilor](https://oddspapi.io/en/docs/get-odds)
- [Tarife](https://oddspapi.io/en/pricing)
- [Termeni](https://oddspapi.io/en/legal/terms)
- [Scoruri](https://oddspapi.io/en/docs/get-scores)
- [Identitate și stare individuală](https://oddspapi.io/en/docs/get-fixture)
- [Ghid oficial fotbal: fulltime și result](https://oddspapi.io/blog/football-data-api-betting-predictions/)
