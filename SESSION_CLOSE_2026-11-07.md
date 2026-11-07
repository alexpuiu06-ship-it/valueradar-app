# ValueRadar — închiderea sesiunii din 6–7 noiembrie 2026

**Stare:** dezvoltarea zilei este închisă; modificările tehnice sunt integrate
și publicate. Automatizările deja configurate continuă. Nu sunt necesare
chei noi, achiziții sau intervenții ale proprietarului pentru regimul actual.

Acest document este memoria de sesiune, păstrată în Git. Pentru reluare se
citește mai întâi [CODEX_HANDOFF.md](CODEX_HANDOFF.md). Prezentarea destinată
unui posibil asociat este [PROJECT_BRIEF_RO.md](PROJECT_BRIEF_RO.md), disponibilă
și ca [PDF](reports/ValueRadar_Prezentare_Asociat_2026-11-07.pdf).

## 1. Obiectivul și deciziile proprietarului

ValueRadar trebuie să compare estimări fotbalistice explicabile cu prețuri
reale, fără semnale false de profit. Domeniul vizat: Premier League, La Liga,
Serie A, Bundesliga, Ligue 1; 1X2, goluri, galbene, cornere și faulturi;
Superbet RO, Betano RO, Unibet RO, MrBit RO, NetBet RO și Casa Pariurilor RO.

Proprietarul a cerut implementare autonomă, audit, teste reale și lucrul pe
branch-uri separate. Deciziile tehnice obișnuite nu necesită reconfirmare.
Cheltuielile, autorizațiile și deciziile majore îi aparțin.

A fost discutată o alternativă de aproximativ £49/lună pentru două case și
au fost căutate opțiuni mai bune. Proprietarul a configurat cheile gratuite
PropLine și OddsPapi în GitHub Actions Secrets. **Decizia finală este să
rămânem momentan la monitorizarea gratuită.** Solicitarea comercială de demo
este pregătită, dar amânată și netrimisă. Nu s-a cumpărat un abonament nou.
Nu se contactează furnizori și nu se reia comercializarea fără o instrucțiune nouă.

## 2. Ce s-a implementat în întreaga sesiune

| Etapă | Rezultatul concret | Dovadă în GitHub |
|---|---|---|
| Audit și cercetare | Import validat, identități exacte, cronologie, formule explicate, comparație Poisson/Elo/calibrare, bariere pentru value și teste E2E | [PR #1](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/1) |
| Stabilitate operațională | Un singur writer, rapoarte coerente, refuzul unui main schimbat, controlul prospețimii | [PR #2](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/2) |
| Cronologia cotelor | Timestamp la primirea răspunsului; respingerea meciurilor începute între cerere și răspuns | [PR #3](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/3) |
| Pilot gratuit RO | Evaluare PropLine și alternative; pregătire fără achiziție | [PR #4](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/4) |
| Feeduri RO reale | Cheie PropLine testată, cinci ligi, aliasuri exacte, monitor zilnic agregat și UI | [PR #5](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/5) |
| Alternativă OddsPapi | Cont, cotă de cereri, competiții, piață și câte un meci/ligă verificate; lipsurile păstrate vizibile | [PR #6](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/6) |
| Regim financiar | Monitorizare gratuită; evaluare comercială amânată | [PR #7](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/7) |
| Istoric și decontare | Istoric RO pe 90 zile, cozi de rezultate/statistici, întârzieri, conflicte și dovezi | [PR #8](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/8) |
| Proveniența dovezilor | Surse selectate după ligă/tip; amprente ale identităților literale, stabile la aliasuri viitoare | [PR #9](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/9) |
| Etichetarea arhivei | Numărul de înregistrări nu mai sugerează că toate sunt eligibile prospectiv | [PR #10](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/10) |
| Scoruri finale gratuite | Patru meciuri validate pentru opt evaluări; dovadă completă, izolare față de antrenare, control săptămânal cu buget | [PR #11](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/11) |
| Livrare Pages | Detectarea fișierelor vechi, până la 18 verificări și o singură republicare; control final obligatoriu și reverificarea main | [PR #12](https://github.com/alexpuiu06-ship-it/valueradar-app/pull/12) |

Aceste 12 PR-uri sunt integrate. Pachetul de închidere adaugă documentația
de predare/prezentare și corectează două ore din textul raportului OddsPapi;
nu modifică formulele, sursele ori programările aplicației.

## 3. Fotografia verificată la închidere

Datele de mai jos aparțin analizei din **7 noiembrie 2026, 02:30:29 ora
României**, adică `2026-11-07T00:30:29.392508+00:00`. Sunt o fotografie,
nu valori permanente ale aplicației. Fusul folosit pentru comunicare este
`Europe/Bucharest`; în această dată diferența este UTC+2.

| Indicator | Valoare și interpretare |
|---|---|
| Aplicație | https://alexpuiu06-ship-it.github.io/valueradar-app/ |
| Codul ultimei execuții tehnice | `82d77af9fe4cc70effdcd2feb1c08008f6e715d9` |
| Commitul datelor publicate | `b1e07c0` — prefix; identificatorul complet se verifică în Git |
| Intrări citite | 20/20 resurse; două familii de surse, nu 20 furnizori independenți |
| Istoric pentru model | 3.935 meciuri; prospețimea diferă pe ligă/piață |
| Analize viitoare în snapshot | 197 meciuri |
| Jurnal | 2.010 estimări din 202 meciuri distincte; piețele și versiunile sunt înregistrări separate |
| Separarea versiunilor | 1.000 înregistrări legacy și 1.010 în versiunea curentă |
| Evaluări eligibile | 8: patru 1X2 și patru pentru goluri, din aceleași patru meciuri |
| Coada versiunii curente | 985 viitoare; 12 așteaptă statistici; 5 estimări ale unui meci așteaptă rezultat/corelare |
| Arhiva legacy | 880 viitoare; 95 fără oră exactă; 25 fără dovadă suficientă a creării înainte de start |
| Istoric agregat RO | Două probe reale; nu s-au inventat zile anterioare |
| Value confirmat / ROI | 0 selecții; ROI indisponibil |
| OddsPapi | 48/250 cereri folosite, 202 rămase, la proba din 02:18 ora României; nu este contor live |

Sursele principale de rezultate se opresc în această fotografie la 1–2
noiembrie. Cele patru scoruri suplimentare din 6 noiembrie sunt folosite
numai pentru evaluarea predicțiilor deja arhivate. **Nu au fost introduse
în cele 3.935 rânduri de antrenare ori în calibrarea retrospectivă.**

## 4. Verificări și incidente închise

- **207 teste Python și 68 teste Playwright** pe desktop/mobil, trecute.
- Sintaxă Python/JavaScript, actionlint și contractele JSON, trecute.
- Import real și calcule de cercetare în GitHub Actions, fără API de cote plătit.
- Păstrarea celor 2.000 înregistrări inițiale, plus adăugarea celor noi,
  verificată prin contractul jurnalului.
- Test public după ultima publicare: câte 25 combinații ligă/piață pe desktop
  și mobil, explicații, comparații manuale, cercetare și refresh; fără erori
  JavaScript, resurse lipsă sau depășire orizontală.
- Două probe autentice și o rulare de producție au calificat aceleași patru
  scoruri. Al cincilea meci nu a fost corelat neambiguu și rămâne respins.
- O publicare Pages a declarat succes, dar servea fotografia anterioară.
  Verificarea a detectat eșecul. Reluarea exclusivă a publicării a recuperat
  artefactul corect, fără alte cereri de date. Recuperarea este acum automatizată,
  limitată la o încercare și urmată de verificare obligatorie.
- Două rezultate curente contradictorii sunt tratate explicit ca un conflict,
  inclusiv pentru decontări deja arhivate; lipsa temporară a sursei rămâne un
  caz diferit. Nu se rescriu rezultatele originale.

Ultima execuție tehnică de producție verificată:
[42318609591](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42318609591).
Execuția cu scoruri reale și incidentul/recuperarea Pages:
[42317213394](https://github.com/alexpuiu06-ship-it/valueradar-app/actions/runs/42317213394).

## 5. Ce continuă automat

| Activitate | Program / plafon |
|---|---|
| Date și model | Aproximativ la patru ore, prin writer-ul unic |
| Cote internaționale | De două ori pe zi, în bugetul existent; nu sunt cote RO confirmate |
| Diagnostic PropLine RO | Zilnic 06:37 UTC; 08:37 România iarna / 09:37 vara; maximum cinci cereri gratuite |
| Cercetare și scoruri OddsPapi | Duminică 05:41 UTC; 07:41 România iarna / 08:41 vara |
| Scoruri OddsPapi | Maximum cinci meciuri și 12 cereri contorizate/rulare, plan gratuit de 250/lună, rezervă de zece; maximum 60 cereri programate într-o lună cu cinci duminici |

Programările GitHub Actions sunt aproximative și depind de serviciu/surse.
Nu există un agent de dezvoltare care continuă să codeze după închiderea
conversației. Continuă doar workflow-urile configurate. Probele manuale au
bugete proprii și nu trebuie lansate repetat fără un motiv concret.

## 6. Ce rămâne pentru sesiunea următoare

1. Verificarea rapoartelor noi și decontarea pe date reale; păstrarea carantinei
   pentru meciul necorelat și completarea statisticilor când apar în surse.
2. Acumularea unui eșantion prospectiv suficient, cu protocol stabilit înainte
   de evaluare; patru meciuri nu validează modelul.
3. Confirmarea ofertelor exacte RO: casă/jurisdicție, piață/linie, timestamp,
   disponibilitate și reguli de decontare. Monitorul gratuit nu dovedește
   acoperirea completă a celor șase case sau a tuturor piețelor.
4. Măsurarea incertitudinii și comparația cu piața pe aceleași meciuri și
   momente. Fără cote istorice potrivite, reperul de piață rămâne indisponibil.
5. Factori noi și modele alternative numai cu surse/licențe clare, test de
   contribuție separată și evaluare prospectivă. Niciun arbitru, accidentare
   sau avantaj tactic fictiv.
6. Înaintea unei utilizări comerciale, clarificarea drepturilor datelor
   existente și a ofertelor furnizorilor. Bugetul și orice contact comercial
   se redeschid numai la cererea proprietarului.

**Nu sunt deschise decizii care să împiedice închiderea zilei.** Nu se
deblochează value/ROI, nu se cumpără nimic și nu se schimbă modelul pe baza
acestui eșantion mic. Reluarea începe cu verificări, apoi cu o etapă limitată,
nu cu rescrierea aplicației ori a arhivei.
