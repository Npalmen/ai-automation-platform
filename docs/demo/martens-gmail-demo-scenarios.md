# Mårtens Demo — Gmail-scenarion (svenska)

> Förbered dessa e-post i Mårten's Gmail-konto under etiketten `krowolf-demo`.
> Alla avsändare är fiktiva. Inget riktigt kunddata används.
>
> **Query för demo-synk:** `label:krowolf-demo is:unread`
>
> Markera varje e-post som **oläst** och lägg till etiketten `krowolf-demo`
> innan du kör inbox-synken.

---

## Scenario 1 — Elcentralbyte

**Subject:** `Behöver byta elcentral — vad kostar det?`
**Sender placeholder:** `lars.eriksson.demo@example.com`
**Body:**
```
Hej,

Jag bor i en villa byggd på 70-talet och min elcentral är av äldre modell.
Jag har förstått att den kan vara en brandrisk och vill byta ut den snarast.

Kan ni ge mig en offert? Jag bor i Sollentuna och är tillgänglig nästan alla vardagar.

Med vänliga hälsningar,
Lars Eriksson
070-123 45 67
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `lead` |
| **Prioritet** | Hög (nämner risk + "snarast") |
| **Extraherade fält** | sender_name: Lars Eriksson, phone: 070-123 45 67, location: Sollentuna, service_type: elcentralbyte, property_type: villa |
| **Föreslagen nästa åtgärd** | Boka besiktning / skicka offertförfrågan |
| **Svarsutkastvinkel** | Bekräfta mottagning, erbjud telefontid eller platsbesök i Sollentuna |
| **Google Sheets-flik** | Leads |
| **Godkännande krävs** | Ja — för att skicka svar |

---

## Scenario 2 — Akut felsökning

**Subject:** `AKUT: ström borta i halva huset`
**Sender placeholder:** `anna.lindqvist.demo@example.com`
**Body:**
```
Hej!

Vi har precis fått ett säkringsavbrott och nu fungerar inga eluttag i halva huset.
Jag har provat att återställa propparna men det hjälper inte.

Vi har barn hemma och behöver hjälp idag om möjligt!

Anna Lindqvist
Täby, 076-987 65 43
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `customer_inquiry` |
| **Prioritet** | Kritisk (AKUT, barn hemma, idag) |
| **Extraherade fält** | sender_name: Anna Lindqvist, phone: 076-987 65 43, location: Täby, issue_type: strömbortfall/säkringsfel, urgency: omedelbart |
| **Föreslagen nästa åtgärd** | Eskalera till jourtekniker — ring tillbaka direkt |
| **Svarsutkastvinkel** | Vi hör av oss inom 30 min — ge kontaktnummer till jour |
| **Google Sheets-flik** | Support |
| **Godkännande krävs** | Ja — men prioritera snabb hantering |

---

## Scenario 3 — Laddbox hemma

**Subject:** `Installation av laddbox för elbil`
**Sender placeholder:** `mikael.svensson.demo@example.com`
**Body:**
```
Hej,

Jag köpte nyligen en Tesla Model 3 och vill installera en hemmaladdbox (11 kW)
i mitt garage. Garaget är fristående, ca 20 meter från huvudhuset.

Är det möjligt att ni kan titta på det? Gärna inom de närmaste veckorna.

Tack på förhand,
Mikael Svensson
Lidingö
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `lead` |
| **Prioritet** | Medel (inga brådskande signaler) |
| **Extraherade fält** | sender_name: Mikael Svensson, location: Lidingö, service_type: laddbox 11kW, property_detail: fristående garage 20m, vehicle: Tesla Model 3 |
| **Föreslagen nästa åtgärd** | Skicka offert, fråga om tillgänglighet för besiktning |
| **Svarsutkastvinkel** | Vi installerar laddboxar, kan boka besök — behöver uppgifter om befintlig säkring |
| **Google Sheets-flik** | Leads |
| **Godkännande krävs** | Ja |

---

## Scenario 4 — Solcellsservice

**Subject:** `Service på befintlig solcellsanläggning`
**Sender placeholder:** `britta.karlsson.demo@example.com`
**Body:**
```
Hej,

Vi installerade solceller för 3 år sedan (annan leverantör) och märker att
produktionen har minskat det senaste halvåret. Panelerna verkar rena men
invertern visar ett fel-LED.

Ni kanske kan komma och titta? Vi finns utanför Västerås.

Vänliga hälsningar,
Britta Karlsson
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `customer_inquiry` |
| **Prioritet** | Medel |
| **Extraherade fält** | sender_name: Britta Karlsson, location: Västerås, service_type: solcellsservice, issue_type: invert-fel/produktionsminskning, installation_age: 3 år |
| **Föreslagen nästa åtgärd** | Erbjud felsökning/servicebesök, fråga om invertermodell |
| **Svarsutkastvinkel** | Vi kan diagnostisera inverterfel — ber om modell och felkod |
| **Google Sheets-flik** | Support |
| **Godkännande krävs** | Ja |

---

## Scenario 5 — Batteri & växelriktare

**Subject:** `Fråga om batterilager till befintlig solcellsinstallation`
**Sender placeholder:** `per.olofsson.demo@example.com`
**Body:**
```
Hej,

Vi har en 10 kWp solcellsanläggning sedan 2022 och funderar på att
komplettera med ett batterilager (gärna 10-15 kWh) för att lagra
överskottsenergi.

Vad kostar det ungefär och hur lång är återbetalningstiden?

Med hälsningar,
Per Olofsson
Nacka
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `lead` |
| **Prioritet** | Medel |
| **Extraherade fält** | sender_name: Per Olofsson, location: Nacka, service_type: batterilager, capacity_wanted: 10-15 kWh, existing_installation: 10 kWp 2022 |
| **Föreslagen nästa åtgärd** | Skicka offert med ROI-kalkyl |
| **Svarsutkastvinkel** | Presentera tillgängliga batterilösningar och typisk payback-tid |
| **Google Sheets-flik** | Leads |
| **Godkännande krävs** | Ja |

---

## Scenario 6 — VVS/servicebegäran

**Subject:** `Vattenläcka under diskbänk — behöver rörmokarhjälp`
**Sender placeholder:** `helena.berg.demo@example.com`
**Body:**
```
Hej,

Jag har en vattenläcka under diskbänken i köket. Det droppar sakta och jag har
lagt en hink under men det behöver fixas snarast. Min man sa att ni kanske kan
hjälpa till med rörmokeri också?

Lägenheten ligger på Södermalm i Stockholm.

Helena Berg
070-555 11 22
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `customer_inquiry` |
| **Prioritet** | Hög (aktiv läcka) |
| **Extraherade fält** | sender_name: Helena Berg, phone: 070-555 11 22, location: Södermalm Stockholm, service_type: rörmokar/VVS, issue_type: vattenläcka diskbänk |
| **Föreslagen nästa åtgärd** | Bekräfta VVS-kapacitet, boka snabbt besök |
| **Svarsutkastvinkel** | Kan hjälpa med VVS — erbjud tid inom 1-2 dagar |
| **Google Sheets-flik** | Support |
| **Godkännande krävs** | Ja |

---

## Scenario 7 — Snickare/byggarbete

**Subject:** `Bygga förråd på tomten — offert önskas`
**Sender placeholder:** `thomas.lindqvist.demo@example.com`
**Body:**
```
Hej,

Vi funderar på att bygga ett 15 kvm friggebodsliknande förråd på vår tomt
i Huddinge. Vi vill ha det klart lagom till hösten.

Hanterar ni snickeriarbeten eller kan ni rekommendera någon?

Hälsningar,
Thomas Lindqvist
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `lead` |
| **Prioritet** | Låg-Medel (inte brådskande) |
| **Extraherade fält** | sender_name: Thomas Lindqvist, location: Huddinge, service_type: snickeri/byggarbete, project_size: 15 kvm förråd, deadline: höst |
| **Föreslagen nästa åtgärd** | Bekräfta om snickeri ingår i tjänster, erbjud hänvisning |
| **Svarsutkastvinkel** | Klargör tjänsteutbud, erbjud eventuell hänvisning till partner |
| **Google Sheets-flik** | Leads |
| **Godkännande krävs** | Ja |

---

## Scenario 8 — Otydlig uppföljning

**Subject:** `Re: Er offert från förra veckan`
**Sender placeholder:** `sofia.nystrom.demo@example.com`
**Body:**
```
Hej,

Jag mailade er förra veckan men har inte hört något.
Tänkte bara kolla läget.

/Sofia
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `customer_inquiry` |
| **Prioritet** | Medel (uppföljning — risk att tappa kund) |
| **Extraherade fält** | sender_name: Sofia Nyström, issue_type: uppföljning, original_inquiry: okänd (hänvisar till tidigare e-post) |
| **Föreslagen nästa åtgärd** | Sök efter tidigare e-post från Sofia, boka in återkoppling |
| **Svarsutkastvinkel** | Ber om ursäkt för dröjsmål, ber om mer info om ursprunglig förfrågan |
| **Google Sheets-flik** | Support |
| **Godkännande krävs** | Ja |

---

## Scenario 9 — Prisjägare / svag lead

**Subject:** `Vad tar ni betalt för att byta ett eluttag?`
**Sender placeholder:** `nils.johansson.demo@example.com`
**Body:**
```
Tja,

Vad kostar det att byta ett eluttag? Har fått pris från tre andra och
letar efter billigaste alternativet.

Nils
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `lead` |
| **Prioritet** | Låg (prisjägare, liten uppgift) |
| **Extraherade fält** | sender_name: Nils Johansson, service_type: eluttag-byte, lead_quality: låg (prisjakt) |
| **Föreslagen nästa åtgärd** | Svara med standardprislista, prioritera ej högt |
| **Svarsutkastvinkel** | Ge standardtaxa, lyft fram kvalitets- och trygghetsfaktorer |
| **Google Sheets-flik** | Leads |
| **Godkännande krävs** | Ja |

---

## Scenario 10 — Brådskande men ofullständig

**Subject:** `Behöver elektriker ASAP!!!`
**Sender placeholder:** `maria.gustafsson.demo@example.com`
**Body:**
```
Hej!!

Vi har ett problem med elen och behöver hjälp idag. Kan ni komma?

Maria
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `customer_inquiry` |
| **Prioritet** | Hög (brådskande signal) men oklar (saknar detaljer) |
| **Extraherade fält** | sender_name: Maria Gustafsson, urgency: omedelbart, issue_type: okänt elfel, missing_info: adress / kontaktnummer / problembeskrivning |
| **Föreslagen nästa åtgärd** | Kontakta Maria direkt för att få adress och feldetaljer |
| **Svarsutkastvinkel** | Snabbt svar: vi är redo att hjälpa — ge oss din adress och telefon |
| **Google Sheets-flik** | Support |
| **Godkännande krävs** | Ja — men snabbt |

---

## Scenario 11 — Återkommande kund, ny tjänst

**Subject:** `Vill lägga till solceller — vi är befintlig kund`
**Sender placeholder:** `erik.persson.demo@example.com`
**Body:**
```
Hej,

Ni installerade vår laddbox för två år sedan (jättebra service!).
Nu funderar vi på att komplettera med solceller, ca 8-10 kWp.

Vilka tider har ni ledigt för ett hembesök?

Erik Persson
Danderyd, 073-222 33 44
```

| Fält | Förväntat värde |
|------|----------------|
| **Klassificering** | `lead` |
| **Prioritet** | Hög (befintlig nöjd kund — hög konverteringschans) |
| **Extraherade fält** | sender_name: Erik Persson, phone: 073-222 33 44, location: Danderyd, service_type: solceller 8-10 kWp, is_existing_customer: ja |
| **Föreslagen nästa åtgärd** | Prioritera — boka hembesök direkt |
| **Svarsutkastvinkel** | Välkommen tillbaka! Bekräfta intresse och erbjud nära tider för besök |
| **Google Sheets-flik** | Leads |
| **Godkännande krävs** | Ja |

---

## Förberedelse-checklista för demo-e-post

1. [ ] Logga in på Mårten's demo Gmail-konto
2. [ ] Skapa etiketten `krowolf-demo` om den inte finns
3. [ ] Skicka eller importera alla 10-11 scenarier som separata e-post (från fiktiva avsändare)
4. [ ] Applicera etiketten `krowolf-demo` på varje e-post
5. [ ] Markera varje e-post som **oläst**
6. [ ] Verifiera med dry_run:
   ```bash
   curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
     -H "X-API-Key: DEMO_TENANT_KEY" \
     -H "Content-Type: application/json" \
     -d '{"max_results":15,"dry_run":true,"query":"label:krowolf-demo is:unread"}'
   # Förväntat: scanned = antal förberedda e-post, inga jobb skapas
   ```
7. [ ] Kontrollera att inga riktiga kundmeddelanden har etiketten `krowolf-demo`

---

## Varning

> **Inga av ovanstående avsändare är riktiga personer.**
> Alla e-postadresser är `@example.com` — de ska aldrig skickas till riktiga mottagare.
> Lägg till etiketten manuellt i Gmail — skicka inte ut e-post externt för demo-scenarierna.
