# SPAR + X5 Club → GnuCash

Объединённый набор скриптов для загрузки истории покупок из:

- **SPAR** (myspar.ru)
- **X5 Club** (Пятёрочка / Перекрёсток)

и импорта чеков в GnuCash.

## Файлы

| Файл | Назначение |
|------|----------|
| `spar_api.py` | Клиент SPAR (логин, синхронизация покупок) |
| `spar_history.py` | Просмотр истории SPAR из локальной базы |
| `spar_export.py` | Экспорт SPAR в CSV/JSON |
| `x5_api.py` | Клиент X5 Club (загрузка истории чеков) |
| `gnucash_import.py` | GUI-импортёр чеков SPAR и X5 в GnuCash |

## Быстрый старт

### 1. SPAR

```bash
python spar_api.py login          # один раз, ввод телефона + OTP
python spar_api.py sync --json    # загрузка покупок
```

### 2. X5 Club

Нужны cookies из браузера (лучше Firefox → скопировать таблицу cookies для x5club.ru).

```bash
python x5_api.py --json
```

### 3. Импорт в GnuCash

```bash
python gnucash_import.py
```

В окне можно:
- Загрузить чеки из SPAR одной кнопкой
- Загрузить чеки из X5 Club другой кнопкой
- Или указать уже сохранённый JSON-файл
- Проверить и создать проводки в GnuCash

## Требования

- Python 3.9+
- `requests` (`pip install requests`)
- Tkinter (обычно уже есть в Python)

## Примечание

Это личный инструмент. Работает с неофициальными API / cookies. Используйте на свой страх и риск.
