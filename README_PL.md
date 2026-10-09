# 🏃 running-air — Optymalizator tras biegowych w Krakowie

> Automatyczny dobór najlepszej trasy do biegania w Krakowie na podstawie danych o jakości powietrza z czujników Airly i sieci dróg z OpenStreetMap.

---

## 📌 Co robi projekt

Każdego dnia potok danych:
1. **Pobiera pomiary jakości powietrza** (PM2.5, PM10, CAQI) z maksymalnie 80 czujników Airly w Krakowie przez API Airly.
2. **Archiwizuje dane** do dziennych plików CSV przechowywanych w repozytorium.
3. **Buduje graf chodników i ścieżek** dla północy i zachodu Krakowa z OpenStreetMap przy użyciu OSMnx.
4. **Interpoluje wartości PM2.5** na każdą krawędź grafu metodą Odwrotnych Odległości (IDW).
5. **Generuje trasy pętlowe** o długości 3, 5, 8 i 10 km i ocenia je według jakości powietrza, udziału zieleni i dokładności długości.
6. **Zapisuje interaktywną mapę HTML** i plik GPX dla najlepszej trasy każdej długości.

Cały potok uruchamia się automatycznie raz dziennie przez GitHub Actions.

---

## 🗺️ Przykładowy wynik

| Dystans | Długość | Śr. PM2.5 | Udział zieleni | Wynik |
|---------|---------|-----------|----------------|-------|
| 5 km | 4 805 m | 13,6 µg/m³ | 92,8 % | 0,881 |

*Punkt startowy: okolice Krowodrzy / Błoni (północny zachód Krakowa)*

---

## 🧠 Metoda

### Interpolacja jakości powietrza (IDW)
Czujniki Airly to pomiary punktowe. Aby oszacować jakość powietrza wzdłuż dowolnej trasy, potok używa **Odwrotnych Odległości (IDW)**: dla środka każdej krawędzi grafu PM2.5 jest szacowane jako ważona średnia k najbliższych czujników, gdzie wagi to odwrotność kwadratu odległości.

```
PM2.5(x) = Σ(wᵢ · PM2.5ᵢ) / Σwᵢ,   wᵢ = 1 / d(x, czujnikᵢ)²
```

### Scoring tras
Każda kandydująca pętla jest oceniana wzorem:

```
wynik = 0,60 × jakość_powietrza + 0,25 × udział_zieleni + 0,15 × dokładność_długości
```

gdzie `jakość_powietrza` jest znormalizowana odwrotnie do PM2.5 (niższe = lepszy wynik).

### Ograniczenia
- IDW to przybliżenie — rzeczywiste stężenie zanieczyszczeń na poziomie ulicy może różnić się od odczytu czujnika.
- Gęstość czujników w Krakowie jest wysoka (~100 w granicach miasta), ale niejednorodna.
- Graf obejmuje tylko północno-zachodni Kraków (promień 7 km od Krowodrzy).

---

## 🛠️ Technologie

| Warstwa | Narzędzia |
|---|---|
| Dane o powietrzu | [Airly API v2](https://developer.airly.org/) |
| Sieć dróg | [OSMnx](https://osmnx.readthedocs.io/) + OpenStreetMap |
| Interpolacja przestrzenna | SciPy (`cKDTree`), NumPy |
| Wyznaczanie tras | NetworkX (najkrótsza ścieżka z własnym kosztem krawędzi) |
| Wizualizacja | Folium (Leaflet.js) |
| Automatyzacja | GitHub Actions (cron, codziennie) |
| Przechowywanie danych | Pliki CSV (dzienne), GraphML |

---

## 📁 Struktura projektu

```
running-air/
├── src/
│   ├── ingest.py       # Klient API Airly, pobieranie i archiwizacja danych
│   ├── graph.py        # Pobieranie grafu OSM, adnotacja krawędzi IDW
│   ├── routes.py       # Generowanie pętli i scoring
│   ├── visualize.py    # Mapa Folium + eksport GPX
│   └── pipeline.py     # Główny punkt wejścia CLI
├── data/
│   ├── measurements/   # Dzienne archiwa CSV (RRRR-MM-DD.csv)
│   ├── selected.json   # Wybrany podzbiór czujników
│   └── krakow_graph.graphml
├── output/             # Wygenerowane mapy i pliki GPX
├── config.yaml         # Obszar, liczba czujników, budżet API
├── requirements.txt
└── .github/workflows/
    └── ingest.yml      # Codzienna automatyzacja
```

---

## 🚀 Uruchomienie lokalnie

### 1. Klonowanie i instalacja

```bash
git clone https://github.com/elphi97/running-air.git
cd running-air
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Ustaw klucz API Airly

```bash
export AIRLY_API_KEY="twój_klucz"   # Windows: $env:AIRLY_API_KEY="twój_klucz"
```

Darmowy klucz: [developer.airly.org](https://developer.airly.org/)

### 3. Pobierz graf OSM (jednorazowo)

```bash
python -m src.pipeline prepare
```

### 4. Pobierz dane z czujników

```bash
python -m src.ingest collect
```

### 5. Wygeneruj trasy i mapy

```bash
python -m src.pipeline run            # wszystkie dystanse: 3, 5, 8, 10 km
python -m src.pipeline run --km 5    # konkretny dystans
```

Otwórz `output/map_5.0km_RRRR-MM-DD.html` w przeglądarce.

---

## ⚙️ Konfiguracja GitHub Actions

1. Sforkuj lub sklonuj repozytorium.
2. Dodaj sekret: **Settings → Secrets → Actions → New repository secret**
   - Nazwa: `AIRLY_API_KEY`
3. Włącz uprawnienia zapisu: **Settings → Actions → General → Workflow permissions → Read and write**
4. Workflow uruchamia się automatycznie codziennie o 05:30 UTC.

---

## 📊 Uwagi o danych

- Darmowy plan Airly: **100 requestów / dobę**. Potok używa do 81 (1 odkrycie + 80 czujników).
- Każdy dzienny przebieg pobiera **bieżący odczyt + 24 h historii godzinowej** na czujnik, więc jeden przebieg dziennie wystarczy.
- Dane gromadzą się w `data/measurements/` — po kilku tygodniach można analizować dowolny miniony dzień bez dodatkowych requestów do API.

---

## 📄 Licencja

MIT — możesz swobodnie używać, modyfikować i rozpowszechniać.
