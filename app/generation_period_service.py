from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.claim_period_service import ClaimPeriod, resolve_claim_period


@dataclass(frozen=True)
class GenerationPeriod:
    mode: str
    start_date: date
    end_date: date
    label: str
    display: str
    slug: str
    year: int | None = None
    month: int | None = None
    standard_claim_period_custom: bool = False

    @property
    def custom(self) -> bool:
        return self.mode == "custom"


def _from_claim_period(claim_period: ClaimPeriod) -> GenerationPeriod:
    return GenerationPeriod(
        mode="standard",
        start_date=claim_period.start_date,
        end_date=claim_period.end_date,
        label=claim_period.label,
        display=claim_period.display,
        slug=f"{int(claim_period.year)}/{int(claim_period.month):02d}",
        year=int(claim_period.year),
        month=int(claim_period.month),
        standard_claim_period_custom=bool(claim_period.custom),
    )


def resolve_standard_generation_period(year: int, month: int) -> GenerationPeriod:
    return _from_claim_period(resolve_claim_period(int(year), int(month)))


def resolve_custom_generation_period(start_date: date, end_date: date) -> GenerationPeriod:
    if start_date is None:
        raise ValueError("Start date is required for a custom date range.")
    if end_date is None:
        raise ValueError("End date is required for a custom date range.")
    if end_date < start_date:
        raise ValueError("End date cannot be before start date.")
    slug = f"custom_{start_date:%Y%m%d}_to_{end_date:%Y%m%d}"
    return GenerationPeriod(
        mode="custom",
        start_date=start_date,
        end_date=end_date,
        label=f"Custom date range {start_date.isoformat()} to {end_date.isoformat()}",
        display=f"{start_date.isoformat()} to {end_date.isoformat()}",
        slug=slug,
        year=start_date.year,
        month=start_date.month,
    )


def describe_generation_period(period: GenerationPeriod) -> str:
    if period.mode == "custom":
        return f"custom date range {period.display}"
    return f"{period.label}: {period.display}"


def output_period_slug(period: GenerationPeriod) -> str:
    if period.mode == "custom":
        return period.slug
    return f"{int(period.year)}/{int(period.month):02d}"
