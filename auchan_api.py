#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка чеков My Auchan в формат Shop2Cash.

Использует Token80 из ~/.config/auchan-purchases/session.json,
созданный скриптом AuchanReverseEngineering/auchan_purchases.py.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional
import requests

BASE = os.getenv("AUCHAN_LOYMAX_BASE", "https://mobile.auchan.ru/ecom").rstrip("/")
CONFIG = Path(os.getenv("AUCHAN_CONFIG_DIR") or
              (Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "auchan-purchases")).expanduser()
SESSION_FILE = CONFIG / "session.json"
TIMEOUT = 35

def load_token() -> str:
    if not SESSION_FILE.is_file():
        raise RuntimeError(
            f"Нет сохранённой авторизации: {SESSION_FILE}. "
            "Сначала выполните SMS-вход скриптом AuchanReverseEngineering/auchan_purchases.py."
        )
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Не удалось прочитать сессию Auchan: {exc}") from exc
    token = data.get("token80") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("В session.json отсутствует Token80. Повторите вход в Auchan.")
    return token

class AuchanClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MyAuchan/4.1.2",
            "Accept": "application/json",
            "X-Token-CMD": token,
            "Content-Type": "application/json",
        })

    def post_history(self, offset: int, limit: int, cheque_number: Optional[str] = None) -> dict:
        body = {
            "channel": "M",
            "pagination": {"offset": offset, "limit": min(limit, 10)},
            "filter": {"chequeNumber": cheque_number} if cheque_number else {"id": None},
        }
        try:
            response = self.session.post(
                f"{BASE}/lk/loyalty/history", json=body, timeout=TIMEOUT
            )
            if response.status_code == 401:
                raise RuntimeError("Token80 отклонён сервером (HTTP 401). Выполните повторный SMS-вход.")
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"Ошибка запроса истории Auchan: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Auchan вернул ответ, который не является JSON.") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Неожиданный формат ответа истории Auchan.")
        return data

def first(obj: dict, *keys):
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return None

def items_from(payload: Any) -> list[dict]:
    """Находит товарные позиции в DTO и вложенных ответах API."""
    if isinstance(payload, list):
        for entry in payload:
            found = items_from(entry)
            if found:
                return found
    elif isinstance(payload, dict):
        for key in ("products", "Products", "items", "Items", "basket", "Basket"):
            value = payload.get(key)
            if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
                if any(first(x, "name", "Name", "title", "Title") for x in value):
                    return value
        for value in payload.values():
            if isinstance(value, (dict, list)):
                found = items_from(value)
                if found:
                    return found
    return []

def normalize_item(item: dict) -> dict | None:
    name = first(item, "name", "Name", "title", "Title", "productName", "ProductName")
    if not name:
        return None
    quantity = first(item, "quantity", "Quantity", "count", "Count") or 1
    # In TransactionDetailsDto product.value is the line total.
    value = first(item, "value", "Value", "sum", "Sum", "total", "Total",
                  "totalValue", "TotalValue", "price", "Price")
    if value is None:
        return None
    return {
        "name": str(name).strip(),
        "quantity": quantity,
        "pricePromo": str(value),
        "priceRegular": str(value),
        "measure": first(item, "measure", "Measure", "unit", "Unit"),
        "article": first(item, "code", "Code", "article", "Article"),
    }

def unwrap_history(payload: dict) -> list[dict]:
    # Основной формат подтверждён исходным AuchanReverseEngineering:
    # {"data":{"items":[...]}}. Дополнительно принимаем варианты обёрток API.
    containers = [payload]
    for key in ("data", "Data", "result", "Result", "response", "Response"):
        value = payload.get(key)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in ("items", "Items", "transactions", "Transactions",
                    "purchases", "Purchases", "history", "History"):
            rows = container.get(key)
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]
    return []


def total_count(payload: dict):
    meta = payload.get("meta", payload.get("Meta", {}))
    pagination = meta.get("pagination", meta.get("Pagination", {})) if isinstance(meta, dict) else {}
    value = pagination.get("total", pagination.get("Total")) if isinstance(pagination, dict) else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def fetch_all(client: AuchanClient, limit: int) -> tuple[dict, list[dict]]:
    first_page = client.post_history(0, limit)
    rows = unwrap_history(first_page)
    total = total_count(first_page)
    offset = len(rows)
    for _ in range(1000):
        if not rows or (total is not None and len(rows) >= total):
            break
        page = client.post_history(offset, limit)
        batch = unwrap_history(page)
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        if total is None and len(batch) < min(limit, 10):
            break
        if total is None:
            total = total_count(page)
    return first_page, rows

def normalize_receipts(client: AuchanClient, rows: list[dict], fetch_details: bool) -> list[dict]:
    """Преобразует записи истории тем же способом, что и myauchan.

    Важные особенности API:
    - trnNo — отображаемый номер кассовой операции, а не transactionId.
    - order_details уже находится в записи истории; не нужно повторно
      запрашивать её через filter.chequeNumber=trnNo.
    - transactionId используется для устранения повторов истории.
    """
    receipts = []
    seen_transactions = set()
    used_check_numbers = set()

    for row in rows:
        # Поля и порядок чтения повторяют рабочий myauchan.
        number = first(row, "trnNo", "TrnNo", "transactionNumber",
                       "TransactionNumber", "chequeNumber", "ChequeNumber",
                       "number", "Number")
        till = first(row, "till", "Till")
        transaction_id = first(row, "transactionId", "TransactionId")
        created = first(row, "date", "Date", "created", "Created",
                        "dateCreate", "DateCreate")
        store = first(row, "locationName", "LocationName", "location", "Location",
                      "storeName", "StoreName")

        # transactionId — идентификатор записи. trnNo может повторяться
        # между кассами/датами и сам по себе не годится для дедупликации.
        if transaction_id not in (None, ""):
            identity = ("transactionId", str(transaction_id).strip())
        else:
            identity = (
                "fallback",
                str(number or "").strip(),
                str(till or "").strip(),
                str(created or "").strip(),
                str(store or "").strip(),
            )
        if identity in seen_transactions:
            continue
        seen_transactions.add(identity)

        # Номер для отображения сохраняем как в myauchan (trnNo).
        # Если такой номер уже встретился у другой транзакции, добавляем
        # transactionId, чтобы чеки не сливались в GnuCash.
        display_number = str(number or transaction_id or "").strip()
        if not display_number:
            continue
        check_number = display_number
        if check_number in used_check_numbers:
            suffix = str(transaction_id or f"{till}-{created}").strip()
            check_number = f"{display_number}-{suffix}"
        used_check_numbers.add(check_number)

        # myauchan печатает товары прямо из order_details в истории.
        # Не делаем запрос filter.chequeNumber с trnNo: он может вернуть
        # другую запись и привести к одинаковому составу разных чеков.
        order = first(row, "order_details", "OrderDetails", "orderDetails")
        candidates = items_from(order if order is not None else row)
        products = [normalized for item in candidates
                    if (normalized := normalize_item(item)) is not None]

        amount = first(row, "totalValue", "TotalValue", "amount", "Amount",
                       "sum", "Sum")
        receipts.append({
            "source": "AUCHAN",
            "checkNum": f"AUCHAN-{check_number}",
            "chequeNumber": display_number,
            "transactionId": transaction_id,
            "trnNo": number,
            "till": till,
            "created": created,
            "amountPromo": amount,
            "title": "АШАН",
            "nameTc": store or "АШАН",
            "store_address": first(row, "address", "Address",
                                   "locationAddress", "LocationAddress") or "",
            "items": products,
            "raw": row,
        })

        if not products:
            print(
                f"Предупреждение: в истории для чека {display_number} "
                "нет order_details/products; отдельный запрос по trnNo не выполнялся.",
                file=sys.stderr,
            )
    return receipts

def main():
    parser = argparse.ArgumentParser(description="Загрузка чеков АШАН для Shop2Cash/GnuCash")
    parser.add_argument("--all", action="store_true", help="загрузить всю историю (по умолчанию — также вся история)")
    parser.add_argument("--limit", type=int, default=10, help="размер страницы API, максимум 10")
    parser.add_argument("--no-details", action="store_true", help="не запрашивать отдельно детали каждого чека")
    parser.add_argument("--json", dest="json_path", help="сохранить чеки в JSON-файл")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10:
        parser.error("--limit должен быть в диапазоне 1..10")
    client = AuchanClient(load_token())
    history, rows = fetch_all(client, args.limit)
    api_total = total_count(history)
    if not rows:
        top_keys = ", ".join(map(str, history.keys()))
        data = history.get("data", history.get("Data", {}))
        data_keys = ", ".join(map(str, data.keys())) if isinstance(data, dict) else type(data).__name__
        raise RuntimeError(
            "API АШАН вернул пустой список записей. "
            f"meta.pagination.total={api_total!r}; "
            f"ключи ответа=[{top_keys}]; ключи data=[{data_keys}]. "
            "Сверьте ответ API с AuchanReverseEngineering."
        )
    receipts = normalize_receipts(client, rows, not args.no_details)
    if not receipts:
        sample_keys = ", ".join(map(str, rows[0].keys())) if rows else "нет записей"
        raise RuntimeError(
            "История АШАН получена, но не удалось извлечь номера чеков. "
            f"Поля первой записи: [{sample_keys}]."
        )
    output = {
        "source": "AUCHAN",
        "history_count": len(rows),
        "api_total": api_total,
        "receipts": receipts,
    }
    if args.json_path:
        path = Path(args.json_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        print(f"JSON сохранён: {path}", file=sys.stderr)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Получено чеков АШАН: {len(receipts)}", file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(2)
