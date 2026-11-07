# ValueRadar — memorie operațională la închiderea din 7 noiembrie 2026

**Sesiunea de dezvoltare din 6–7 noiembrie este închisă la cererea
proprietarului.** Cele 12 PR-uri tehnice sunt integrate și publicate.
Automatizările existente continuă; alte lucrări de dezvoltare se reiau la
o cerere nouă. Nu există o achiziție, configurare de cheie sau decizie majoră
necesară pentru a închide ziua.

Aceasta este memoria proiectului păstrată în Git, pentru reluarea lucrului;
nu presupune acces la întreaga conversație ChatGPT. Citește acest fișier,
[ANALYSIS_METHODOLOGY.md](ANALYSIS_METHODOLOGY.md) și codul real înainte de
modificări. Valorile numerice de mai jos sunt fotografii datate, nu valori
care trebuie impuse unor rulări ulterioare.

## 1. Documentele de reluare

- [Bilanțul complet al sesiunii și cele 12 PR-uri](SESSION_CLOSE_2026-11-07.md).
- [Prezentarea pentru un posibil asociat](PROJECT_BRIEF_RO.md) și
  [versiunea PDF](reports/ValueRadar_Prezentare_Asociat_2026-11-07.pdf).
- [Operare, programări și publicare](OPERATIONS.md).
- [Protocolul comparației modelelor](RESEARCH_PROTOCOL.md) și
  [auditul cu etapele istorice](AUDIT_REPORT.md).
- [Alternative și limite de furnizori](PROVIDER_ALTERNATIVES.md),
  [evaluarea OddsPapi](ODDSPAPI_EVALUATION.md).
- [Documentul de predare anterior închiderii](history/CODEX_HANDOFF_BEFORE_CLOSE_2026-11-07.md),
  păstrat ca istoric; valorile sale vechi nu înlocuiesc această fotografie.

Repository public: https://github.com/alexpuiu06-ship-it/valueradar-app

Aplicație: https://alexpuiu06-ship-it.github.io/valueradar-app/

## 2. Intenția proprietarului și autorizațiile

Ținta este o aplicație practică și transparentă pentru Premier League, La
Liga, Serie A, Bundesliga și Ligue 1: 1X2, goluri, galbene, cornere și faulturi.
Pe termen de dezvoltare sunt vizate Superbet RO, Betano RO, Unibet RO,
MrBit RO, NetBet RO și Casa Pariurilor RO, fără a pretinde integrarea completă.

Proprietarul nu programează și dorește implementare autonomă de calitate,
nu opriri repetate pentru decizii tehnice obișnuite. Lucrează pe branch separat,
pregătește rezultate verificabile și continuă în scopul cererii active.
Întreabă doar pentru decizii majore, cheltuieli, chei ori autorizații lipsă.
La finalul etapei raportează ce s-a implementat, ce a trecut, ce rămâne și
ce urmează. Comunică în română.

**Decizia financiară actuală: numai monitorizare gratuită.** Referința de
£49/lună pentru două case a fost discutată, dar ultima instrucțiune amână
evaluarea comercială. Mesajul de demo din PROVIDER_ACCEPTANCE_REQUEST.md
este pregătit, netrimis și amânat. Nu contacta furnizori, nu cumpăra și nu
interpreta plafonul discutat ca instrucțiune de plată.

ODDS_API_KEY, PROPLINE_API_KEY și ODDSPAPI_API_KEY sunt configurate în GitHub
Actions Secrets. Nu le citi, copia, tipări sau introduce în client/repository.
Folosește numai workflow-urile cu bugete și pașii autorizați. Nu plasa pariuri.

## 3. Fotografia tehnică verificată

Snapshot: 7 noiembrie 2026, **02:30:29 Europe/Bucharest**,
adică 00:30:29 UTC. La această dată România este UTC+2. Convenția orelor din
programul open-matchday rămâne separat UTC+01:00 fix, conform sursei.

- Codul execuției: 82d77af9fe4cc70effdcd2feb1c08008f6e715d9; date publicate
  în commitul cu prefix b1e07c0. Verifică head-ul real, nu presupune că a rămas acesta.
- Pipeline: validated_identity_v2; formulă: weighted_opponent_model_v1.
- 20/20 resurse principale citite, două familii de surse; 3.935 rânduri
  istorice pentru model și 197 analize viitoare în snapshot.
- Jurnal: 2.010 estimări, 202 meciuri distincte; 1.000 legacy și 1.010 curente.
  Cele 2.000 inițiale au fost păstrate; nu reseta sau trunchia jurnalul.
- Evaluări eligibile curente: opt, din patru meciuri — patru 1X2 și patru
  goluri. Nu reprezintă opt observații sportive independente.
- Versiunea curentă: 985 viitoare, 12 așteaptă statistici, cinci estimări
  ale unui meci așteaptă rezultat/corelare, opt decontate cu dovadă.
- Legacy: 880 viitoare, 95 fără oră exactă și 25 fără dovada suficientă a
  creării înainte de start. Nu amesteca versiunile ca dovadă a modelului curent.
- Istoric RO: două probe reale; 90 zile, maximum 512 înregistrări; agregate,
  fără cote brute. Nu reconstitui zile lipsă.
- Value confirmat: zero; ROI indisponibil; reper de piață complet aliniat N=0.
- Ultima cotă OddsPapi verificată: 48/250 cereri folosite, 202 rămase,
  la 7 noiembrie 02:18 România. Contorul se verifică din nou numai prin
  calea sigură când este justificată o probă nouă.

Ultima rulare tehnică de producție verificată:
https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42318609591

Probe de scoruri și incidentul Pages recuperat:
https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42317213394

## 4. Modelul și concluziile de cercetare

Medii ponderate cu timp de înjumătățire 185 zile, regularizare cu șapte
pseudo-meciuri, producție/permisivitate acasă/deplasare combinate geometric.
Totaluri Poisson/binomială negativă; 1X2 din două Poisson independente.
Nu există factori de arbitru, accidentări, formații ori tactică în model.
Incertitudinea probabilității unei partide nu este încă cuantificată.

Comparația cronologică are suport comun 605 validare / 400 calibrare /
693 evaluare. Poisson log-loss 1,026404, Elo 1,000988, Poisson calibrat
1,018566. Câștigul Elo are interval aproximativ 95% [-0,003717; 0,053414],
care include zero. Amestecul selectat coincide cu Elo în acest experiment.
Datele fuseseră deja inspectate; evaluarea este exploratorie. Nu s-a promovat
automat nici Elo, nici calibrarea. O apropiere de piață nu dovedește profit.

## 5. Separarea surselor și evaluărilor

Sursele principale din snapshot au rezultate numai până la 1–2 noiembrie.
Cele patru scoruri OddsPapi mai recente sunt **numai pentru evaluarea
predicțiilor arhivate**, nu pentru antrenare, prospețime sau calibrare
retrospectivă. score_evidence.py controlează această separare.

Scorurile cer aceeași ligă/echipe/orientare, kickoff în 60 secunde, stare
explicit finală, final plauzibil și perioada fulltime la 90 minute; starea și
identitatea sunt reverificate. Nu substitui result, prelungiri sau chei
numerice nedocumentate. Patru din cinci meciuri au trecut; al cincilea rămâne
necorelat, iar proba incompletă. Nu forța aliasuri sau ore pentru a obține verde.

settlement.py păstrează dovezi și amprente; schemele 1/2 rămân citibile,
schema 3 include dovada externă completă. Identitățile noi sunt literale,
stabile la aliasuri viitoare. Sursele se selectează după ligă/tip.
Corecțiile sau două rezultate curente contradictorii exclud evaluările
afectate fără rescriere. Absența temporară a sursei păstrează dovada validă;
rezultatele arhivate nu pot fi reutilizate înainte de momentul observării.

The Odds API este UK/internațional. PropLine și proba OddsPapi nu confirmă
un feed complet RO; changedAt este schimbare de preț, nu dovadă a ultimei
livrări. Cotele brute ale furnizorilor nu se publică în dumpuri. Drepturile
surselor se clarifică înainte de folosire comercială.

## 6. Operare și teste

Un singur writer de producție: .github/workflows/valueradar.yml. Importul
și rapoartele recalculate folosesc o intrare principală capturată o singură
dată. Cercetarea separată produce artefacte, fără a scrie în main.

- Model: aproximativ la patru ore. Cote internaționale: două scanări/zi,
  în bugetul existent. Niciuna nu reprezintă oferte RO confirmate.
- PropLine RO: zilnic 06:37 UTC, 08:37 România iarna / 09:37 vara, maximum
  cinci cereri gratuite, numai agregate.
- Cercetare/scoruri: duminică 05:41 UTC, 07:41 România iarna / 08:41 vara.
  Scoruri: maximum cinci meciuri și 12 cereri din planul gratuit de 250,
  rezervă zece; maximum 60 programate într-o lună cu cinci duminici.
- Probele manuale sunt implicite false; nu face experimente repetate fără motiv.
- Publicarea verifică head-ul exact, timestamp și hash-uri pentru HTML,
  scripturi și rapoarte. Până la 18 verificări de propagare, apoi o singură
  republicare dacă este necesar, cu reverificarea main și control final
  obligatoriu. Nu reface importul și nu consumă credite de date pentru recuperare.
- Monitorul semnalează model >6 ore, probă RO >30 ore și cozi >48 ore după
  perioada minimă de completare. Nu trimite notificări externe.
- Istoric statistic >21 zile sau sursă curentă indisponibilă: comparația
  afectată este blocată. Jurnal/istoric corupt: nu se înlocuiește cu gol.

Verificări trecute: **207 teste Python, 68 Playwright desktop/mobil**, sintaxă,
actionlint, import real/contracte în CI și test al site-ului public cu 25
combinații ligă/piață pe fiecare dispozitiv. Testele dovedesc comportamentul
tehnic observat, nu profit sau absența tuturor bugurilor.

Comenzi uzuale sunt în README.md. Pentru schimbări rulează verificările
potrivite; nu reface API-uri autentificate doar pentru documentație sau
pentru repetarea unei verificări deja trecute. Nu publica work/, .env sau
dumpuri ale mediului. Preferă loturi coerente, nu multe merge-uri succesive.

## 7. Priorități la o cerere nouă

1. Citește rapoartele/producția actuală; păstrează dovezile și separarea
   versiunilor. Verifică apariția statisticilor și motivul meciului necorelat.
2. Continuă acumularea prospectivă și definirea criteriilor înaintea unor
   date noi. Patru meciuri nu validează calibrarea sau profitabilitatea.
3. Cote RO exacte și licențe: nicio substituire UK/RO, nicio acceptare din
   nume/booleeni, nicio cheltuială ori contact comercial neautorizat.
4. Evaluează incertitudinea și factori/modelări noi prin contribuție izolată,
   cronologie și test prospectiv; nu regla pe rezultatele finale deja văzute.
5. Menține value/ROI blocate până la dovezi complete. Nu inventa date,
   intervale de probabilitate, acoperire sau pariuri confirmate.
