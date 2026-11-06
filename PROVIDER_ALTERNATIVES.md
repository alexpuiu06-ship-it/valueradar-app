# Alternative pentru cote RO — verificare 6 noiembrie 2026

Bugetul acceptat de proprietar este cel mult **£49/lună pentru două case**,
cu preferință pentru un raport preț/calitate mai bun. Niciun abonament nou
nu a fost cumpărat. Recomandarea este un pilot gratuit înaintea oricărei plăți.

| Furnizor | Preț public relevant | Acoperire RO identificată | Ce nu este încă demonstrat |
|---|---|---|---|
| PropLine | Gratuit: 1.000 cereri/zi; Hobby opțional $9/lună | Superbet RO și NetBet RO, explicit, inclusiv cele cinci ligi | Cotele autentificate pentru contul nostru, decontarea și concordanța cu operatorul |
| OddsPapi | Gratuit: 250 cereri/lună; tarifele plătite se configurează | Pagini specifice Superbet RO, Betano RO, MrBit RO și Casa Pariurilor RO | Oferta exactă a contului, toate piețele, dreptul de publicare/retentie necesar |
| Odds-API.io | Solo: £49/lună, două case | Superbet RO, Betano RO și MrBit RO listate explicit; Casa Pariurilor listată | Unibet RO și NetBet RO exacte, piață/linie/reguli și contractul ales |
| The Odds API, integrarea existentă | Planul existent cu plafon local de consum | UK/internațional; nu confirmă cele șase versiuni RO | Nu trebuie folosit ca înlocuitor al ofertelor românești |

Acestea sunt declarații publice ale furnizorilor, nu un audit independent al
fiecărei cote. Termenii, disponibilitatea și prețurile se pot modifica.
Sumele sunt în moneda furnizorului; nu sunt oferte ferme cu taxe/conversie.

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

## Activarea probei, fără programare

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
  [lista caselor](https://odds-api.io/sportsbooks).
- [The Odds API: bookmakeri și regiuni](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html).
