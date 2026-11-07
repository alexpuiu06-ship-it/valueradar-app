# Funcționarea și publicarea ValueRadar

Aplicația publică este la https://alexpuiu06-ship-it.github.io/valueradar-app/.
Probabilitățile rămân experimentale. Nicio selecție value nu este confirmată,
iar cotele internaționale nu sunt oferte românești verificate.

**Regimul ales de proprietar este momentan monitorizarea gratuită.** PropLine
continuă verificarea zilnică de cel mult cinci cereri gratuite. Proba de cote
OddsPapi rămâne manuală; verificarea scorurilor finale rulează săptămânal,
tot în planul gratuit. Evaluarea comercială și solicitarea de demo sunt
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

O rulare manuală are patru opțiuni, implicit dezactivate:

- refresh_research: recalculează și publică rapoartele, fără credite de cote.
- scan_odds: solicită cote, în limita bugetului existent; nu cumpără credite.
- probe_ro: verifică diagnosticul de acoperire Superbet RO/NetBet RO, cel mult
  cinci cereri gratuite. Nu salvează prețuri și nu activează recomandări.
- probe_scores: verifică cel mult cinci rezultate la 90 minute pentru meciuri
  arhivate, maximum 12 cereri din contul gratuit OddsPapi. Sunt folosite numai
  la evaluare, separat de antrenare și istoricul statistic.

Diagnosticul RO rulează separat zilnic la **08:37 ora României iarna / 09:37 vara
(06:37 UTC)**, prin același writer
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

Opțiunea `OddsPapi scores` din același workflow verifică separat scoruri la
90 de minute pentru cel mult cinci meciuri arhivate care așteaptă rezultate.
Plafonul este tot 12 cereri contorizate, numai din planul gratuit de 250,
cu rezervă de zece. Proba diagnostică nu scrie în producție. Același control
rulează în writer-ul unic duminica la **07:41 ora României iarna / 08:41 vara
(05:41 UTC)** sau prin `probe_scores`. Un cont fără planul gratuit confirmat
este refuzat; o probă fără meciuri în așteptare nu face cereri. Plafonul
programat este de cel mult 60 de cereri într-o lună cu cinci duminici, înainte
de orice probă manuală, iar contul este reverificat înaintea fiecărei probe.

Numai observațiile individuale valide decontează 1X2/goluri în jurnalul
curent, cu dovada identității, finalului, perioadei `fulltime`, sursei,
momentelor și amprentelor. O probă parțială rămâne explicit incompletă;
celelalte meciuri și piețe continuă să aștepte date. Aceste rânduri nu intră
în antrenare, calibrare retrospectivă sau indicatorii de prospețime a datelor
statistice. Nu există feed brut public ori prețuri din această sursă.

Dovada externă folosește schema 3; schemele 1 și 2 rămân citibile. Dispariția
temporară a sursei păstrează dovada arhivată, iar un rezultat principal
contradictoriu exclude decontarea din evaluare fără să o rescrie. Panoul arată
numărul de meciuri/estimări evaluate din această sursă și limitele eșantionului.
Momentul și starea ultimei probe sunt păstrate și la actualizările fără API;
un diagnostic incomplet sau blocat nu este înlocuit cu o confirmare de succes.
Scorurile finale din dovezile arhivate pot menține starea „așteaptă statistici”
fără o cerere nouă. Sursele curente au prioritate la comparația cu arhiva;
două rezultate curente contradictorii sunt carantinate explicit și exclud
decontările afectate, fără a fi confundate cu o sursă temporar dispărută.

Publicarea verifică timestamp-ul datelor servite și amprenta HTML-ului și a
celor cinci scripturi. Un răspuns HTTP 200 cu fișiere vechi nu este succes.
Verificările permit până la 18 încercări, la cinci secunde, pentru propagarea
Pages. Dacă fotografia sau fișierele tot nu corespund, writer-ul încearcă o
singură republicare a aceluiași artefact deja validat, apoi repetă obligatoriu
controlul public. O a doua nepotrivire eșuează rularea. Recuperarea nu reface
importul, nu modifică jurnalul și nu consumă credite ale furnizorilor.
Dacă main se schimbă în timpul calculului, salvarea este refuzată; o nouă
rulare pe ultima revizie este preferabilă suprascrierii jurnalului.

## Starea datelor

Panoul „Monitorizare și decontarea estimărilor” asociază raportul cu exact
aceeași analiză și versiune. Semnalează peste șase ore fără analiză nouă și
peste 30 de ore fără probă RO. Acestea sunt avertizări de întârziere, nu dovezi
că GitHub Actions a eșuat. Problemele rămân vizibile chiar dacă unele surse au
răspuns. Panoul nu trimite e-mailuri sau alte notificări externe.

Istoricul RO păstrează cel mult 512 probe în ultimele 90 de zile. Sunt salvate
numai timestamp-uri, stări și numărători pe ligă/casă, fără cote, selecții sau
răspunsuri brute. O rulare a modelului care recitește aceeași probă nu adaugă
o observație și nu îi actualizează momentul. Modificarea unei probe deja
înregistrate este refuzată; fișierul corupt nu este înlocuit cu un istoric gol.
Zilele sunt grupate în fusul Europe/Bucharest; zilele lipsă rămân lipsă.
Prima observație este ultima probă reală existentă la activare, nu o serie
reconstituită retrospectiv. Numărul de probe cu potriviri nu reprezintă
procentul întregii oferte acoperite; aceleași meciuri pot reapărea.

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

Politica de decontare `observed_results_v1` cere identitate exactă, moment de
creare anterior startului și rezultat/statistici disponibile. Dacă ora
rezultatului diferă cu peste 60 secunde de ora arhivată, decontarea este
oprită. Se așteaptă cel puțin două ore după cel mai târziu start cunoscut;
aceasta este o regulă operațională, nu confirmarea independentă a finalului.

La decontare se adaugă valorile observate, amprenta lor, sursele și amprentele
fișierelor sursă disponibile. Predicția și timestamp-ul inițial rămân intacte.
În dovezile noi (schema 2), amprentele folosesc identitatea literală arhivată,
astfel încât un alias nou
nu invalidează dovezile vechi. Fișierele sursă sunt selectate și după ligă și
tipul rezultatului; un identificator comun al familiei nu include alte ligi
sau fișiere de program în dovada meciului.
Dovezile și rapoartele din schema 1 rămân citibile, fără rescrierea arhivei.
O corecție ulterioară a rezultatului exclude scorul afectat și este raportată;
decontarea inițială nu este rescrisă. Dovada arhivată validă rămâne evaluabilă
dacă sursa lipsește într-o rulare ulterioară, în absența unui conflict cunoscut.

Raportul separă estimările viitoare, ora necunoscută în arhiva veche, perioada
minimă de verificare, rezultatele/statisticile lipsă și carantina. Lipsa datelor
mai mult de 48 ore după perioada minimă de verificare este semnalată explicit.
Numărătorile sunt estimări distincte per piață/versiune, cu numărul de meciuri
afișat separat. Scorurile prospective și comparația cu piața folosesc aceeași
eligibilitate de decontare. Niciun astfel de raport nu deblochează value sau ROI.

Fișierele `settlement_report.json`, `ro_feed_history.json` și
`operations_report.json` sunt generate și salvate de writer-ul unic.
Contractele verifică numărătorile și asocierea cu analiza, iar publicarea
compară și amprentele acestor fișiere servite public.

Jurnalul păstrează prima estimare a fiecărei versiuni. Dublurile canonice,
inclusiv aceeași echipă scrisă diferit, opresc salvarea înainte de orice
modificare. Scorurile versiunilor nu sunt amestecate ca dovadă de validare.
Un raport Elo din altă versiune nu poate fi asociat cu probabilitățile curente.

Testele CI și funcționarea publicării demonstrează funcționarea tehnică,
nu existența unui profit. Pentru oferte RO este necesară confirmarea unui
furnizor, a drepturilor de folosire și a regulilor fiecărei piețe; un serviciu
plătit necesită acord separat.
