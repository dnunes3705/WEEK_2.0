import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median


PROCESSED_DIR = Path("data/processed")


def parse_ymd(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def safe_int(value: str) -> int:
    v = (value or "").strip()
    return int(v) if v != "" else 0


def safe_float(value: str) -> float:
    v = (value or "").strip()
    return float(v) if v != "" else 0.0


def yes_no(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"yes", "y", "true", "1"}:
        return "Yes"
    if v in {"no", "n", "false", "0"}:
        return "No"
    return ""


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


@dataclass(frozen=True)
class OrderEvent:
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


def clean_orders_enriched(
    in_path: Path, out_path: Path
) -> tuple[dict[str, list[OrderEvent]], dict[str, dict[str, str]], date]:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    events_by_customer: dict[str, list[OrderEvent]] = defaultdict(list)
    customer_dim: dict[str, dict[str, str]] = {}
    max_order_date: date | None = None

    with in_path.open(newline="", encoding="utf-8-sig") as fin, out_path.open(
        "w", newline="", encoding="utf-8"
    ) as fout:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            customer_id = (row.get("customer_id") or "").strip()
            order_dt = parse_ymd(row["order_date"])
            signup_dt = parse_ymd(row["signup_date"])

            if max_order_date is None or order_dt > max_order_date:
                max_order_date = order_dt

            # Normalize key fields
            row["promo_used"] = yes_no(row.get("promo_used", ""))
            row["is_promo_used"] = row["promo_used"]

            order_value = safe_float(row.get("order_value_usd", "0"))
            discount_amount = safe_float(row.get("discount_amount_usd", "0"))
            row["order_value_usd"] = f"{order_value:.2f}".rstrip("0").rstrip(".") if order_value % 1 else f"{int(order_value)}"
            row["discount_amount_usd"] = (
                f"{discount_amount:.2f}".rstrip("0").rstrip(".") if discount_amount % 1 else f"{int(discount_amount)}"
            )
            discount_pct = (discount_amount / order_value) if order_value > 0 else 0.0
            row["discount_pct"] = f"{discount_pct:.6f}"

            promised = safe_int(row.get("promised_time_min", "0"))
            actual = safe_int(row.get("actual_time_min", "0"))
            delay = safe_int(row.get("delay_minutes", "0"))
            computed_delay = max(actual - promised, 0)
            if computed_delay != delay:
                delay = computed_delay
                row["delay_minutes"] = str(delay)

            row["promised_time_min"] = str(promised)
            row["actual_time_min"] = str(actual)

            is_delayed = "Yes" if delay > 0 else "No"
            row["is_delayed"] = is_delayed
            row["delivery_status"] = "Delayed" if delay > 0 else "On-Time"
            row["delay_bucket"] = delay_bucket(delay)

            acc = (row.get("order_accuracy") or "").strip()
            row["is_inaccurate"] = "No" if acc == "Correct" else "Yes"

            rating = safe_int(row.get("customer_rating", "0"))
            row["customer_rating"] = str(rating)
            row["rating_bucket"] = rating_bucket(rating) if rating else ""
            row["is_low_rating"] = "Yes" if rating and rating <= 3 else "No"

            # Recompute time-derived fields from order_date/signup_date
            row["order_year"] = str(order_dt.year)
            row["order_month"] = f"{order_dt.year:04d}-{order_dt.month:02d}"
            row["order_dayofweek"] = str(order_dt.weekday())
            row["is_weekend"] = "Yes" if order_dt.weekday() >= 5 else "No"
            row["days_since_signup"] = str((order_dt - signup_dt).days)

            # Keep a stable customer dimension snapshot
            if customer_id and customer_id not in customer_dim:
                customer_dim[customer_id] = {
                    "signup_date": row.get("signup_date", ""),
                    "city": row.get("city", ""),
                    "state": row.get("state", ""),
                    "age_group": row.get("age_group", ""),
                    "gender": row.get("gender", ""),
                    "customer_segment": row.get("customer_segment", ""),
                    "preferred_device": row.get("preferred_device", ""),
                }

            writer.writerow(row)

            # Build event list for customer-level aggregation
            promo_used = row["promo_used"] == "Yes"
            events_by_customer[customer_id].append(
                OrderEvent(
                    order_date=order_dt,
                    vendor_id=(row.get("vendor_id") or "").strip(),
                    vendor_category=(row.get("vendor_category") or "").strip(),
                    delivery_type=(row.get("delivery_type") or "").strip(),
                    items_count=safe_int(row.get("items_count", "0")),
                    order_value_usd=order_value,
                    promo_used=promo_used,
                    discount_amount_usd=discount_amount,
                    delay_minutes=delay,
                    delivery_status=row["delivery_status"],
                    order_accuracy=acc,
                    customer_rating=rating,
                )
            )

    if max_order_date is None:
        raise RuntimeError("No orders found in urbancart_orders_enriched.csv")

    return events_by_customer, customer_dim, max_order_date


def retention_label(observed_yes: bool, eligible: bool) -> str:
    if observed_yes:
        return "Yes"
    if eligible:
        return "No"
    return ""


def build_customers_features_clean(
    events_by_customer: dict[str, list[OrderEvent]],
    customer_dim: dict[str, dict[str, str]],
    max_order_date: date,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

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

    # Keep original columns + add censoring-safe labels and helpful flags
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
        "has_second_order",
        "unique_vendors_first_14d",
        "unique_categories_first_14d",
        "retained_30d_observed",
        "retained_90d_observed",
        "eligible_30d",
        "eligible_90d",
        "retained_30d",
        "retained_90d",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=customer_cols + feature_cols)
        writer.writeheader()

        for customer_id, events in events_by_customer.items():
            if not customer_id:
                continue
            ordered = sorted(events, key=lambda e: e.order_date)
            first_dt = ordered[0].order_date
            last_dt = ordered[-1].order_date

            orders_total = len(ordered)
            days_active = (last_dt - first_dt).days

            avg_value = sum(e.order_value_usd for e in ordered) / orders_total
            avg_items = sum(e.items_count for e in ordered) / orders_total

            promo_share = sum(1 for e in ordered if e.promo_used) / orders_total
            avg_discount = sum(e.discount_amount_usd for e in ordered) / orders_total

            delayed_share = sum(
                1
                for e in ordered
                if e.delay_minutes > 0 or e.delivery_status == "Delayed"
            ) / orders_total

            delays = sorted(float(e.delay_minutes) for e in ordered)
            med_delay = float(median(delays)) if delays else 0.0
            p90_delay = quantile(delays, 0.9) if delays else 0.0

            inaccurate_share = sum(
                1 for e in ordered if e.order_accuracy and e.order_accuracy != "Correct"
            ) / orders_total

            ratings = [e.customer_rating for e in ordered if e.customer_rating]
            avg_rating = (sum(ratings) / len(ratings)) if ratings else 0.0
            low_rating_share = (
                sum(1 for r in ratings if r <= 3) / len(ratings) if ratings else 0.0
            )

            orders_7d = sum(1 for e in ordered if (e.order_date - first_dt).days <= 7)
            orders_14d = sum(1 for e in ordered if (e.order_date - first_dt).days <= 14)

            has_second = orders_total >= 2
            days_to_second = (
                str((ordered[1].order_date - first_dt).days) if has_second else ""
            )

            vendors_14 = {
                e.vendor_id
                for e in ordered
                if (e.order_date - first_dt).days <= 14 and e.vendor_id
            }
            cats_14 = {
                e.vendor_category
                for e in ordered
                if (e.order_date - first_dt).days <= 14 and e.vendor_category
            }

            eligible_30d = (max_order_date - first_dt).days >= 30
            eligible_90d = (max_order_date - first_dt).days >= 90

            observed_30d = any(
                1 <= (e.order_date - first_dt).days <= 30 for e in ordered[1:]
            )
            observed_90d = any(
                1 <= (e.order_date - first_dt).days <= 90 for e in ordered[1:]
            )

            row = {
                "customer_id": customer_id,
                **customer_dim.get(customer_id, {}),
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
                "has_second_order": "Yes" if has_second else "No",
                "unique_vendors_first_14d": str(len(vendors_14)),
                "unique_categories_first_14d": str(len(cats_14)),
                "retained_30d_observed": "Yes" if observed_30d else "No",
                "retained_90d_observed": "Yes" if observed_90d else "No",
                "eligible_30d": "Yes" if eligible_30d else "No",
                "eligible_90d": "Yes" if eligible_90d else "No",
                "retained_30d": retention_label(observed_30d, eligible_30d),
                "retained_90d": retention_label(observed_90d, eligible_90d),
            }
            writer.writerow(row)


def main() -> None:
    orders_in = PROCESSED_DIR / "urbancart_orders_enriched.csv"
    customers_in = PROCESSED_DIR / "urbancart_customers_features.csv"

    if not orders_in.exists():
        raise SystemExit(f"Missing input file: {orders_in}")
    if not customers_in.exists():
        raise SystemExit(f"Missing input file: {customers_in}")

    orders_out = PROCESSED_DIR / "urbancart_orders_enriched_clean.csv"
    customers_out = PROCESSED_DIR / "urbancart_customers_features_clean.csv"

    events_by_customer, customer_dim, max_order_date = clean_orders_enriched(
        in_path=orders_in, out_path=orders_out
    )
    build_customers_features_clean(
        events_by_customer=events_by_customer,
        customer_dim=customer_dim,
        max_order_date=max_order_date,
        out_path=customers_out,
    )

    print(f"Wrote: {orders_out}")
    print(f"Wrote: {customers_out}")


if __name__ == "__main__":
    main()

