## Stan projektu - 2026-08-13

### Struktura
- Projekt zostal rozdzielony na moduly.
- `main.py` uruchamia aplikacje.
- `main_window.py` sklada glowne okno.
- `tabs/` trzyma osobne zakladki:
  - `view_tab.py`
  - `settings_tab.py`
  - `manual_tab.py`
- `widgets/status_indicator.py` trzyma widget statusu.
- `helpers/app_settings.py` obsluguje trwale ustawienia przez `QSettings`.
- `workers/tcp_server_worker.py` trzyma worker lokalnego serwera TCP.

### UI / Podglad
- `status_layout` jest po prawej stronie gornego panelu.
- Nazwa i status w `StatusIndicator` sa blizej siebie.
- Teksty `QLabel` nie maja niepotrzebnego tla.
- Przycisk `Uruchom skaner` zmienia kolor na czerwony po uruchomieniu.

### Zakladka Ustawienia
- Ustawienia sa zapisywane trwale przez `QSettings`.
- Sekcja jest podzielona na 3 osobne panele:
  - `Ustawienia komunikacji PLC`
  - `Ustawienia modelu AI`
  - `Ustawienia kamery`
- `TCP PLC adress` i port sa pokazane w jednym wierszu jako `adres : port`, ale dalej zapisuja sie osobno.
- `Prog wykrywania sekow` jest sliderem od `0.00` do `1.00`.
- Tlo za sliderem zostalo usuniete.
- Ustawienia kamery:
  - `Ekspozycja`
  - `Gain`
  - `Jasnosc`
- Pola kamery sa typu spinbox bez strzalek.
- Jednostki sa w samych wartosciach pol:
  - `ms`
  - `%`
- Kursor w polach z jednostka jest cofany przed suffix, zeby dalo sie normalnie wpisywac liczby.

### TCP / Skaner
- Po kliknieciu `Uruchom skaner` aplikacja tworzy lokalny serwer TCP.
- Serwer nasluchuje lokalnie na `0.0.0.0:<port z ustawien>`.
- Adres PLC z ustawien nie sluzy do `bind`, tylko do filtrowania dozwolonego klienta.
- Polaczenie przyjmowane jest tylko od IP PLC wpisanego w ustawieniach.
- Logika start/stop siedzi w `tabs/view_tab.py`.
- Worker TCP siedzi w `workers/tcp_server_worker.py`.

### Porzucone
- Pomysl z ekranowa klawiatura zostal usuniety z projektu.

### Dobry nastepny krok
- Dodac konkretne komendy/protokol wymiany z PLC po odebraniu polaczenia.

## Snapshot - 2026-08-19 17:31:01

### UI / Sterowanie
- `tabs/view_tab.py` ma osobne przyciski:
  - `Polacz z PLC`
  - `Polacz z kamera`
  - `Uruchom skaner`
- `Uruchom skaner` steruje tylko stanem skanera, a nie zestawianiem polaczen.
- Podglad pokazuje ostatni `stitched.bmp` obrocony o `90` stopni w prawo.
- Obraz w podgladzie jest skalowany do widgetu i nie powinien rozpychac aplikacji.

### Stitching
- Stitching dziala w osobnym workerze: `workers/stitch_worker.py`.
- Aktualna logika stitchingu:
  - najpierw pelne doklejanie wszystkich zrodlowych `bmp`
  - dopiero potem jeden finalny crop calego obrazu
- Wynik jest zapisywany jako `stitched.bmp`, nie `png`.
- W `tabs/manual_tab.py` jest przycisk `Przestitchuj ostatnia deske`.

### Crop / Strojenie
- W `tabs/settings_tab.py` sa suwaki do strojenia cropu:
  - `Margines X crop klatki`
  - `Margines Y crop klatki`
  - `Margines X crop final`
  - `Prog wykrycia deski`
  - `Max przesuniecie X deski`
- Tytuly tych parametrow maja tooltipy z opisem.
- Crop byl przenoszony z pre-cropu klatek na finalny crop calego stitched obrazu.

### Przypisywanie zdjec do desek
- Aktualna logika paczek w `tabs/view_tab.py` jest FIFO:
  - `image_saved` dopisuje sciezke do `pending_image_paths`
  - ramka TCP z `photo_count` dopisuje paczke do `pending_board_batches`
  - gdy liczba zapisanych zdjec osiagnie `photo_count`, pierwsze `N` zdjec z kolejki trafia do folderu deski
- Nie ma juz skanowania calego katalogu `scany` po `mtime`.

### Stan roboczy
- Ten stan zostal uznany za dobry punkt odniesienia do ewentualnego powrotu.
