# Acoperirea cotelor — verificare 6 noiembrie 2026

Pentru alternativele evaluate în plafonul de £49/lună și pilotul gratuit
Superbet RO/NetBet RO, consultați [PROVIDER_ALTERNATIVES.md](PROVIDER_ALTERNATIVES.md).
Tabelul de mai jos descrie integrarea The Odds API existentă; pilotul nou
nu este încă un feed de cote autentificat ori verificat.

Integrarea instalată folosește **The Odds API v4**, regiunea `uk`, piața `h2h`.
Lista publică a furnizorului identifică `betano_uk` drept Betano (UK),
`unibet_uk` în regiunea UK și `netbet_fr` în regiunea Franța. Aceste identificări
nu confirmă oferta, jurisdicția ori regulile versiunilor din România.

| Operator cerut | Feed exact RO demonstrat în integrare | Semnale value |
|---|---|---|
| Superbet RO | Nu | Blocate |
| Betano RO | Nu; Betano UK este altă ofertă | Blocate |
| Unibet RO | Nu; Unibet UK este altă ofertă | Blocate |
| MrBit RO | Nu | Blocate |
| NetBet RO | Nu; NetBet FR nu dovedește RO | Blocate |
| Casa Pariurilor | Nu | Blocate |

Absența confirmării nu afirmă că un furnizor nu ar putea oferi aceste date.
Paginile comerciale ale altor furnizori nu stabilesc drepturile de folosire,
prețul exact, întârzierea, acoperirea fiecărei piețe sau regulile de decontare.
Nu s-a cumpărat niciun serviciu, nu s-a accesat niciun cont de bookmaker și
nu s-a implementat scraping.

## Dovezi necesare pentru o integrare ulterioară

Oferta trebuie să identifice operatorul și jurisdicția RO, evenimentul exact,
ora UTC, piața, linia, selecția, moneda/costurile relevante, timestamp-ul
cotei și regulile de decontare (90 de minute, prelungiri, anulări, cartonașe).
Este necesar și dreptul de utilizare/publicare a datelor. Chiar și atunci,
modelul trebuie validat prospectiv înainte de orice semnal value.

Introducerea manuală a unei cote este doar o comparație aritmetică. Numele
casei ales de utilizator și câmpurile booleene dintr-un JSON nu sunt dovezi
independente de verificare.

## Surse consultate

- [Lista bookmakerilor și regiunilor The Odds API](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html)
- [Documentația oficială v4](https://the-odds-api.com/liveapi/guides/v4/)

Verificarea s-a făcut din documentație și din observațiile derivate existente,
fără interogări suplimentare cu cheia `ODDS_API_KEY` și fără consum API.
