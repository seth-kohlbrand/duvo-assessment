"""Deterministic buyer workflows and business rules."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import defaultdict
from typing import Any

from .storelink import StoreLinkClient
from .audit import AuditRecorder


class BuyerError(ValueError):
    """A safe, actionable error for an MCP caller."""


class BuyerService:
    COVER_DAYS = 21
    STORE_GAP_THRESHOLD_UNITS = 6

    def __init__(self, client: StoreLinkClient, audit: AuditRecorder | None = None) -> None:
        self.client = client
        self.audit = audit or AuditRecorder()
        self._plans: dict[str, dict[str, Any]] = {}

    def list_categories(self) -> dict[str, Any]:
        return {"categories": self.client.list_categories()}

    def review_category(self, category_id: str) -> dict[str, Any]:
        self._require_category(category_id)
        products = self.client.list_products(category_id)
        items = [self._item_summary(product) for product in products]
        return {
            "category_id": category_id,
            "item_count": len(items),
            "items_needing_attention": [item for item in items if item["needs_reorder"]],
            "items": items,
        }

    def investigate_product(self, product_id: str) -> dict[str, Any]:
        product = self._require_product(product_id)
        result = self._item_summary(product)
        result.update({
            "name": product["name"], "category_id": product["category_id"],
            "supplier_id": product["supplier_id"], "unit_cost": product["unit_cost"],
            "lead_time_days": product["lead_time_days"],
        })
        return result

    def replenish_store_stock(
        self, sku: str, store_ids: list[int], idempotency_key: str
    ) -> dict[str, Any]:
        operation_id = str(uuid.uuid4())
        started = time.perf_counter()
        key_fingerprint = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12] if idempotency_key else None
        operation_token = self.audit.begin_operation(operation_id)
        self.audit.technical({
            "operation_id": operation_id, "event": "workflow.started",
            "workflow": "replenish_store_stock", "sku": sku, "store_ids": store_ids,
            "idempotency_key_fingerprint": key_fingerprint,
        })
        try:
            result = self._replenish_store_stock(sku, store_ids, idempotency_key, operation_id)
        except Exception as exc:
            self.audit.technical({
                "operation_id": operation_id, "event": "workflow.failed",
                "workflow": "replenish_store_stock", "error_type": type(exc).__name__,
                "error_message": str(exc), "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            })
            self.audit.buyer({
                "operation_id": operation_id,
                "action": "Tried to check store stock and conditionally replenish it",
                "product": {"sku": sku}, "requested_stores": store_ids,
                "status": "failed", "orders_created": [],
                "plain_language_summary": self._safe_failure_summary(exc),
                "next_step": self._failure_next_step(exc),
            })
            raise
        else:
            result["operation_id"] = operation_id
            self.audit.technical({
                "operation_id": operation_id, "event": "workflow.completed",
                "workflow": "replenish_store_stock", "stores_checked": result["summary"]["stores_checked"],
                "orders_created": result["summary"]["stores_replenished"],
                "duplicate_request": result["summary"]["duplicate_request"],
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            })
            self.audit.buyer({
                "operation_id": operation_id, "action": "Checked store stock and conditionally replenished it",
                "product": {"sku": sku, "name": result["product_name"]},
                "requested_stores": store_ids, "rule_applied": "Order the gap only when 24-hour POS minus on-hand exceeds 6 units",
                "store_decisions": result["store_checks"], "orders": result["orders_created"],
                "was_safe_retry": result["summary"]["duplicate_request"],
                "plain_language_summary": self._buyer_summary(result),
            })
            return result
        finally:
            self.audit.end_operation(operation_token)

    def _replenish_store_stock(
        self, sku: str, store_ids: list[int], idempotency_key: str, operation_id: str
    ) -> dict[str, Any]:
        if not sku or not sku.isdigit():
            raise BuyerError("sku must contain digits only")
        if not store_ids or len(store_ids) > 50:
            raise BuyerError("store_ids must contain 1 to 50 store IDs")
        if len(set(store_ids)) != len(store_ids):
            raise BuyerError("store_ids must not contain duplicates")
        if not idempotency_key or len(idempotency_key) > 100:
            raise BuyerError("idempotency_key must contain 1 to 100 characters")

        checks = []
        orders_to_create = []
        product_name = None
        for store_id in store_ids:
            if not isinstance(store_id, int) or isinstance(store_id, bool) or store_id <= 0:
                raise BuyerError("each store_id must be a positive integer")
            if store_id not in self.client.credentialed_store_ids():
                available = ", ".join(str(value) for value in self.client.credentialed_store_ids()) or "none"
                raise BuyerError(
                    f"No StoreLink credential is configured for store {store_id}; no StoreLink calls or writes were made. "
                    f"Configured stores: {available}. Ask Korral IT to provision this store's weekly-rotated key."
                )
            call_started = time.perf_counter()
            evidence = self.client.get_store_stock(sku, store_id)
            self.audit.technical({
                "operation_id": operation_id, "event": "storelink.read.completed",
                "dependency": "StoreLink", "method": "get_store_stock", "store_id": store_id,
                "found": evidence is not None,
                "latency_ms": round((time.perf_counter() - call_started) * 1000, 3),
            })
            if evidence is None:
                raise BuyerError(f"Unknown SKU/store combination: {sku} at store {store_id}")
            product_name = evidence["product_name"]
            gap = evidence["pos_units_last_24h"] - evidence["on_hand_units"]
            should_replenish = gap > self.STORE_GAP_THRESHOLD_UNITS
            checks.append({
                "store_id": store_id,
                "on_hand_units": evidence["on_hand_units"],
                "pos_units_last_24h": evidence["pos_units_last_24h"],
                "gap_units": gap,
                "threshold_units": self.STORE_GAP_THRESHOLD_UNITS,
                "decision": "replenish" if should_replenish else "no_action",
                "reason": (
                    f"Gap {gap} exceeds {self.STORE_GAP_THRESHOLD_UNITS} units"
                    if should_replenish
                    else f"Gap {gap} does not exceed {self.STORE_GAP_THRESHOLD_UNITS} units"
                ),
            })
            if should_replenish:
                orders_to_create.append({"store_id": store_id, "quantity_units": gap})

            self.audit.technical({
                "operation_id": operation_id, "event": "business_rule.evaluated",
                "store_id": store_id, "on_hand_units": evidence["on_hand_units"],
                "pos_units_last_24h": evidence["pos_units_last_24h"], "gap_units": gap,
                "threshold_units": self.STORE_GAP_THRESHOLD_UNITS, "decision": "replenish" if should_replenish else "no_action",
            })

        try:
            call_started = time.perf_counter()
            orders, duplicate = self.client.create_store_replenishment_orders(
                sku, orders_to_create, idempotency_key
            )
        except ValueError as exc:
            raise BuyerError(str(exc)) from exc
        self.audit.technical({
            "operation_id": operation_id, "event": "storelink.write.completed",
            "dependency": "StoreLink", "method": "create_store_replenishment_orders",
            "requested_order_count": len(orders_to_create), "returned_order_ids": [order["replenishment_order_id"] for order in orders],
            "duplicate_request": duplicate, "latency_ms": round((time.perf_counter() - call_started) * 1000, 3),
        })
        return {
            "request": {"sku": sku, "store_ids": store_ids},
            "product_name": product_name,
            "rule": {"calculation": "pos_units_last_24h - on_hand_units", "replenish_when": "gap_units > 6"},
            "store_checks": checks,
            "orders_created": orders,
            "summary": {
                "stores_checked": len(checks),
                "stores_replenished": len(orders),
                "duplicate_request": duplicate,
            },
        }

    @staticmethod
    def _buyer_summary(result: dict[str, Any]) -> str:
        ordered = [str(order["store_id"]) for order in result["orders_created"]]
        if result["summary"]["duplicate_request"]:
            return "This was a safe retry; no duplicate replenishment orders were created."
        if not ordered:
            return "No store exceeded the 6-unit gap, so no replenishment order was placed."
        return f"Replenishment was placed for store(s) {', '.join(ordered)}; all other checked stores required no action."

    @staticmethod
    def _safe_failure_summary(exc: Exception) -> str:
        if isinstance(exc, BuyerError):
            return str(exc)
        return "The StoreLink check could not be completed safely, so no new replenishment action was taken."

    @staticmethod
    def _failure_next_step(exc: Exception) -> str:
        if isinstance(exc, BuyerError) and "credential" in str(exc).lower():
            return "Ask Korral IT to provision or refresh the per-store key, then retry the request."
        return "Review the technical trace using this operation ID before retrying."

    def plan_replenishment(self, category_id: str) -> dict[str, Any]:
        self._require_category(category_id)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for product in self.client.list_products(category_id):
            quantity = self._recommended_quantity(product)
            if quantity > 0:
                grouped[product["supplier_id"]].append({
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity": quantity,
                    "unit_cost": product["unit_cost"],
                    "line_total": round(quantity * product["unit_cost"], 2),
                    "reason": f"Restore {self.COVER_DAYS} days of cover using the last 28 days of sales",
                })
        orders = [
            {
                "supplier_id": supplier_id,
                "lines": lines,
                "order_total": round(sum(line["line_total"] for line in lines), 2),
            }
            for supplier_id, lines in sorted(grouped.items())
        ]
        fingerprint = json.dumps({"category_id": category_id, "orders": orders}, sort_keys=True)
        plan_id = "RP-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
        plan = {
            "plan_id": plan_id, "category_id": category_id, "status": "ready",
            "orders": orders, "total_cost": round(sum(order["order_total"] for order in orders), 2),
            "next_step": "Review the proposal, then submit this plan using its plan_id.",
        }
        self._plans[plan_id] = plan
        return plan

    def submit_replenishment(self, plan_id: str, idempotency_key: str) -> dict[str, Any]:
        if not plan_id or plan_id not in self._plans:
            raise BuyerError("Unknown plan_id; create a fresh replenishment plan first")
        if not idempotency_key or len(idempotency_key) > 100:
            raise BuyerError("idempotency_key must contain 1 to 100 characters")
        plan = self._plans[plan_id]
        if not plan["orders"]:
            raise BuyerError("This plan has no orders to submit")
        orders, duplicate = self.client.create_purchase_orders(plan["orders"], idempotency_key)
        return {
            "plan_id": plan_id, "duplicate_request": duplicate,
            "purchase_orders": orders,
            "message": "Existing result returned; no duplicate orders created" if duplicate else "Purchase orders submitted",
        }

    def get_purchase_order(self, purchase_order_id: str) -> dict[str, Any]:
        if not purchase_order_id:
            raise BuyerError("purchase_order_id is required")
        order = self.client.get_purchase_order(purchase_order_id)
        if order is None:
            raise BuyerError(f"Unknown purchase_order_id: {purchase_order_id}")
        return order

    def _require_category(self, category_id: str) -> dict[str, Any]:
        if not category_id:
            raise BuyerError("category_id is required")
        category = self.client.get_category(category_id)
        if category is None:
            raise BuyerError(f"Unknown category_id: {category_id}")
        return category

    def _require_product(self, product_id: str) -> dict[str, Any]:
        if not product_id:
            raise BuyerError("product_id is required")
        product = self.client.get_product(product_id)
        if product is None:
            raise BuyerError(f"Unknown product_id: {product_id}")
        return product

    def _recommended_quantity(self, product: dict[str, Any]) -> int:
        target = round(product["units_sold_28d"] / 28 * self.COVER_DAYS)
        return max(0, target - product["on_hand"] - product["on_order"])

    def _item_summary(self, product: dict[str, Any]) -> dict[str, Any]:
        daily_sales = product["units_sold_28d"] / 28
        days_of_cover = None if daily_sales == 0 else round((product["on_hand"] + product["on_order"]) / daily_sales, 1)
        recommended = self._recommended_quantity(product)
        return {
            "product_id": product["id"], "on_hand": product["on_hand"],
            "on_order": product["on_order"], "units_sold_28d": product["units_sold_28d"],
            "days_of_cover": days_of_cover, "needs_reorder": recommended > 0,
            "recommended_quantity": recommended,
        }
