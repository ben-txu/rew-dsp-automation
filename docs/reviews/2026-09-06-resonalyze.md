# Resonalyze-Review, Stand 2026-09-06

Gegenstand: https://github.com/DIMOSUS/Resonalyze, Clone auf Commit `8514e7b`
(2026-09-05, "The energy onset is admitted from 30 dB of SNR (#181)").
366 Commits seit 2026-06-14, davon rund 120 seit dem 1. August. 333 C#-Dateien,
113k Zeilen, 3200 Tests, 400 kB Dokumentation (README, MANUAL, REFERENCE,
TODO, AGENTS, docs/agent).

Zweck dieses Dokuments: Was kann das Projekt REW_ATF_Script (Auto-EQ,
.pct6-Parser, Helix DSP Ultra XT) und dieses Repo (rew-dsp-automeasure) von
Resonalyze lernen. Es ist kein Feature-Vergleich. Der Zeitpunkt des letzten
Checks ist mir nicht bekannt; ich habe die Commits ab Juli vollständig
gesichtet und die Codebasis in ihrer heutigen Form gelesen.

Verifikationsgrad: [SELBST] habe ich im Clone selbst gelesen. [AGENT] stammt
aus drei Analyse-Agenten, die Code und Docs mit Dateipfad und Zeilennummer
zitiert haben; ich habe diese Stellen nicht alle nachgelesen. [FOLGERUNG] ist
meine Ableitung.

---

## 1. Befunde, die unseren verifizierten Stand berühren

### 1.1 ATF-Import: 30-Band-TSV mit Shelf und Allpass [SELBST]

`dsp/AudiotecFischerFormat.cs` implementiert REWs Export "Audiotec Fischer"
als Datei mit Kopfzeile `Audiotec_Fischer_Full_EQ_(30_bands)` und exakt 30
Zeilen (`Number Enabled Control Type Frequency(Hz) Gain(dB) Q Bandwidth(Hz)
TargetT60(ms)`). Typen: `PK`, `Modal` (als PK gelesen), `LS_Q`, `HS_Q`,
`AP1`, `AP2`, `None`. Der Dateikommentar sagt, das PC-Tool importiere diese
Datei in den EQ eines Kanals; die Zeilenformen folgen "REW's export byte for
byte, because that is the layout the PC-Tool is known to accept". Kein
Preamp-Slot; Weichen, Delay, Polarität, Phase bleiben außen vor.

Unser Stand (Skill, verifiziert): Datei-Import nur Festbreiten und nur PK;
Clipboard nur TSV mit PK, LS_Q, HS_Q. Das ist ein Widerspruch in zwei
Punkten: Datei statt Clipboard, und AP1/AP2 als importierbare Typen.
Mögliche Auflösungen: (a) unser "Clipboard-TSV" und deren "Datei" sind
derselbe Pfad und wir haben nur den Datei-Dialog nie mit diesem Format
probiert; (b) Resonalyze hat den Datei-Import nie selbst getestet und stützt
sich auf REW; (c) PC-Tool-Versionen unterscheiden sich.

Vorschlag: ein Verifikationsexperiment mit einer von Hand gebauten
30-Zeilen-Datei (ein PK, ein LS_Q, ein AP2), Import über den Datei-Dialog
auf einer Kopie, danach `.pct6` decodieren und die Slots lesen. Fällt der
Test positiv aus, fällt die Begründung "S1-Fitter PK-only, weil Datei-Import
kein Shelf kann". Die Typcodes 3/4 (Shelf) hätten dann auch einen
Schreibpfad ohne unseren Parser.

### 1.2 Helix-Phasensteuerung: gemessenes Modell [SELBST]

`dsp/PhaseRotationControl.cs`, gemessen auf einem DSP ULTRA S (Issue #88,
rund 60 elektrische Sweeps):

- Ein AP2 mit Q = 1,0 (auf sechs Kurven 1,0000), Magnitude flach auf 0,02 dB.
- Die Eckfrequenz wird so gelegt, dass die Phase **an der konfigurierten
  Trennfrequenz** dem eingestellten Winkel entspricht: Tiefpass auf
  Sub-Kanälen, Hochpass auf allen anderen. Passt auf 0,2 % (7961 Hz gemessen
  gegen 7977 Hz gelöst für 90° bei 5 kHz Referenz).
- Raster 5,625° (64 Schritte), Maximum 354,375°.
- Die Referenz ist die Weiche **wie konfiguriert**, auch bei Bypass oder
  Slope OFF.
- Corner-Cap bei 3/16 der Prozessorrate (18007–18011 Hz gemessen bei 96 kHz),
  undokumentiert. Bei einem Hochtöner mit 5 kHz Trennung sind die ersten
  fünf Rasterschritte derselbe Filter (mindestens ~29°).
- Kalkuliert an der Prozessorrate: 90° bei 5 kHz ist ein 7977-Hz-Corner auf
  96 kHz und 7674 Hz auf 48 kHz.
- Offen laut Datei: das 5,625°-Raster ist nur auf einem Sub-Kanal gemessen;
  ältere Tool-Generationen sollen Mid/High mit 11,25° rastern.

Für uns: Das ist der erste belastbare Fremdbefund zur Semantik einer
Phasen-Einstellung im Helix. Ob das `PM`-Attribut in unserem
`<T PM P T=Delay/>` diese Phase trägt, ist Spekulation und bleibt bis zum
Schreibtest gesperrt. Der Katalog in `dsp/DspProcessorProfile.cs` führt den
"NEXT DSP ULTRA XT" mit 96 kHz, RBJ-Q und Phasensteuerung; das ist die
Tabelle des Autors aus Herstellerangaben, nicht gemessen. Ein Delay-Limit
oder eine Delay-Auflösung für Helix ist **nicht** hinterlegt (jede Zeile
`MaxDelayMs = null`, Fallback 50 ms). Unsere offene Frage zur Delay-Einheit
im .pct6 bleibt also offen.

### 1.3 Q-Konvention [SELBST]

`dsp/PeqQConvention.cs`: Audiotec Fischer (HELIX/MATCH/BRAX) liest Q als
RBJ (BW = f0/Q, gainunabhängig). Quelle ist REWs Equaliser-Referenz, nicht
eine eigene Messung; nur AMP Panacea wurde von Resonalyze gemessen. Die
Umrechnung Symmetric/Classic ist `10^(±gain/40)` und nur bei tiefen Bändern
relevant (×1,19 bei 3 dB, ×2,37 bei 15 dB). Falls unser Fitter und der
Vorwärtsmodell-Beweis (0,0000 dB gegen REW) RBJ-Q voraussetzen, sind wir
konsistent mit dieser Annahme. Der Zwei-Band-Messtest aus der Datei (Fc 1
kHz, Q 4, +12 und −12 dB, Bandbreite an den ±6-dB-Punkten: RBJ ~250 Hz
beide, Symmetric ~499 Hz beide) ist billig und würde die Annahme für den
Ultra XT hart machen.

### 1.4 Spectrum vs. RTA: unabhängige Bestätigung [SELBST]

REFERENCE.md, Abschnitt Live Spectrum, "Slope compensation": "pink otherwise
falls 3 dB per octave on the per-bin dB axis, and on the banded dB SPL
display even flat white noise climbs 3 dB per octave, since a band's power
grows with its width." Das ist unser zentraler Modus/Ziel-Befund
(−10·log10(2) = −3,0103 dB/oct) in fremden Worten und unabhängig
hergeleitet. Nichts Neues, aber ein externer Anker.

### 1.5 REW-API: Befunde, die sich mit unseren decken oder sie erweitern [AGENT]

Resonalyze spricht REW nur an drei Endpunkten an (`GET version`,
`POST import/impulse-response-data`, `GET measurements`), gemessen gegen
5.40 Beta 132 / API 0.9.6. Daraus:

- **Busy-Sperre bestätigt.** Der Live-Test löscht mit bis zu vier Retries,
  weil "REW can still be finishing with a measurement it has already listed,
  and refuses the delete while it is". Deckt sich mit unserem OS2-5.
- **`GET /measurements` ist ein Objekt mit Index-Schlüsseln**, kein Array.
  Identifikation der eigenen Messung über neue UUID **und** Titel-Präfix,
  Polling 200 ms, Deadline 15 s, Mehrdeutigkeit wird gemeldet, nicht
  geraten.
- **Titel werden nach Anzeigebreite gekürzt, nicht nach Zeichenzahl**: 40
  Zeichen kamen ganz zurück, 47 als 45, 54 als 48, 64 als 45. Konsequenz für
  unser `name_template` und alle Titel-basierten Lookups: Diskriminator
  (Session, Datum) nach vorn, Gesamtlänge unter 40 Zeichen halten.
  `{session}_{channel}` ist unkritisch, solange die Session kurz bleibt.
- **`timeOfIRStartSeconds` ist REWs eigene Onset-Erkennung**, nicht die
  gesendete Startzeit; `timeOfIRPeakSeconds` trägt sie zurück. Relevant,
  sobald wir Sweep-Block-3-Daten per API auswerten.
- **Import-Gate 100 ms links vs. 125 ms bei nativen Sweeps**, und REW
  klemmt ein angefordertes Fenster still auf den vorhandenen Pre-Roll.
  Vergleiche Import gegen native Messung nur bei gleichem Fenster.
- `applyCal: true` beim Import wendet REWs geladene Mic-Kalibrierung auf
  Fremddaten an; `splOffset` weggelassen ergibt nicht "kein Offset", sondern
  REWs Default (~75 dB).
- **Pro-Lizenz:** Im Resonalyze-Code gibt es keine Pro-Sperre; Vorbedingung
  ist nur der eingeschaltete API-Server. Unser README sagt, POST-Endpunkte
  seien Pro-gated. Beides kann stimmen, wenn der Autor Pro hat; aus dem Code
  ist es nicht entscheidbar.
- REW liest aus dem Text-Export `IR is normalised`, `IR window applied`,
  `IR is min phase` als Ablehnungsgründe; `GET /impulse-response` liefert
  eine peak-normalisierte Kopie, `?normalised=false` die Rohwerte.
- Der Text-Export trägt den **Timing-Offset nicht** im Header (identischer
  Header mit und ohne Offset, Offset in die Startzeit gefaltet); die API
  liefert `timingOffset` direkt.

### 1.6 MMM-Rezept [SELBST]

Resonalyze pinnt in seinem MMM-Modus: periodisches Pink Noise mit Periode =
FFT-Länge (exakt 1/√f, leckfrei mit Rechteckfenster, Overlap aus),
unendliche Mittelung (exponentielle Mittelung gewichtet das Ende des
Mikrofonwegs), Bandpower-dB-Darstellung, Slope-Kompensation an, Glättung
aus, Sequenzlänge 65536 (0,73-Hz-Bins bei 48 kHz). Empfehlung im Manual: 30
Sekunden oder mehr in langsamen Kreisen etwa im Kopfradius, Mikro von hinten
in den Kopfbereich, Kapsel nach oben, Messender sitzt hinten.

Unser Skript setzt `"averaging": "Forever"` und `stopAt` auf eine Mittelungszahl
(`mac/dv_speaker_measure.py:773-777`); Fenster und Overlap bleiben
REW-Default. Das Averaging entspricht der Regel. Der Punkt "periodisches
Rauschen ohne Resampling in der Kette" steht bei uns schon im README. Neu
ist die Begründung, warum exponentielle Mittelung für MMM falsch wäre, und
die feste Fensterlänge als Teil des Rezepts.

---

## 2. Auto-EQ: was der Fitter dort anders macht [AGENT, Kernkonstanten in `dsp/EqAutoTuner.cs`]

Der Fitter ist gierig, kein globaler Optimierer: Band an der größten
Restabweichung, Gain auf 0,1 dB gerundet, Frequenz auf ganze Hz, Q aus einer
festen Leiter `0.5 0.7 1.0 1.4 2.0 2.8 4.0 5.6 8.0 10.0`, Abbruch bei
Residuum unter 0,5 dB. 256 log-verteilte Stützstellen, Fehler = mittleres
Fehlerquadrat ohne Frequenzgewichtung (durch das Log-Raster implizit gleich
pro Oktave). Kein Nachoptimieren gesetzter Bänder.

Übertragbar:

- **Cuts-only-Preamp:** `ceil(max(target − source))`, geklemmt auf ≤ 0, nicht
  der Mittelwert. Ausrichtung am Punkt, wo die Quelle am wenigsten über dem
  Ziel liegt, damit jedes Band schneidbar bleibt.
- **Übertiefungs-Strafe mit Freizone:** nur der eigene Beitrag eines Bandes
  unter das Ziel wird bestraft, 1 dB frei, Gewicht 25. Die Datei dokumentiert
  den Fehlversuch, die vorbestehende Tiefe zu bestrafen: "shredded a smooth
  response into a swarm of Q=10 slivers".
- **Q-Deckel 6 im Wizard** (Leiter endet bei 5,6), Begründung #138: ein an
  einer Mikrofonposition gelesener Peak kam als Q-10-Notch zurück, der nur
  diese Position korrigiert. Bei uns ist die Eingangskurve schon ein MMM,
  das Argument greift also schwächer; die Nähe-zur-Weiche-Regel (unten)
  bleibt.
- **Zielpegel-Plausibilität vor dem Fit** (`EqTargetLevelCheck.cs`): Median
  von Ziel minus Quelle im Fit-Fenster; über +3 dB oder unter −10 dB fragt
  das Tool nach. Billig und fängt den häufigsten Fehlerfall.
- **House-Curve-Semantik** (`ImportedTargetCurve.cs`): Textdatei mit
  `f dB`-Paaren, Duplikate gemittelt, bei 1 kHz verankert, log-f/dB linear
  interpoliert, **außerhalb des Bereichs werden Randwerte gehalten**, nie die
  Steigung extrapoliert. Kurven mit Korrektur-Metadaten werden als Ziel
  abgelehnt. Unsere `Schnorke House Curve.txt` endet bei 20500 Hz flach, das
  ist konsistent.
- **Filter an der Prozessorrate entwerfen, Fit auf der digitalen Biquad
  bewerten.** Gemessen (#126): Kette bei 48 kHz statt 96 kHz entworfen ergab
  0,96 dB RMS Fehler und +4,1 dB bei 19,9 kHz; richtig entworfen 0,000 dB.
  Ob `target_level_fit.py` Biquads bei 96 kHz entwirft oder analog rechnet,
  habe ich nicht geprüft; unser Vorwärtsmodell-Beweis gegen REW sagt nichts
  über das, was der Helix aus denselben Zahlen baut.
- **Fit-gegen-Render-Schleife verworfen** (#138): der ganze Unterschied
  zwischen versprochener und gerenderter Kurve war 0,13 dB RMS, eine
  Iteration holte 0,09 zurück, weitere oszillierten. Die Gesamtordnung
  "Filter zuerst, dann glätten, Kalibrierung zuletzt" hatte in der falschen
  Reihenfolge 3,06 dB Fehler bei psychoakustischer Glättung. Glättung und
  Filteraddition kommutieren nicht, wie bei uns bewiesen.
- **Shelf-Entscheid per Lookahead** (#142): ein Shelf wird nur genommen, wenn
  der komplette Restfit mit ihm besser endet als ohne (mindestens 0,01 dB
  RMS, oder er spart Slots). Vier billigere Regeln wurden gemessen und
  verworfen (Commit `66789fa`). Nur relevant, falls 1.1 den Shelf-Weg öffnet.

Zielkurve: Die Car-Presets sind seit #80 **kein Tilt mehr**, sondern flach
400 Hz–5 kHz, Bass-Shelf 100 Hz/0,9 oct mit +6/+9,2/+12 dB, Höhen-Shelf −3 dB
bei 10 kHz/0,7 oct. Begründung des Autors: ein durchgehender −1-dB/oct-Tilt
ab 200 Hz war "+2.5 dB hot at 200 Hz, where cabin boom lives, and 2 dB dark
at 8 kHz". Die Referenz ist eine im Test gepinnte Terzband-Tabelle ohne
Zitat. Das ist eine Autorenmeinung, kein Beleg; aber sie trifft Bens
Geschmacks-Tilt (−0,5 dB/oct ab 200 Hz) genau an der Stelle, wo er den
200-Hz-Bereich anhebt. Wert einer Probe: Tilt erst ab 400 Hz oder 1 kHz
beginnen lassen und hören.

Junction-Regel für PEQ (docs/agent/AGENT_GUIDE.md §3, seit #170): innerhalb
einer Oktave um eine aktive Trennfrequenz nur Q ≤ 2, es sei denn, das
Merkmal ist positionsstabil (zeigt sich in der Spatial-Average-Kurve
genauso wie in der Punktmessung). Und: "the spatial average proves a
feature's stability, not its origin." Für uns: MMM-Daten sind per
Konstruktion positionsstabil, aber narrow-Q nahe der Weiche dreht Phase im
Übergabebereich. Ein Q-Deckel im Fit-Korridor um die Trennfrequenzen wäre
eine kleine, gut begründbare Ergänzung.

---

## 3. Spatial Average [AGENT, `dsp/SpatialAverage.cs`]

- Mittelung als **Leistungsmittel** (`10·log10(Σ10^(L/10)/n)`), nicht in dB,
  nicht komplex. Begründung: ein Position in einem 25-dB-Notch zieht ein
  dB-Mittel so stark wie eine 25 dB zu laute Position. Und: ein
  positionsunabhängiger Filter faktorisiert aus dem Leistungsmittel heraus
  (`⟨|D·H|²⟩ = |D|²⟨|H|²⟩`), deshalb ist "Spatial Average + analytische Kette"
  eine exakte Vorhersage. REWs "RMS average" (bei uns belegt als
  `sqrt(Σ|H_i|²/n)`) ist dasselbe Mittel.
- Gemessen: dB-Mittelung liegt 1,2–1,6 dB **unter** dem MMM-Durchlauf.
- Array (7 Positionen) vs. MMM desselben Treibers: 0,7 dB RMS bei 1/6 oct,
  Streuung ist reines Sampling-Rauschen von n = 7.
- **Spread als Boost-Gate:** Auto Tune boostet nicht, wo die Positionen
  mehr als 20 dB auseinanderliegen. Der Median-Spread im Auto liegt bei
  11–12 dB über das ganze Band, p90 nahe 15 dB; ein Gate bei 10 oder 12 dB
  wäre "a boost ban wearing a threshold's clothes". Gelesen am ungeglätteten
  Spread. Wir haben keinen Spread, weil MMM einen Weg mittelt; der Befund
  ist trotzdem eine Warnung davor, aus MMM-Daten oberhalb der Modalregion
  Boosts abzuleiten.
- Pegelanker: ein gemeinsamer Offset für den ganzen Satz (Median über das
  20-dB-Arbeitsband unter dem Peak jedes Kanals, dann Median über Kanäle),
  nie ein Offset pro Kanal. Entspricht unserer Regel, dass relative Pegel
  zwischen Kanälen aus einer Session mit unverändertem Gain kommen müssen.

---

## 4. Zeitrichtigkeit, Weichen, Verifikation [AGENT]

Wir automatisieren keine Delays; das Dossier (`references/zeitrichtigkeit.md`)
sieht Laufzeitarbeit über PC-Tool und Messung. Was trotzdem trägt:

- **Reihenfolge des Manuals:** EQ vor Delay, Delay auf dem prozessierten
  System, nach jeder Weichen- oder Bank-Änderung Auto delay erneut.
  Begründung identisch mit unserem Dossier: Magnitude-EQ bewegt den
  Minimalphasen-Anteil mit. Neu formuliert als Diagnose-Regel: eine
  Junction mit schlechtem Sum Loss, bestem Extra-Delay nahe null und großem
  Phasen-RMS ist **kein** Delay-Problem; der Excess-Group-Delay-Verlauf
  (Group Delay minus Minimalphasen-Anteil, 1/12 oct, durch das Phasen-Gate
  am Arrival) entscheidet: flach = keine Excess-Dispersion, zwei flache
  Kurven auf verschiedenen Niveaus = Laufzeit, Schwingen im Junction-Band =
  Reflexion oder zweiter Pfad, "never a PEQ". Ein Feldlauf hatte die Regel
  vorher mit falschem Vorzeichen (schmale Bänder an einer Mid/Tweeter-
  Junction entfernt, Sum Loss wurde schlechter).
- **Sum-Loss-Metrik:** pro Bin `20·log10(|ΣH| / Σ|H|)`, log-frequent
  gemittelt, plus Dip-Strafe 0,5·(Dip − Mittel). Immer ≤ 0 dB. Als reine
  Verifikationszahl auf unseren Sweep-Messungen (Block 3, 23–32) ohne
  Automatisierung sofort nutzbar: Sum Loss vor/nach einem PC-Tool-Delay.
- **Fenster nach Band dimensionieren:** ~8,66 Perioden der unteren
  Bandkante (Herleitung aus der Breite des 1/6-oct-Minimum-Statistiks),
  geklemmt 4–350 ms, FFT 4× gepaddet nur für Abtastung. Bei 33–130 Hz sind
  das 262 ms, bei 750–3000 Hz 11,5 ms. Für die Auswahl der
  Sub/Satellit-Trennung nach minimalem max|GD| (Acta Acustica 2025 im
  Dossier) ist das der passende Fensterbegriff.
- **Widerlegtes, das wir nicht wiederholen sollten** (TODO.md, mit [✗]):
  Phasensteigungs-Prior für Delay (zweimal auf realen Messungen widerlegt);
  Sum Loss als Lobe-Wähler über ~1 kHz (0,04–0,05-dB-Ties zwischen Lobe und
  Halbperioden-Zwilling); Energie-Onsets über verschiedene Ketten hinweg
  (2,4 ms daneben bei einem BW36-Bandpass).
- **Energie-Onset für L/R unter 300 Hz** (#180/#181): laufende Energie der
  Bandhüllkurve erreicht 10 % der Energie bis 60 ms nach dem Peak, Samples
  30 dB unter dem Peak zählen null. Nur für die zwei Seiten **eines**
  Treiberpaars durch nahezu identische Ketten, beide Seiten ≥ 30 dB SNR.
  Feldfall: ein 7-ms-L/R-Split, den keine Kabine erzeugt, wurde 2,2 ms
  (Handtune 1,35). Möllers 35-µs-Schwelle aus dem Dossier macht L/R-
  Symmetrie zur teuersten Größe; dieser Schätzer ist das passende Werkzeug,
  falls wir je Sweep-Paare vergleichen.
- **Frontkette zuerst, andere Gruppen dagegen platzieren** (#150/#151,
  a39add2): Rear und Center werden nicht gesucht, sondern platziert, gegen
  **einen** Fronttreiber (der mit dem größten 1–4-kHz-Anteil), nicht gegen
  die Frontsumme. Fehler gegen Handtune 0,46 → 0,07 ms. Unser G31 hat Front
  3-Wege + Sub; falls Rear dazukommt, ist das die Architektur.
- **Kausalitätsprüfung der IR** (#146): Energie 100–600 ms **vor** dem
  Arrival gegen ±100 ms um den Arrival, zirkulär; ab −22 dB Hinweis (saubere
  Messungen −39 bis −47 dB, zwei kaputte −14 dB bei Kohärenz 0,9995). Meldet,
  verweigert nicht, und nennt keine Ursache. Fängt eine Loopback-Fehlroutung,
  die Kohärenz nicht sieht.

Auto-Crossover-Score (Konstanten in `dsp/CrossoverAutoSetup.cs`): RMS-
Flachheit der Summe, Dip-Strafe 0,5, Overlap-Strafe 0,6 dB/oct, Slope-
Abweichung von 24 dB/oct bestraft, Ohr-Gewicht 2–4 kHz, Sub-Übergabe nach
oben Richtung 80 Hz genudged, Mitten-Übergabe nach unten Richtung 250 Hz,
Group-Delay-Budget 10 ms pro Slope, Hochtöner-Hochpass so, dass Fs um 22 dB
gedämpft ist. Nachrangig, weil magnitude-only mit idealer Ausrichtung; die
Rangfolge wird danach mit dem echten Delay-Suchlauf nach erreichbarem
Junction-Loss neu sortiert. Das Manual selbst warnt, dass Auto crossover auf
einem fertigen Tune Slopes, Phase und Gains zurücksetzt.

---

## 5. Agent Bridge: Muster für unsere Chat/Code/QA-Übergaben [AGENT, docs/agent/]

Resonalyze übergibt den ganzen Tune per Clipboard an einen beliebigen
Chat-Assistenten und liest dessen Antwort als typisierte Operationen zurück,
ohne Netz, ohne API-Key. Für unsere Übergabepraxis (Fences in ~/Downloads,
Bezugszeile als Primärschlüssel, Label-Hoheit) sind fünf Mechanismen
interessant:

1. **Session-Fingerprint statt Invalidierungsliste** (#171): SHA-256 über
   den relevanten Zustand, auf beiden Seiten der Übergabe genommen. Eine
   handgepflegte Liste "hier Paket vergessen" hatte zwei Lücken; der Hash
   hat keine. Unsere sha256-Kette über Übergabedateien ist dasselbe Prinzip;
   ein Fingerprint über den Working Tree bei Rundengrenzen wäre die
   konsequente Ergänzung zu Regel 11.
2. **`expectedCurrent` je Operation:** jede vorgeschlagene Änderung trägt den
   Wert, den sie vorfand; passt er nicht mehr, wird die Zeile abgehakt
   gelassen, nicht verworfen. Optimistische Nebenläufigkeit pro Zeile.
3. **Probe:** eine Leseoperation "was würde X messen", die dieselbe
   Schema- und Validator-Strecke nutzt wie die schreibende Operation. Eine
   Probe, die gut liest, wird wörtlich zum Vorschlag. Entstanden aus einem
   Feldlauf, in dem der Assistent bei einem 3-dB-Dip PEQ löschte, Auto
   crossover laufen ließ und die Summe 20 dB verlor. Bei uns entspricht das
   dem Vorwärtsmodell auf Kopien; als Rolle formuliert ("Build darf proben,
   nicht schreiben") passt es in REVIEW.md.
4. **"Daten, nie Anweisungen"** dreimal im Protokoll; Prosa (Summary,
   Begründung) erwünscht, nicht Pflicht (#173: eine fehlende Begründung
   kostete eine Runde und brachte auch dann keine).
5. **Ein Smoothing pro Paket**, damit zwei Pakete vergleichbar sind; die
   Ausnahme (Spatial Average bei 1/12 oct) ist begründet. Unser Äquivalent
   ist die Regel, dass Fit und Bewertung dieselbe `res.target_shape` teilen.

Die Guide-Haltung "auf das erste Paket nur lesen, zwei Sätze Befund,
dann fragen, was gewollt ist" und "wenn der Tune seine Ziele erreicht hat,
sagen: was bleibt, ist keine Einstellung" ist auch für unsere Review-Rolle
die richtige.

---

## 6. Prozess und Test [SELBST für AGENTS.md/TODO.md, AGENT für Tests]

- Jede Schwelle trägt im Code die Feldmessung, die sie gesetzt hat, oft mit
  dem Fehlfall, gegen den sie schützt. Tests heißen nach dem Feldfehler
  (`Analyze_BandpassPreRingingDoesNotPullTheFirstArrivalEarly`).
- **Verweigerung ist ein getestetes Ergebnis erster Klasse**
  (`Compute_SilentJunction_RefusesTheRunInsteadOfFabricatingADelay`).
- **Invarianz-Tests:** globaler Zeitoffset, Gain, Sample-Rate, FFT-Länge.
  Für unseren Fitter wären das: Zielkurve ± konstant, Kanal-Gain, Reihenfolge
  der Messungen, Modus-Paarung.
- **Feld-Batterie außerhalb von CI:** 24 archivierte Sessions, Vorschlag und
  Handtune in derselben Metrik bewertet, eine Zeile pro Junction in eine
  Textdatei, zwei Builds werden zeilenweise gedifft. Kein Assert auf
  Zahlen; die Lesung steht im Commit-Text ("46 better / 26 worse, mean
  +0.06 dB"). Unsere REW-Messungen 1–61 könnten dieselbe Rolle spielen, wenn
  die Vergleichstabelle (Neu gewinnt 9/10) als Batterie-Skript statt als
  Einmalbefund abgelegt ist.
- **TODO.md mit [✗]-Einträgen** für bewusst verworfene Ideen, damit sie
  nicht erneut vorgeschlagen werden, mit Datum und Messung. Entspricht
  unserem "Verworfen"-Block im Skill; deren Form (Ursache, Zahl, Datum,
  "do not re-propose") ist strenger.
- AGENTS.md verlangt, dass eine Änderung erst fertig ist, wenn die Docs im
  selben Commit stimmen, und dass man alle drei Doc-Dateien nach den Begriffen
  greppt, die die Änderung obsolet macht: "a stale sentence is worse than a
  missing one". Passt zu unserer STATUS.md-Pflicht.
- Commits sind mit Claude Opus 5 co-authored, Reviews durch ein zweites
  Modell ("GPT review correction folded in"). Dieselbe Besetzungsregel wie
  unser QA-Grundsatz.

---

## 7. Was nicht übertragbar ist

- Kein `.pct6`/`.afpx`-Wissen im Repo; nichts für den Parser.
- Kein Delay-Limit, keine Delay-Auflösung für Helix; die 0,01-ms-Rasterung
  ist Resonalyzes UI-Annahme.
- Die Q-Konventions-Tabelle ist REWs Liste, für ATF nicht nachgemessen.
- Loopback-Pflicht und Sweep-Zentrik passen nicht zu unserer MMM-Pipeline;
  MMM ist dort ein Nebenmodus für den EQ, wie bei uns.
- Windows/WinForms/.NET, ASIO-Pflicht für Arrays.
- Die Titel-Kürzung, das Import-Gate und die `timeOfIRStart`-Falle sind auf
  Beta 132 / API 0.9.6 gemessen; wir stehen auf Beta 129 / 0.9.5. Verhalten
  kann abweichen.

---

## 8. Konkrete nächste Schritte (Vorschlag, priorisiert)

1. Verifikationsexperiment ATF-30-Band-Datei-Import mit LS_Q und AP2 (1.1).
   Kriterium vorab: Erscheint nach Import im decodierten .pct6 ein Slot mit
   T=3/4 bzw. einem bisher unbekannten Typcode und den gesetzten Werten,
   fällt "PK-only". Erscheint nichts oder nur PK, bleibt der Stand.
2. Prüfen, ob `target_level_fit.py` Biquads an 96 kHz entwirft oder analog
   bewertet (2, Rate). Kriterium: Vorwärtsmodell gegen eine bei 96 kHz
   digital gerechnete PK-Kaskade auf 0,01 dB im Kernband.
3. Q-Konventions-Messtest am Ultra XT (1.3), zwei Bänder, ein Sweep.
4. Zielpegel-Plausibilität (Median, +3/−10 dB) und Q-Deckel im Oktavfenster
   um Trennfrequenzen als Optionen in den Fitter (2).
5. Titel-Länge in `name_template` dokumentieren: unter 40 Zeichen,
   Diskriminator vorn (1.5).
6. Sum-Loss-Skript auf Block-3-Sweeps als Verifikationsmetrik für
   PC-Tool-Delays (4).
7. Geschmacks-Tilt-Startfrequenz als Hörprobe (2, Zielkurve).

---

## Was ich nicht verifizieren konnte

- Ob das PC-Tool die 30-Band-Datei tatsächlich per Datei-Dialog importiert
  und AP1/AP2 annimmt. Resonalyze beruft sich auf REW und "known to accept",
  ohne eigenen Testbeleg im Repo.
- Ob unsere REW-Version (Beta 129 / API 0.9.5) die auf Beta 132 gemessenen
  Verhaltensweisen (Titel-Kürzung, Import-Gate, `timeOfIRStart`) teilt.
- Ob das Pro-Gate für POST-Endpunkte besteht; der Resonalyze-Code hat keine
  Sperre, das beweist nichts über die Lizenzlage des Autors.
- Die Quelle der Terzband-Tabelle hinter den Car-Presets (#80); der Autor
  hat "published" selbst aus dem Kommentar gestrichen.
- Das 5,625°-Raster auf Mid/High-Kanälen (nur Sub gemessen).
- Alle mit [AGENT] markierten Zeilenangaben habe ich nicht selbst
  nachgelesen; die Agenten haben aus dem Clone zitiert, nicht aus dem
  Gedächtnis.
- Den Zeitpunkt des letzten Checks; die Deltas beziehen sich auf den
  gesamten Stand seit Juli.
