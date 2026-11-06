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
confirmate de cont după ultima probă. Nu există programare automată OddsPapi;
monitorizarea zilnică din aplicație folosește PropLine și plafonul său separat.

Workflow-ul existent „evaluare gratuita feed RO” permite alegerea furnizorului.
Pentru OddsPapi, „All leagues” este un singur job serial, astfel încât cele
două cataloage sunt cerute o singură dată. Numai pasul furnizorului ales primește
cheia sa. Rapoartele agregate sunt păstrate ca artefacte pentru verificare.

## Următorul pas

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
