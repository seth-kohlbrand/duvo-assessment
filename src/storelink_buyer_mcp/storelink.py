"""StoreLink API client layer — the only code that talks to StoreLink.

``StoreLinkClient`` mirrors the real ``/v1`` endpoints, sends the
per-store ``X-Korral-Store-Key`` on every request, and handles the
weekly key rotation: if StoreLink rejects a key mid-flight, the client
re-reads the key from its source and retries exactly once. If the source
still holds the rejected key, the call fails with an actionable error.

``StubTransport`` is the in-memory stand-in for the real HTTP transport.
The real transport would be a thin httpx wrapper with the same
``request(method, path, key, params, body, idempotency_key)`` contract,
so swapping it in touches nothing above this layer.
"""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .credentials import StoreKeyProvider, key_fingerprint


class StoreLinkError(Exception):
    """Base for errors returned by StoreLink."""


class StoreLinkAuthError(StoreLinkError):
    """StoreLink rejected the presented store key (HTTP 401)."""


class StoreLinkNotFoundError(StoreLinkError):
    """StoreLink has no such resource (HTTP 404)."""


class _StubKeyProvider:
    """Reads the stub's current keys on every call, including rotations."""

    def __init__(self, transport: Any):
        self.transport = transport

    def get_key(self, store_id: int) -> str:
        try:
            return self.transport.keys[store_id]
        except KeyError:
            from .credentials import MissingStoreCredentialError
            raise MissingStoreCredentialError(store_id, self.available_store_ids()) from None

    def available_store_ids(self) -> list[int]:
        return sorted(self.transport.keys)


class StoreLinkClient:
    def __init__(
        self,
        transport: "StubTransport | None" = None,
        keys: StoreKeyProvider | None = None,
        trace: Callable[..., None] | None = None,
    ):
        transport = transport or StubTransport()
        keys = keys or _StubKeyProvider(transport)
        self._transport = transport
        self._keys = keys
        self._trace = trace or (lambda event, **fields: None)
        self._categories = {"beverages": {"id": "beverages", "name": "Beverages"}}
        self._products = {
            "coffee-1kg": {
                "id": "coffee-1kg", "name": "House Coffee 1kg", "category_id": "beverages",
                "supplier_id": "northstar", "on_hand": 8, "on_order": 0,
                "units_sold_28d": 56, "unit_cost": 12.50, "lead_time_days": 7,
            },
            "tea-100": {
                "id": "tea-100", "name": "Breakfast Tea 100ct", "category_id": "beverages",
                "supplier_id": "northstar", "on_hand": 40, "on_order": 0,
                "units_sold_28d": 28, "unit_cost": 8.00, "lead_time_days": 7,
            },
        }
        self._category_orders: dict[str, dict[str, Any]] = {}
        self._category_idempotency: dict[str, list[str]] = {}

    def credentialed_store_ids(self) -> list[int]:
        return self._keys.available_store_ids()

    # -- endpoints ---------------------------------------------------------

    def get_store(self, store_id: int) -> dict[str, Any]:
        return self._request(store_id, "GET", f"/v1/stores/{store_id}")

    def get_inventory(self, store_id: int, sku: str) -> dict[str, Any]:
        return self._request(
            store_id, "GET", f"/v1/stores/{store_id}/inventory", params={"sku": sku}
        )

    def get_pos_transactions(self, store_id: int, sku: str, since: str) -> list[dict[str, Any]]:
        return self._request(
            store_id, "GET", f"/v1/stores/{store_id}/pos",
            params={"sku": sku, "since": since},
        )

    def create_replenishment_order(
        self, store_id: int, sku: str, quantity_units: int, reason: str, idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            store_id, "POST", f"/v1/stores/{store_id}/replenishment",
            body={"sku": sku, "quantity_units": quantity_units, "reason": reason},
            idempotency_key=idempotency_key,
        )

    def get_replenishment_order(self, store_id: int, order_id: str) -> dict[str, Any]:
        return self._request(
            store_id, "GET", f"/v1/stores/{store_id}/replenishment/{order_id}"
        )

    def get_sku(self, sku: str, auth_store_id: int) -> dict[str, Any]:
        return self._request(auth_store_id, "GET", f"/v1/skus/{sku}")

    def get_supplier(self, supplier_id: str, auth_store_id: int) -> dict[str, Any]:
        return self._request(auth_store_id, "GET", f"/v1/suppliers/{supplier_id}")

    # -- task-oriented facade used by the service -------------------------

    def get_store_stock(self, sku: str, store_id: int) -> dict[str, Any] | None:
        try:
            product = self.get_sku(sku, store_id)
            inventory = self.get_inventory(store_id, sku)
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            transactions = self.get_pos_transactions(store_id, sku, since)
        except StoreLinkNotFoundError:
            return None
        return {
            "sku": sku, "product_name": product["name"], "store_id": store_id,
            "on_hand_units": inventory["on_hand_units"],
            "pos_units_last_24h": sum(transaction["units"] for transaction in transactions),
        }

    def create_store_replenishment_orders(
        self, sku: str, orders: list[dict[str, int]], idempotency_key: str
    ) -> tuple[list[dict[str, Any]], bool]:
        created = []
        duplicate_flags = []
        for order in orders:
            value = self.create_replenishment_order(
                order["store_id"], sku, order["quantity_units"],
                "24-hour POS minus on-hand exceeded 6 units", idempotency_key,
            )
            created.append({
                "replenishment_order_id": value["order_id"], "sku": value["sku"],
                "store_id": value["store_id"], "quantity_units": value["quantity_units"],
                "status": value["status"], "submitted_on": value["created_at"][:10],
            })
            duplicate_flags.append(value["duplicate_request"])
        return created, bool(created) and all(duplicate_flags)

    def list_categories(self) -> list[dict[str, Any]]:
        return deepcopy(list(self._categories.values()))

    def get_category(self, category_id: str) -> dict[str, Any] | None:
        return deepcopy(self._categories.get(category_id))

    def list_products(self, category_id: str) -> list[dict[str, Any]]:
        return deepcopy([p for p in self._products.values() if p["category_id"] == category_id])

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        return deepcopy(self._products.get(product_id))

    def create_purchase_orders(
        self, orders: list[dict[str, Any]], idempotency_key: str
    ) -> tuple[list[dict[str, Any]], bool]:
        previous_ids = self._category_idempotency.get(idempotency_key)
        if previous_ids is not None:
            return deepcopy([self._category_orders[value] for value in previous_ids]), True
        created = []
        for order in orders:
            order_id = f"PO-{len(self._category_orders) + 1:04d}"
            value = {"purchase_order_id": order_id, "supplier_id": order["supplier_id"],
                     "status": "submitted", "lines": deepcopy(order["lines"])}
            self._category_orders[order_id] = value
            created.append(value)
        self._category_idempotency[idempotency_key] = [value["purchase_order_id"] for value in created]
        return deepcopy(created), False

    def get_purchase_order(self, purchase_order_id: str) -> dict[str, Any] | None:
        return deepcopy(self._category_orders.get(purchase_order_id))

    # -- transport with auth handling --------------------------------------

    def _request(
        self,
        auth_store_id: int,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        key = self._keys.get_key(auth_store_id)
        started = time.monotonic()

        def send(current_key: str, retried: bool) -> Any:
            result = self._transport.request(
                method, path, key=current_key, params=params,
                body=body, idempotency_key=idempotency_key,
            )
            self._trace(
                "storelink_request", method=method, path=path,
                auth_store_id=auth_store_id, status="ok", retried_after_rotation=retried,
                key_fingerprint=key_fingerprint(current_key),
                duration_ms=round((time.monotonic() - started) * 1000, 1),
            )
            return result

        try:
            return send(key, retried=False)
        except StoreLinkAuthError:
            self._trace(
                "storelink_request", method=method, path=path,
                auth_store_id=auth_store_id, status="auth_rejected",
                key_fingerprint=key_fingerprint(key),
                duration_ms=round((time.monotonic() - started) * 1000, 1),
            )
            # The weekly rotation may have landed mid-flight. Re-read the
            # key from its source and retry once with the fresh value.
            fresh_key = self._keys.get_key(auth_store_id)
            if fresh_key != key:
                return send(fresh_key, retried=True)
            raise StoreLinkAuthError(
                f"StoreLink rejected the key for store {auth_store_id}, and the key "
                "in the secret source is unchanged after a fresh read. The weekly "
                "rotation has likely happened in StoreLink but not yet in the secret "
                "source. Nothing was changed in StoreLink by this call. Ask Korral IT "
                "to publish the new key for this store, then retry."
            ) from None


class StubTransport:
    """In-memory StoreLink used for the pilot exercise.

    Enforces the same contract as the real service: every request must
    present the current key for the store in its path, POSTs honour an
    idempotency key, and unknown resources are 404s.
    """

    def __init__(self, now: datetime | None = None):
        # Current valid key per store; rotate_key() simulates Korral IT's
        # weekly rotation on the StoreLink side.
        self.keys: dict[int, str] = {47: "stub-key-47", 102: "stub-key-102"}
        self._stores = {
            47: {"store_id": 47, "name": "Korral Praha 7 — Letná",
                 "region": "CZ Prague", "timezone": "Europe/Prague"},
            102: {"store_id": 102, "name": "Korral Brno — Veveří",
                  "region": "CZ South Moravia", "timezone": "Europe/Prague"},
        }
        self._skus = {
            "8847291": {"sku": "8847291", "name": "Madeta butter 250g",
                        "category": "dairy", "supplier_id": "SUP-441"},
        }
        self._suppliers = {
            "SUP-441": {"supplier_id": "SUP-441", "name": "Madeta a.s.",
                        "lead_time_days": 2},
        }
        self._inventory = {(47, "8847291"): 3, (102, "8847291"): 8}
        now = now or datetime.now(timezone.utc)
        self._pos = {
            (47, "8847291"): self._transactions(now, [(22, 3), (16, 4), (9, 3), (2, 2)]),
            (102, "8847291"): self._transactions(now, [(20, 5), (11, 4), (3, 3)]),
        }
        self._orders: dict[tuple[int, str], dict[str, Any]] = {}
        self._idempotency: dict[tuple[int, str], dict[str, Any]] = {}
        self._order_seq = 0

    @staticmethod
    def _transactions(now: datetime, hours_ago_and_units: list[tuple[int, int]]) -> list[dict]:
        return [
            {"timestamp": (now - timedelta(hours=hours)).isoformat(timespec="seconds"),
             "units": units}
            for hours, units in hours_ago_and_units
        ]

    def rotate_key(self, store_id: int, new_key: str) -> None:
        self.keys[store_id] = new_key

    def request(
        self,
        method: str,
        path: str,
        key: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        params = params or {}
        parts = path.strip("/").split("/")

        if parts[:2] == ["v1", "stores"] and len(parts) >= 3:
            store_id = int(parts[2])
            self._authorize(store_id, key)
            if len(parts) == 3 and method == "GET":
                return deepcopy(self._require(self._stores, store_id, path))
            if parts[3] == "inventory" and method == "GET":
                on_hand = self._require(self._inventory, (store_id, params["sku"]), path)
                return {"store_id": store_id, "sku": params["sku"], "on_hand_units": on_hand}
            if parts[3] == "pos" and method == "GET":
                transactions = self._require(self._pos, (store_id, params["sku"]), path)
                since = datetime.fromisoformat(params["since"])
                return deepcopy([
                    tx for tx in transactions
                    if datetime.fromisoformat(tx["timestamp"]) >= since
                ])
            if parts[3] == "replenishment" and method == "POST":
                return self._create_order(store_id, body or {}, idempotency_key)
            if parts[3] == "replenishment" and len(parts) == 5 and method == "GET":
                return deepcopy(self._require(self._orders, (store_id, parts[4]), path))

        if parts[:2] == ["v1", "skus"] and method == "GET":
            self._authorize_any(key)
            return deepcopy(self._require(self._skus, parts[2], path))
        if parts[:2] == ["v1", "suppliers"] and method == "GET":
            self._authorize_any(key)
            return deepcopy(self._require(self._suppliers, parts[2], path))

        raise StoreLinkNotFoundError(f"StoreLink has no route {method} {path}")

    def _authorize(self, store_id: int, key: str) -> None:
        if self.keys.get(store_id) != key:
            raise StoreLinkAuthError(f"401: invalid X-Korral-Store-Key for store {store_id}")

    def _authorize_any(self, key: str) -> None:
        if key not in self.keys.values():
            raise StoreLinkAuthError("401: invalid X-Korral-Store-Key")

    @staticmethod
    def _require(mapping: dict, resource_key: Any, path: str) -> Any:
        try:
            return mapping[resource_key]
        except KeyError:
            raise StoreLinkNotFoundError(f"StoreLink returned 404 for {path}") from None

    def _create_order(
        self, store_id: int, body: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise StoreLinkError("StoreLink requires an Idempotency-Key for replenishment")
        previous = self._idempotency.get((store_id, idempotency_key))
        if previous is not None:
            if previous["body"] != body:
                raise StoreLinkError(
                    "409: this Idempotency-Key was already used for a different request"
                )
            return deepcopy({**previous["order"], "duplicate_request": True})
        self._order_seq += 1
        order = {
            "order_id": f"R{store_id}-{self._order_seq:04d}",
            "store_id": store_id,
            "sku": body["sku"],
            "quantity_units": body["quantity_units"],
            "reason": body["reason"],
            "status": "received",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._orders[(store_id, order["order_id"])] = order
        self._idempotency[(store_id, idempotency_key)] = {
            "body": deepcopy(body), "order": deepcopy(order),
        }
        return deepcopy({**order, "duplicate_request": False})
