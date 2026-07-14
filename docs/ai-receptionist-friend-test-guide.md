# Krowolf AI Receptionist — Guide för testanvändare

> **För dig som deltar i vårt interna test.**
> Tack för att du hjälper oss testa! Det här är en kort guide som förklarar
> vad som händer, vad vi testar och vad vi vill ha feedback på.

---

## Vad är Krowolf?

Krowolf är ett system som hjälper installations- och serviceföretag att hantera
inkommande mejl automatiskt.

När en kund skickar ett mejl om t.ex. en elbilsladdare, ett VVS-problem eller
ett snickeriarbete kan systemet:

- **Läsa och förstå mejlet** (vad kunden vill, vad som saknas)
- **Förbereda ett svarsutkast** med relevanta följdfrågor
- **Skapa ett ärende internt** och skicka det till rätt person

**Vi skickar aldrig ett mejl till kunden utan att en operatör godkänt det.**

---

## Vad testar vi just nu?

Vi testar **AI Receptionist MVP** — den grundläggande flödet:

1. Du skickar ett testmejl till oss
2. Systemet läser och klassificerar mejlet
3. Systemet föreslår ett svar
4. Vi (operatören) granskar och godkänner (eller avvisar) svaret
5. Om godkänt: svaret skickas tillbaka till dig i samma mejltråd

Det vi vill verifiera:
- Förstår systemet vad du menar?
- Ställer det rätt följdfrågor?
- Är tonläget naturligt och professionellt?
- Verkar svaret komma från en riktig servicefirma?

---

## Vad testar vi INTE just nu?

Det här är ett tidigt test. Följande är **inte aktiverat**:

- Automatisk bokning eller offert
- Integration med ekonomisystem (Fortnox, Visma)
- CRM-integration (Monday.com)
- SMS eller telefoni
- Automatiska uppföljningar utan godkännande

---

## Vad ska du göra?

**Skicka ett eller flera testmejl** med en av dessa typer av ärenden:

| Typ | Exempel |
|-----|---------|
| Ny installation — elbilsladdare | "Vill installera laddbox hemma i garaget" |
| Fel på befintlig laddbox | "Laddboxen blinkar rött och fungerar inte" |
| Batteri till solceller | "Vill lägga till batteri till våra befintliga solpaneler" |
| Solceller producerar dåligt | "Produktionen har sjunkit det senaste månaden" |
| VVS-läcka | "Det läcker under diskbänken" |
| Snickeri/bygg | "Vill bygga en altan och renovera ett sovrum" |

Skriv mejlen som du skulle skriva till ett riktigt företag.
Inkludera ditt namn i slutet (signatur) så att systemet kan hälsa dig rätt.

**Skicka till:** [e-postadress som operatören ger dig]

---

## Vad händer sen?

1. Systemet processar ditt mejl automatiskt (brukar ta under en minut)
2. En operatör granskar det föreslagna svaret
3. Om svaret ser bra ut godkänns det och du får det i mejltråden
4. Om svaret inte är bra avvisas det och vi noterar problemet

Du kan förvänta dig svar **inom ett par timmar** under testet (inte automatiskt direkt).

---

## Vad vill vi ha feedback på?

Efter att du fått svar, berätta gärna:

1. **Förstod systemet vad du frågade om?** (rätt ämne/tjänst)
2. **Hälsade det dig rätt?** (rätt namn, inte konstigt)
3. **Var följdfrågorna relevanta?** Frågar det om saker som verkligen behövs?
4. **Verkade svaret komma från ett seriöst företag?** Ton, språk, stil.
5. **Vad saknades eller var konstigt?**

Du behöver inte använda tekniska termer. Berätta bara vad du tyckte.

---

## Säkerhetsförväntningar

- **Vi delar inte dina testmejl med tredje part.**
- Testmejlen läses av ett AI-system och av en intern operatör.
- Du kan skriva fiktiva adresser och uppgifter — du behöver inte använda riktiga.
- Systemet skickar inget utan att vi godkänt det.
- Det här är ett test, inte en riktig tjänst. Vi lovar inte att åtgärda ärenden.

---

## Om något känns fel

Hör av dig direkt till oss om:
- Du inte fått något svar inom rimlig tid
- Svaret verkar helt fel (fel tjänst, fel namn, konstigt innehåll)
- Du är osäker på något

Vi vill veta om det inte fungerar — det är hela poängen med testet.

---

## Tack!

Din feedback hjälper oss göra AI Receptionist bättre.
Det vi bygger ska i slutändan spara tid för servicepersonal som annars sitter
och svarar på mejl manuellt varje dag.
