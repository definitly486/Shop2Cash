# SPAR + X5 Club + АШАН → GnuCash

Объединённый набор скриптов для загрузки истории покупок из:

- **SPAR** (myspar.ru)
- **X5 Club** (Пятёрочка / Перекрёсток)
- **АШАН** (My Auchan / история покупок и детали чеков)

и импорта чеков в GnuCash.

## Файлы

| Файл | Назначение |
|------|----------|
| `spar_api.py` | Клиент SPAR (логин, синхронизация покупок) |
| `spar_history.py` | Просмотр истории SPAR из локальной базы |
| `spar_export.py` | Экспорт SPAR в CSV/JSON |
| `x5_api.py` | Клиент X5 Club (загрузка истории чеков) |
| `auchan_api.py` | Клиент АШАН (история и отдельная загрузка деталей чеков) |
| `gnucash_import.py` | GUI-импортёр чеков SPAR, X5 Club и АШАН в GnuCash |

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

### 3. АШАН

Сначала выполните SMS-вход существующим скриптом из `AuchanReverseEngineering` (он сохраняет Token80 в `~/.config/auchan-purchases/session.json`):

```bash
python /путь/к/auchan_purchases.py
```

Затем Shop2Cash использует эту сохранённую сессию, загружает историю и запрашивает подробности каждого чека:

```bash
python auchan_api.py --json auchan_receipts.json
```

Для АШАН не нужно повторно вводить пароль или SMS, пока сохранённый Token80 действителен. При HTTP 401 повторите SMS-вход исходным скриптом. Файл сессии не копируется в Shop2Cash.

### 4. Импорт в GnuCash

```bash
python gnucash_import.py
```

В окне можно:
- Загрузить чеки из SPAR одной кнопкой
- Загрузить чеки из X5 Club другой кнопкой
- Загрузить историю и детали чеков АШАН отдельной кнопкой
- Или указать уже сохранённый JSON-файл
- Проверить и создать проводки в GnuCash

## Требования

- Python 3.9+
- `requests` (`pip install requests`)
- Tkinter (обычно уже есть в Python)

## Примечание

Это личный инструмент. Работает с неофициальными API / cookies. Используйте на свой страх и риск.
