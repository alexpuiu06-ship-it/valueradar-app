# Protocol de cercetare — versiunea audit 2026-11-06

Protocol stabilit înaintea rulării noii comparații. Este o evaluare exploratorie
pe date publice deja disponibile, nu un test nou, independent de dezvoltare.
Rapoartele istorice din versiunile anterioare au fost deja consultate; folosirea
unui alt split nu transformă aceleași rezultate într-o dovadă prospectivă.

## Decizii fixe

- Modelul operațional rămâne Poisson `weighted_opponent_model_v1`, cu identități
  și date corectate. Corecțiile de date nu rescriu predicțiile arhivate.
- Comparăm Poisson, candidații Elo declarați în cod, amestecul Poisson–Elo și
  ajustarea temperaturii probabilităților. Grilele sunt fixe înaintea rulării.
- Toate ligile folosesc aceleași frontiere de **dată**. Nicio zi nu este
  împărțită între antrenare, selecție, calibrare și evaluarea finală.
- La fiecare predicție sunt eligibile doar rezultate din zile anterioare.
  Actualizarea Elo se face după întregul grup al zilei. Duplicatele și
  rezultatele viitoare nu sunt exemple noi.
- Parametrii sunt aleși pe validare; temperatura pe fereastra de calibrare;
  apoi se îngheață. Rezultatele finale nu aleg nici parametrii, nici grila.
- Raportăm log-loss, Brier (media pe cele trei clase), calibrare pe clase,
  numărul de partide, rezultatele pe ligă și intervale prin resampling al
  grupurilor de dată. Dependențele între echipe de-a lungul timpului rămân o
  limitare; intervalele nu sunt garanții asupra următorului meci.
- Consensul cotelor fără marjă este reper doar când există o fotografie
  completă, identificată și anterioară începerii aceleiași partide. În lipsa
  acestei baze istorice, scorul de piață este **indisponibil**, nu estimat din
  cotele actuale ori din rezultate.
- Nicio îmbunătățire retrospectivă nu promovează automat un model și nu
  deblochează semnale value. Sunt necesare observații prospective separate,
  cote RO exacte, reguli compatibile și incertitudine măsurată.

## Reproducere

Codul, grilele, limitele temporale și amprenta istoricului apar în rapoartele
JSON. Importul înregistrează URL, momentul citirii și SHA-256 al sursei.
Un hash identifică datele folosite; nu permite recuperarea unei versiuni
dispărute din upstream. Pentru reproducere identică păstrați separat intrările
descărcate și utilizați aceleași fișiere, fără un nou import de pe rețea.

Reluarea pe un upstream modificat este un experiment nou. Orice schimbare de
grilă după consultarea rezultatelor necesită o nouă versiune a protocolului și
un nou set prospectiv; nu se prezintă drept confirmare a acestei evaluări.
