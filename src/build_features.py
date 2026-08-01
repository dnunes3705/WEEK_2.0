import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def parse_ymd(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def safe_float(value: str) -> float:
    v = (value or "").strip()
    return float(v) if v != "" else 0.0


def safe_int(value: str) -> int:
    v = (value or "").strip()
    return int(v) if v != "" else 0


def as_bool_yes_no(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"yes", "y", "true", "1"}:
        return True
    if v in {"no", "n", "false", "0"}:
        return False
    return False


def quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if q <= 0:
        return float(sorted_values[0])
    if q >= 1:
        return float(sorted_values[-1])
    idx = (len(sorted_values) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def delay_bucket(delay_minutes: int) -> str:
    if delay_minutes <= 0:
        return "On-Time"
    if delay_minutes <= 10:
        return "1-10"
    if delay_minutes <= 30:
        return "11-30"
    return "31+"


def rating_bucket(rating: int) -> str:
    if rating <= 2:
        return "1-2"
    if rating == 3:
        return "3"
    if rating == 4:
        return "4"
    return "5"


@dataclass
class OrderEvent:
    order_id: str
    order_date: date
    vendor_id: str
    vendor_category: str
    delivery_type: str
    items_count: int
    order_value_usd: float
    promo_used: bool
    discount_amount_usd: float
    delay_minutes: int
    delivery_status: str
    order_accuracy: str
    customer_rating: int


def load_customers(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return {row["customer_id"].strip(): row for row in reader}


def load_deliveries_by_order_id(path: Path) -> dict[str, dict[str, str]]:
    deliveries: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            deliveries[row["order_id"].strip()] = row
    return deliveries


def build_orders_enriched(
    customers: dict[str, dict[str, str]],
    deliveries_by_order_id: dict[str, dict[str, str]],
    orders_path: Path,
    out_path: Path,
) -> dict[str, list[OrderEvent]]:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    events_by_customer: dict[str, list[OrderEvent]] = defaultdict(list)

    with orders_path.open(newline="", encoding="utf-8-sig") as fin, out_path.open(
        "w", newline="", encoding="utf-8"
    ) as fout:
        reader = csv.DictReader(fin)

        base_cols = list(reader.fieldnames or [])
        customer_cols = [
            "signup_date",
            "city",
            "state",
            "age_group",
            "gender",
            "customer_segment",
            "preferred_device",
        ]
        delivery_cols = [
            "promised_time_min",
            "actual_time_min",
            "delay_minutes",
            "delivery_status",
            "order_accuracy",
            "customer_rating",
        ]
        engineered_cols = [
            "order_year",
            "order_month",
            "order_dayofweek",
            "is_weekend",
            "days_since_signup",
            "is_promo_used",
            "discount_pct",
            "is_delayed",
            "delay_bucket",
            "is_inaccurate",
            "is_low_rating",
            "rating_bucket",
        ]

        fieldnames = base_cols + customer_cols + delivery_cols + engineered_cols
        writer = csv.DictWriter(fout, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for row in reader:
            customer_id = row["customer_id"].strip()
            order_id = row["order_id"].strip()

            cust = customers.get(customer_id, {})
            deliv = deliveries_by_order_id.get(order_id, {})

            order_dt = parse_ymd(row["order_date"])
            signup_dt = parse_ymd(cust.get("signup_date", row["order_date"]))

            promo_used = as_bool_yes_no(row.get("promo_used", ""))
            discount_amount = safe_float(row.get("discount_amount_usd", "0"))
            order_value = safe_float(row.get("order_value_usd", "0"))
            discount_pct = (discount_amount / order_value) if order_value > 0 else 0.0

            delay_m = safe_int(deliv.get("delay_minutes", "0"))
            is_delayed = delay_m > 0 or (deliv.get("delivery_status", "") == "Delayed")
            acc = (deliv.get("order_accuracy", "") or "").strip()
            is_inaccurate = acc != "" and acc != "Correct"
            rating = safe_int(deliv.get("customer_rating", "0"))
            is_low_rating = rating != 0 and rating <= 3

            merged = dict(row)
            for c in customer_cols:
                merged[c] = cust.get(c, "")
            for c in delivery_cols:
                merged[c] = deliv.get(c, "")

            merged["order_year"] = str(order_dt.year)
            merged["order_month"] = f"{order_dt.year:04d}-{order_dt.month:02d}"
            merged["order_dayofweek"] = str(order_dt.weekday())  # 0=Mon..6=Sun
            merged["is_weekend"] = "Yes" if order_dt.weekday() >= 5 else "No"
            merged["days_since_signup"] = str((order_dt - signup_dt).days)

            merged["is_promo_used"] = "Yes" if promo_used else "No"
            merged["discount_pct"] = f"{discount_pct:.6f}"

            merged["is_delayed"] = "Yes" if is_delayed else "No"
            merged["delay_bucket"] = delay_bucket(delay_m)
            merged["is_inaccurate"] = "Yes" if is_inaccurate else "No"
            merged["is_low_rating"] = "Yes" if is_low_rating else "No"
            merged["rating_bucket"] = rating_bucket(rating) if rating else ""

            writer.writerow(merged)

            events_by_customer[customer_id].append(
                OrderEvent(
                    order_id=order_id,
                    order_date=order_dt,
                    vendor_id=row.get("vendor_id", "").strip(),
                    vendor_category=row.get("vendor_category", "").strip(),
                    delivery_type=row.get("delivery_type", "").strip(),
                    items_count=safe_int(row.get("items_count", "0")),
                    order_value_usd=order_value,
                    promo_used=promo_used,
                    discount_amount_usd=discount_amount,
                    delay_minutes=delay_m,
                    delivery_status=(deliv.get("delivery_status", "") or "").strip(),
                    order_accuracy=acc,
                    customer_rating=rating,
                )
            )

    return events_by_customer


def build_customer_features(
    customers: dict[str, dict[str, str]],
    events_by_customer: dict[str, list[OrderEvent]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    max_order_date = max(
        (e.order_date for events in events_by_customer.values() for e in events),
        default=None,
    )
    if max_order_date is None:
        raise RuntimeError("No orders found; cannot compute customer features.")

    customer_cols = [
        "customer_id",
        "signup_date",
        "city",
        "state",
        "age_group",
        "gender",
        "customer_segment",
        "preferred_device",
    ]

    feature_cols = [
        "first_order_date",
        "last_order_date",
        "days_active",
        "orders_total",
        "avg_order_value_usd",
        "avg_items_count",
        "promo_order_share",
        "avg_discount_amount_usd",
        "delayed_order_share",
        "median_delay_minutes",
        "p90_delay_minutes",
        "inaccurate_order_share",
        "avg_customer_rating",
        "low_rating_share",
        "orders_first_7d",
        "orders_first_14d",
        "days_to_second_order",
        "unique_vendors_first_14d",
        "unique_categories_first_14d",
        "retained_30d",
        "retained_90d",
        "eligible_30d",
        "eligible_90d",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=customer_cols + feature_cols)
        writer.writeheader()

        for customer_id, customer in customers.items():
            events = sorted(events_by_customer.get(customer_id, []), key=lambda e: e.order_date)
            if not events:
                continue

            first_dt = events[0].order_date
            last_dt = events[-1].order_date
            days_active = (last_dt - first_dt).days

            orders_total = len(events)
            avg_value = sum(e.order_value_usd for e in events) / orders_total
            avg_items = sum(e.items_count for e in events) / orders_total

            promo_share = sum(1 for e in events if e.promo_used) / orders_total
            avg_discount = sum(e.discount_amount_usd for e in events) / orders_total

            delayed_share = sum(1 for e in events if e.delay_minutes > 0 or e.delivery_status == "Delayed") / orders_total
            delays = sorted([float(e.delay_minutes) for e in events])
            med_delay = float(median(delays)) if delays else 0.0
            p90_delay = quantile(delays, 0.9) if delays else 0.0

            inaccurate_share = sum(1 for e in events if e.order_accuracy and e.order_accuracy != "Correct") / orders_total

            ratings = [e.customer_rating for e in events if e.customer_rating]
            avg_rating = (sum(ratings) / len(ratings)) if ratings else 0.0
            low_rating_share = (
                sum(1 for r in ratings if r <= 3) / len(ratings) if ratings else 0.0
            )

            orders_7d = sum(1 for e in events if (e.order_date - first_dt).days <= 7)
            orders_14d = sum(1 for e in events if (e.order_date - first_dt).days <= 14)

            days_to_second = ""
            if len(events) >= 2:
                days_to_second = str((events[1].order_date - first_dt).days)

            vendors_14 = set(
                e.vendor_id for e in events if (e.order_date - first_dt).days <= 14 and e.vendor_id
            )
            cats_14 = set(
                e.vendor_category
                for e in events
                if (e.order_date - first_dt).days <= 14 and e.vendor_category
            )

            eligible_30d = (max_order_date - first_dt).days >= 30
            eligible_90d = (max_order_date - first_dt).days >= 90

            retained_30d = (
                "Yes"
                if any(1 <= (e.order_date - first_dt).days <= 30 for e in events[1:])
                else "No"
            )
            retained_90d = (
                "Yes"
                if any(1 <= (e.order_date - first_dt).days <= 90 for e in events[1:])
                else "No"
            )

            row = {
                "customer_id": customer_id,
                "signup_date": customer.get("signup_date", ""),
                "city": customer.get("city", ""),
                "state": customer.get("state", ""),
                "age_group": customer.get("age_group", ""),
                "gender": customer.get("gender", ""),
                "customer_segment": customer.get("customer_segment", ""),
                "preferred_device": customer.get("preferred_device", ""),
                "first_order_date": first_dt.isoformat(),
                "last_order_date": last_dt.isoformat(),
                "days_active": str(days_active),
                "orders_total": str(orders_total),
                "avg_order_value_usd": f"{avg_value:.6f}",
                "avg_items_count": f"{avg_items:.6f}",
                "promo_order_share": f"{promo_share:.6f}",
                "avg_discount_amount_usd": f"{avg_discount:.6f}",
                "delayed_order_share": f"{delayed_share:.6f}",
                "median_delay_minutes": f"{med_delay:.6f}",
                "p90_delay_minutes": f"{p90_delay:.6f}",
                "inaccurate_order_share": f"{inaccurate_share:.6f}",
                "avg_customer_rating": f"{avg_rating:.6f}",
                "low_rating_share": f"{low_rating_share:.6f}",
                "orders_first_7d": str(orders_7d),
                "orders_first_14d": str(orders_14d),
                "days_to_second_order": days_to_second,
                "unique_vendors_first_14d": str(len(vendors_14)),
                "unique_categories_first_14d": str(len(cats_14)),
                "retained_30d": retained_30d,
                "retained_90d": retained_90d,
                "eligible_30d": "Yes" if eligible_30d else "No",
                "eligible_90d": "Yes" if eligible_90d else "No",
            }
            writer.writerow(row)


def main() -> None:
    customers_path = RAW_DIR / "customers.csv"
    orders_path = RAW_DIR / "orders.csv"
    deliveries_path = RAW_DIR / "deliveries.csv"

    customers = load_customers(customers_path)
    deliveries_by_order_id = load_deliveries_by_order_id(deliveries_path)

    orders_out = PROCESSED_DIR / "urbancart_orders_enriched.csv"
    customers_out = PROCESSED_DIR / "urbancart_customers_features.csv"

    events_by_customer = build_orders_enriched(
        customers=customers,
        deliveries_by_order_id=deliveries_by_order_id,
        orders_path=orders_path,
        out_path=orders_out,
    )
    build_customer_features(customers=customers, events_by_customer=events_by_customer, out_path=customers_out)

    print(f"Wrote: {orders_out}")
    print(f"Wrote: {customers_out}")


if __name__ == "__main__":
    main()

