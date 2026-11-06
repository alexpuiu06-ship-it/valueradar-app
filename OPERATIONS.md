# Funcționarea și publicarea ValueRadar

Aplicația publică este la https://alexpuiu06-ship-it.github.io/valueradar-app/.
Probabilitățile rămân experimentale. Nicio selecție value nu este confirmată,
iar cotele internaționale nu sunt oferte românești verificate.

**Regimul ales de proprietar este momentan monitorizarea gratuită.** PropLine
continuă verificarea zilnică de cel mult cinci cereri gratuite; OddsPapi nu
are programare automată. Evaluarea comercială și solicitarea de demo sunt
amânate. Plafonul de £49/lună discutat anterior nu este o instrucțiune de
achiziție în acest regim. Nu sunt necesare alte configurări din partea
proprietarului pentru continuarea monitorizării existente.

## Actualizarea automată

Un singur workflow de producție, „ValueRadar / actualizare date”, importă,
salvează și publică. Actualizarea modelului rulează aproximativ la patru ore.
Scanarea internațională păstrează programarea de două ori pe zi; cheia este
citită numai din GitHub Actions Secrets. Importul și toate rapoartele unei
rulări folosesc aceeași fotografie a datelor.

La modificări de cod și duminica se recalculează împreună laboratorul,
calibrarea și Elo, apoi se publică alături de modelul operațional. Workflow-urile
separate de cercetare sunt doar pentru rulări manuale și artefacte descărcabile;
nu scriu în repository și nu pot înlocui o publicare aflată în așteptare.

O rulare manuală are trei opțiuni, implicit dezactivate:

- refresh_research: recalculează și publică rapoartele, fără credite de cote.
- scan_odds: solicită cote, în limita bugetului existent; nu cumpără credite.
- probe_ro: verifică diagnosticul de acoperire Superbet RO/NetBet RO, cel mult
  cinci cereri gratuite. Nu salvează prețuri și nu activează recomandări.

Diagnosticul RO rulează separat zilnic la **06:37 UTC**, prin același writer
de producție. PROPLINE_API_KEY este transmisă numai acestei probe sau unei
rulări manuale care o cere explicit. Un răspuns parțial ori o eroare de furnizor
produce un status vizibil, fără a bloca actualizarea modelului. Un raport cu
prețuri brute, numărători inconsistente sau indicatori de value confirmați
este refuzat înainte de publicare. Nu există retry automat care să consume
cereri în buclă.

Panoul RO arată fotografii istorice, cu momentul fiecărei probe și pragul de
120 secunde aplicat atunci. Un diagnostic mai vechi de 24 ore este marcat
explicit. Verificarea zilnică nu este un serviciu de cote în timp real.

Același workflow manual de evaluare permite și OddsPapi. Contul gratuit a fost
testat, însă proba nu a confirmat piețe acceptabile la cele două case RO;
rezultatele sunt în [ODDSPAPI_EVALUATION.md](ODDSPAPI_EVALUATION.md). O probă
folosește cel mult 12 cereri contorizate pentru toate ligile sau patru pentru
una, plus verificările necontorizate ale contului. Nu rulează automat și nu
este integrată în scannerul de producție. Cheia este transmisă numai pasului
furnizorului selectat, iar rapoartele nu conțin cote sau identificatori de cont.

Publicarea verifică timestamp-ul datelor servite și amprenta HTML-ului și a
celor cinci scripturi. Un răspuns HTTP 200 cu fișiere vechi nu este succes.
Dacă main se schimbă în timpul calculului, salvarea este refuzată; o nouă
rulare pe ultima revizie este preferabilă suprascrierii jurnalului.

## Starea datelor

„Ultima actualizare” arată când s-a executat analiza. Panoul „Starea datelor
pe ligi și piețe” arată ultima partidă efectiv disponibilă și sursele lipsă.
Aceste două momente au semnificații diferite.

O sursă de rezultate curente indisponibilă, un istoric neverificabil sau mai
vechi de 21 de zile blochează comparațiile curente pentru piața afectată.
Acesta este un prag conservator de funcționare, nu o calibrare statistică.
Și în pauza dintre sezoane se așteaptă date recente; nu se inventează rezultate.
Calculele istorice de cercetare nu sunt schimbate de această regulă.

La pierderea conexiunii sau expirarea celor 8 secunde de încărcare, pagina
ascunde analizele și blochează comparația. „Reîncarcă datele” verifică din nou
fișierele publice. Verificarea minutului curent elimină meciurile începute,
fără să închidă explicațiile și fără să șteargă o comparație încă valabilă.

## Dovezile prospective

Jurnalul păstrează prima estimare a fiecărei versiuni. Dublurile canonice,
inclusiv aceeași echipă scrisă diferit, opresc salvarea înainte de orice
modificare. Scorurile versiunilor nu sunt amestecate ca dovadă de validare.
Un raport Elo din altă versiune nu poate fi asociat cu probabilitățile curente.

Testele CI și funcționarea publicării demonstrează funcționarea tehnică,
nu existența unui profit. Pentru oferte RO este necesară confirmarea unui
furnizor, a drepturilor de folosire și a regulilor fiecărei piețe; un serviciu
plătit necesită acord separat.
