# Local Knot Labeling

Źródło danych:
- aplikacja zapisuje gotowe deski w `scany/<board_id>/stitched.bmp`

Przygotowanie zestawu do oznaczania:
```powershell
C:\Users\Oskar\Desktop\skaner\.venv\Scripts\python.exe scripts\prepare_local_stitched_dataset.py --clean --limit 300
```

Domyślny wynik:
- `D:\SpeedEyeWoodTraining\local_stitched_labeling`

Co trafia do środka:
- `images/` - obrazy `stitched.bmp` do ręcznego oznaczania
- `previews/` - aktualne `stitched_annotated.bmp`
- `ai_logs/` - aktualne `stitched_knots.json`
- `labels/` - puste pliki `.txt`
- `manifest.json` - lista wszystkich próbek

Dalszy plan:
1. Oznaczyć prawdziwe sęki na obrazach z `images/`.
2. Zapisać etykiety do `labels/`.
3. Zrobić konwersję tego zbioru do treningu YOLO.
