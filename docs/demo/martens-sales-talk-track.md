# Mårtens Demo — Säljmanus (svenska)

> **Avsedd läsare:** Mårten (säljare)
> **Syfte:** Demonstrera kundvärde utan att avslöja interna system eller
> lova funktioner som inte finns i produktion ännu.
> **Ton:** Äkta, kontrollerad, kundcentrerad.

---

## 2-minutersmanus

> *Använd detta för en första intro eller när kunden har lite tid.*

---

**Öppning:**
> "Jag ska visa er hur vi tar emot kundförfrågningar idag — och hur AI
> hjälper oss att svara snabbare och mer kontrollerat."

**Steg 1 — Gmail-inkorgen:**
> "Vi tar emot mejl precis som ni gör idag. Men istället för att läsa varje
> mejl manuellt, scannar AI-systemet inkorgen och förstår direkt vad varje
> kund vill ha."

*(Visa: POST /gmail/process-inbox → svar med klassificerade jobb)*

**Steg 2 — Klassificering och extraktion:**
> "Ser ni? Den här förfrågan är automatiskt klassificerad som ett lead — hög
> prioritet, elcentralbyte, från Sollentuna. Telefonnumret är extraherat.
> Det här tog AI:n en sekund."

*(Visa: jobblistan med klassificering och extraherade fält)*

**Steg 3 — Godkännandeflödet:**
> "Vi skickar ingenting automatiskt. Varje svar går igenom ett godkännande
> först. Här ser ni svarsutkastet — ni kan redigera det och sedan trycka
> godkänn. Eller avvisa om det inte stämmer."

*(Visa: pending approvals med svarsutkast)*

**Avslutning:**
> "Det handlar inte om att ta bort människor från processen. Det handlar om
> att AI tar hand om sortering, prioritering och svarsutkast — så att ni
> lägger er tid på rätt ärenden och skickar rätt budskap."

---

## 5-minutersmanus

> *Använd detta för en fullständig demo med tid för frågor.*

---

### Del 1 — Problemet vi löser (30 sek)

> "Vad händer idag när en kund mejlar in om en akut elcentral klockan 08 på
> måndag? Mejlet hamnar i inkorgen, någon ser det kanske efter lunch, svarar
> manuellt och hoppas att tonen stämmer. Ni tappar 4 timmar och kunden kanske
> har ringt konkurrenten."

> "Vi förändrar det."

---

### Del 2 — Gmail-flödet (1 min)

> "Vi synkroniserar mot er Gmail-inkorg — på begäran eller schemalagt.
> Ni behåller full kontroll: det händer ingenting automatiskt utan att ni
> bestämt det."

*(Visa: dry_run = true → scanned = 10, no jobs created)*

> "Vi kan köra ett preview-läge först. Precis som nu — 10 mejl scannades,
> vi ser vad som skulle hända. Ingen data ändrad."

*(Kör sedan utan dry_run)*

> "Nu skapar vi jobb för varje mejl. Ni ser klassificeringen direkt."

---

### Del 3 — Klassificering och extraktion (1 min)

> "Varje jobb har en typ: lead eller kundärende. En prioritet: kritisk,
> hög, medel, låg. Och extraherade fält: namn, telefon, ort, tjänsttyp."

> "Det här drar AI:n ut ur mejltexten — oavsett hur kunden formulerar sig.
> En kund skriver 'behöver hjälp idag!' och systemet förstår att det är
> brådskande."

*(Visa: Scenario 2 — Anna Lindqvist, Täby, kritisk prioritet)*

---

### Del 4 — Godkännandeflödet (1 min)

> "Nu är det viktiga: vi skickar ingenting utan ert godkännande."

> "Här är svarsutkastet för Annas akuta ärende. AI:n har skrivit ett förslag
> baserat på vad hon skrivit. Ni kan redigera det, ni kan avvisa det, ni kan
> godkänna det."

> "Ni är alltid den sista länken innan något skickas ut."

*(Visa: pending approvals → approval detail med draft_response)*

---

### Del 5 — Output till Google Sheets (30 sek)

> "För att ni enkelt ska kunna följa upp leads och ärenden — utan att behöva
> logga in i systemet hela dagen — skriver vi automatiskt till ett Google
> Sheet. Här ser ni leadet från Lars i Sollentuna, telefonnumret, tjänsten,
> prioriteten. Allt samlat på ett ställe."

*(Visa: demo-sheetet — Leads-fliken med ifyllda rader)*

> "Det här sheetet är isolerat — det är bara för er demo. Inga riktiga
> kunddata blandas in."

---

### Del 6 — Visma-koppling (30 sek)

> "När ett lead konverteras till kund — till exempel Lars i Sollentuna
> tackar ja till offerten — kan vi automatiskt skapa kundkortet och fakturan
> i Visma. Idag visar vi att kopplingen är aktiv. Inga produktionsposter
> skapas under demon, men infrastrukturen är på plats."

*(Visa: GET /integrations/visma/status → connected)*

---

### Avslutning — Vad detta ger er (30 sek)

> "Snabbare svar. Rätt prioritering. Inga mejl som glöms bort.
> Och ni bestämmer fortfarande varje svar."

> "Nästa steg är att vi sätter upp det för just er verksamhet — med era
> jobtyper, era integrationer, ert arbetsflöde."

---

## Hur du förklarar Gmail

> "Vi kopplar till er befintliga Gmail via Google OAuth — samma säkerhet
> som Gmail använder. Ni behöver inte byta e-postklient. Vi läser inkorgen
> med er tillåtelse, sorterar och klassificerar mejlen, och lägger ett
> svarsutkast i godkännandekön. Ingen automatisk avsändning."

> "Ni kontrollerar vilka mejl vi tittar på via en söklabel eller ett filter.
> Under demon använder vi etiketten `krowolf-demo` — så vi rör aldrig
> era riktiga kundmejl."

---

## Hur du förklarar Google Sheets för leads/support

> "Istället för att bygga en ny vy ni behöver lära er, skriver systemet
> till ett Google Sheet ni redan kan. Leads i en flik, supportärenden i en
> annan. Ni kan filtrera, sortera och följa upp precis som ni gör med
> vilken tabell som helst."

> "Sheetet är kopplat till just er — ingen annan ser era data."

> **Om de frågar om integration med Hubspot/Salesforce/etc:**
> "Det är något vi kan diskutera som nästa steg. Grundflödet fungerar
> via sheets idag — det är enkelt att köra med direkt."

---

## Hur du förklarar Visma sandbox

> "Vi har kopplat mot Visma-API:et. Idag visar vi att kopplingen fungerar
> och att systemet kan kommunicera med Visma. Under demon skapar vi inga
> riktiga poster — ingen kund, ingen faktura — utan det är ett 'klart att
> skjuta'-läge vi visar."

> "När ni är redo att köra skarpt, är det ett konfigurationssteg att slå på
> de Visma-åtgärderna."

---

## Hur du förklarar godkännandeflödet

> "Systemet genererar ett svarsutkast men skickar ingenting utan att ni
> trycker godkänn. Det är en medveten designprincip — AI:n är ert stöd,
> inte er representant."

> "Ni kan redigera utkastet, godkänna det, eller avvisa det. Inget lämnar
> systemet utan er åtgärd."

---

## Hur du förklarar säkerhet och kontroll

> "Inga kunddata lagras utanför er konfigurerade miljö. Systemet är
> hyresgästisolerat — om ni har en tenant så ser ni bara era egna jobb
> och godkännanden."

> "Vi loggar varje händelse med tidsstämpel och aktör. Ni kan alltid gå
> tillbaka och se vad som hände, vem som godkände vad, och när."

> "Vi kopplar aldrig in automatiska externa skrivningar — Visma, måndag,
> eller e-post — utan att ni explicit aktiverat det per jobtyp."

---

## Vad du inte ska lova ännu

| Funktion | Status |
|----------|--------|
| Automatisk Google Sheets-skrivning | Planerad — inte live ännu |
| Visma automatisk fakturahantering | Kopplingen finns — aktivering krävs per kund |
| Monday-integration | Tillgänglig men inte aktiverad i demo |
| Schemalagd automatisk inkorgsynk | Tekniskt klart — konfigureras per tenant |
| Kundportal / kundvy | Planerat — inte i scope för demo |
| Direkt integration med bokningssystem | Inte i scope |

> **Säg hellre:** "Det är något vi planerar — låt oss boka en uppföljning
> när ni är redo att testa det."

---

## Vanliga kundinvändningar och säkra svar

**"Vad händer om AI:n gissar fel?"**
> "Allt går igenom ett godkännande. Ni ser klassificeringen och kan
> korrigera den. Och med fler körningar lär sig systemet era specifika
> ärendetyper bättre."

**"Vi vill inte att AI ska skriva till kunder."**
> "Ni styr det. Systemet skickar ingenting utan ert godkännande. AI:n
> är ett verktyg för att spara tid på sortering och utkast — ni bestämmer
> vad som skickas."

**"Hur vet vi att inga data läcker?"**
> "Varje kund har en isolerad konfiguration — inga delade databaser.
> Vi loggar varje åtgärd. Vi skickar inga data till externa AI-leverantörer
> utan konfiguration och avtal."

**"Det verkar komplicerat att sätta upp."**
> "Vi hanterar driftsättningen. Det ni behöver göra är att godkänna
> Gmail-koppling och titta på hur jobb och godkännanden ser ut. Resten
> är konfiguration vi gör åt er."

**"Vi har redan ett CRM."**
> "Vi kan skriva till ert CRM via Sheets-export eller direkt API —
> det är ett bra nästa steg att diskutera. Grundflödet fungerar utan CRM."

**"Vad kostar det?"**
> "Det pratar vi om när vi vet exakt vilket flöde som passar er —
> det beror på volym, integrationer, och hur ni vill hantera godkännanden."
> *(Hänvisa till prisdiskussion utanför demo.)*

---

## Discoveryfråggor Mårten kan använda med kunder

1. "Hur många mejl tar ni emot från kunder en typisk måndag?"
2. "Hur lång tid tar det idag från att ett mejl kommer in tills det är besvarat?"
3. "Hur sorterar ni leads från supportärenden idag?"
4. "Händer det att mejl glöms bort eller faller mellan stolarna?"
5. "Hur mycket tid lägger ni på att skriva standardsvar?"
6. "Använder ni Visma / Fortnox idag — hur skapar ni kundkort och fakturor?"
7. "Vad skulle det betyda för er att svara på en akut förfrågan inom 5 minuter istället för 4 timmar?"
8. "Har ni en process för att följa upp leads som inte svarat?"
9. "Vilka system är ni mest beroende av idag — och vilka är ni minst nöjda med?"
10. "Om systemet kunde ta hand om 80 % av sorteringen och utkastskrivningen — vad skulle ni göra med den tiden?"
