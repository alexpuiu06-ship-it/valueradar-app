# Alternative pentru cote RO — verificare 6 noiembrie 2026

**Decizia curentă: continuăm momentan numai cu monitorizarea gratuită.**
Evaluarea comercială și solicitarea de demo sunt amânate. Plafonul anterior
de **£49/lună pentru două case** rămâne doar o referință pentru o eventuală
reluare a discuției de către proprietar. Niciun abonament nou nu a fost cumpărat.

| Furnizor | Preț public relevant | Acoperire RO identificată | Ce nu este încă demonstrat |
|---|---|---|---|
| PropLine | Gratuit: 1.000 cereri/zi; Hobby opțional $9/lună | Superbet RO și NetBet RO; autentificare testată, acoperire observată parțială | Stabilitatea acoperirii, decontarea și concordanța cu operatorul |
| OddsPapi | Gratuit: 250 cereri/lună; tarifele plătite se configurează | Pagini specifice Superbet RO, Betano RO, MrBit RO și Casa Pariurilor RO | Oferta exactă a contului, toate piețele, dreptul de publicare/retentie necesar |
| Odds-API.io | Solo: £49/lună, două case | Superbet RO, Betano RO și MrBit RO listate explicit; Casa Pariurilor listată | Unibet RO și NetBet RO exacte, piață/linie/reguli și contractul ales |
| The Odds API, integrarea existentă | Planul existent cu plafon local de consum | UK/internațional; nu confirmă cele șase versiuni RO | Nu trebuie folosit ca înlocuitor al ofertelor românești |

Acestea sunt declarații publice ale furnizorilor, nu un audit independent al
fiecărei cote. Termenii, disponibilitatea și prețurile se pot modifica.
Sumele sunt în moneda furnizorului; nu sunt oferte ferme cu taxe/conversie.

**Actualizare autentificată OddsPapi:** cheia este confirmată, cu acces declarat
la Superbet RO/Betano RO. Proba unui meci din fiecare ligă nu a găsit un 1X2
care să treacă toate verificările la ambele case. Au rămas 232/250 cereri.
Vezi [raportul real și limitele eșantionului](ODDSPAPI_EVALUATION.md).

**Reverificarea alternativei comerciale:** documentația Odds-API.io listează
Solo £49/lună, iar pagina de tarife servită în USD listează $65/lună. Moneda
și taxele se confirmă la checkout; nu considerăm automat aceste sume identice.
Cheile gratuite noi sunt suspendate conform documentației. Termenii actuali
cer clarificarea redistribuirii pentru un site public. Nu a fost efectuat
checkout și nu avem o ofertă completă care să confirme costul total în buget.

## De ce pilotul PropLine este primul test

Documentația identifică explicit bookmakerii superbet_ro și netbet_ro,
jurisdicția România și cote pre-match în cele cinci ligi urmărite. Planul
gratuit nu cere card și are suficientă cotă de cereri pentru o probă limitată.
Planul Hobby nu este necesar pentru testarea 1X2; istoricul/CLV se evaluează
separat, numai dacă datele de bază trec verificările.

Endpointul public de stare a răspuns real la 6 noiembrie, 21:21 ora României.
Snapshotul furnizorului raporta actualizări globale recente pentru ambele
case, dar și piețe vechi coexistente. O actualizare recentă pentru un bookmaker
nu dovedește prospețimea fiecărei cote. Acesta nu a fost un test autentificat
al prețurilor și nu confirmă oferta efectiv accesibilă unui utilizator.

Codul de evaluare este ro_feed_probe.py și workflow-ul „ValueRadar / evaluare
gratuita feed RO”. El face cel mult **o cerere autentificată pentru o ligă**,
filtrată la cele două case și 1X2. Verifică startul, identitățile, piața completă,
perioada, suspendarea și timestamp-ul fiecărei selecții. Transformă explicit
formatul american documentat în cote zecimale. Păstrează doar numere agregate,
fără cote brute, pariuri sau ROI.

## Configurarea cheii

PROPLINE_API_KEY este deja configurată și a fost verificată prin cereri reale.
Pașii următori sunt păstrați doar pentru o eventuală înlocuire a cheii:

1. Creează un cont gratuit folosind [Get Free Key](https://prop-line.com/pricing).
   Nu este necesar un plan plătit pentru această probă.
2. Adaugă cheia în [GitHub Actions Secrets](https://github.com/alexpuiu06-ship-it/valueradar-app/settings/secrets/actions/new),
   cu numele exact PROPLINE_API_KEY. Nu o trimite în chat și nu o pune în repository.
3. După această configurare pot rula și interpreta testul din Actions.
   Proba fără autentificare funcționează deja și este etichetată explicit
   „stare publică”, fără a pretinde că a verificat cote.

Integrarea de producție rămâne separată până când proba autentificată
confirmă acoperirea și regulile. Acordul de buget nu transformă o listare
comercială într-o ofertă verificată și nu deblochează semnale value.

## Prima probă autentificată

La 6 noiembrie 2026 cheia a fost confirmată de API, cu plan gratuit de
1.000 cereri/zi și 999 rămase după prima cerere. Răspunsul Premier League
conținea 17 piețe NetBet RO complete și recente, dintre care 15 potrivite
cu modelul curent. Superbet RO nu a fost confirmat în acel răspuns, deci
proba a fost marcată incompletă; nu s-au deblocat recomandări sau ROI.

Aceste numere descriu fotografia inițială, înaintea verificării celorlalte
ligi și a revizuirii suplimentare a numărătorilor. Nu sunt o promisiune de
acoperire permanentă. Filtrul de 120 de secunde elimină piețele prea vechi;
statistica globală „bookmaker proaspăt” nu dovedește existența unui 1X2
proaspăt pentru fiecare ligă.

Workflow-ul permite și „All leagues”: cinci joburi seriale, cel mult o cerere
per ligă, cu rapoarte separate. Un rezultat incomplet rămâne vizibil chiar
când alte ligi trec verificările. Nicio cotă brută și nicio cheie nu sunt
salvate în aceste rapoarte.

Pentru alternativa OddsPapi, documentația limitează bulk-ul la trei ligi și
un singur bookmaker per cerere. Toate cele cinci ligi și două case înseamnă
patru cereri per scanare. O scanare pe zi folosește 124 într-o lună de
31 de zile; două folosesc 248 și nu lasă rezervă adecvată pentru metadata,
erori sau repetări. Planul gratuit trebuie bugetat cu această limitare.

## Rezultatele pe toate cele cinci ligi

Proba extinsă din **6 noiembrie, 20:13:22–20:13:59 UTC** este disponibilă în
[Actions](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42286457429).
Cererea a permis livrări cu timestamp de până la 3.600 secunde pentru diagnostic;
acceptarea locală a rămas la **120 secunde**, atât pentru piață, cât și pentru
fiecare selecție. Acesta este ultimul răspuns disponibil, nu un istoric al cotelor.

| Ligă | Blocuri Superbet / NetBet primite | Piețe complete și recente Superbet / NetBet | Potrivite cu modelul Superbet / NetBet |
|---|---:|---:|---:|
| Premier League | 9 / 19 | 0 / 0 | 0 / 0 |
| La Liga | 9 / 19 | 0 / 0 | 0 / 0 |
| Serie A | 9 / 19 | 0 / 14 | 0 / 14 |
| Bundesliga | 8 / 17 | 0 / 0 | 0 / 0 |
| Ligue 1 | 8 / 17 | 1 / 0 | 0 / 0 |

Majoritatea blocurilor au fost respinse pentru timestamp vechi. Acea respingere
oprește verificările ulterioare, deci nu dovedește că piața era altfel completă.
Singura piață Superbet recentă din Ligue 1 nu s-a potrivit cu programul modelului:
Auxerre–Paris avea startul 18:00 UTC la furnizor și 16:15 UTC în sursa programului.
Conflictul este respins; nu am ales arbitrar o oră. Identificările observate
Coventry City, Betis, Hull City și Paderborn au aliasuri exacte, fără potrivire
aproximativă și fără modificarea istoricului modelului.

Fotografiile anterioare au avut și 17 piețe NetBet Serie A sau piețe Superbet
La Liga, care ulterior nu mai treceau filtrul. Nu deducem acoperire permanentă
dintr-o probă reușită. Niciunul dintre cele cinci joburi nu a confirmat simultan
ambele case; rezultatul incomplet este intenționat vizibil în Actions.
Ultimul header de cotă de cereri raporta **988 rămase din 1.000**; valorile din
headere pot proveni din cache și nu înlocuiesc contorul de cereri emise.

Monitorul zilnic păstrează numai agregatele din `docs/ro_feed_status.json`,
fără exemple de identitate, selecții sau prețuri. Panoul din aplicație arată
momentul probei și numerele istorice; nu le prezintă ca oferte actuale. Lipsa
cheii, erorile, răspunsurile goale și diagnosticul mai vechi de 24 ore sunt explicite.
Nu sunt deblocate selecții value sau ROI. Detaliile programării sunt în
[OPERATIONS.md](OPERATIONS.md).

Nu există motiv demonstrat să cumpărăm Hobby pentru această lipsă de prospețime:
documentația PropLine descrie același răspuns `/odds` indiferent de nivelul
abonamentului. Următorul candidat rămâne planul gratuit OddsPapi înaintea unei
oferte de £49. Atenție: `changedAt` de la OddsPapi înseamnă ultima modificare de
preț, nu ultima livrare verificată; nu poate fi folosit automat ca dovadă de
prospețime. Nici răspunsul `/account`, care poate conține cheia, nici URL-urile
autentificate ale acelui furnizor nu trebuie salvate sau tipărite.

## Drepturi și limite

PropLine permite afișarea valorilor/insighturilor individuale în produs,
dar interzice redistribuirea în masă a datelor, a exporturilor și a corpusului.
De aceea pilotul nu salvează răspunsurile cu cote în repository sau artefacte.
Păstrarea unui istoric de cote pentru producție trebuie proiectată separat
în limitele licenței; nu copiem automat arhitectura publică de dumpuri JSON.

OddsPapi recomandă chiar pe pagina prețurilor testarea planului gratuit înainte
de cumpărare. Limita de 250 de cereri/lună trebuie bugetată după endpointurile
alese; nu promitem acoperirea continuă a tuturor ligilor din acea cotă.

## Surse oficiale

- [PropLine: tarife](https://prop-line.com/pricing), [documentație](https://prop-line.com/docs),
  [Superbet RO](https://prop-line.com/odds-api/book/superbet-ro),
  [NetBet RO](https://prop-line.com/odds-api/book/netbet-ro),
  [stare publică](https://prop-line.com/freshness), [termeni](https://prop-line.com/terms).
- [OddsPapi: cont gratuit](https://oddspapi.io/en/sign-up), [tarife](https://oddspapi.io/en/pricing),
  [Superbet RO](https://oddspapi.io/sportsbooks/superbet-ro),
  [Betano RO](https://oddspapi.io/blog/betano-api-odds-access/),
  [MrBit RO](https://oddspapi.io/sportsbooks/mrbit-ro),
  [Casa Pariurilor RO](https://oddspapi.io/sportsbooks/casapariurilor-ro).
- [Odds-API.io: tarife](https://odds-api.io/pricing),
  [lista caselor](https://odds-api.io/sportsbooks),
  [documentație și disponibilitatea cheilor](https://docs.odds-api.io/),
  [termeni și taxe](https://odds-api.io/terms).
- [The Odds API: bookmakeri și regiuni](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html).
