# Working Rules

## Rule 1
Chatten är inte source of truth. Repot är source of truth.

## Rule 2
Alla större arbetsblock ska uppdatera:
- current-state
- backlog
- handoff
- decisions vid arkitekturella ändringar

## Rule 3
Arbeta i vertical slices, inte planlös lagerutbyggnad.

## Rule 4
Ingen slice är klar utan:
- kod
- test eller verifierbar smoke-test
- docs update
- handoff update

## Rule 5
Befintlig arkitektur respekteras tills nytt beslut loggas.

## Rule 6
Backend stabiliseras före bred UI-expansion.

## Rule 7
Gamla docs är referensmaterial tills de migrerats, men nya docs/01-11 är styrande.

## Rule 8
En branch per slice eller feature.