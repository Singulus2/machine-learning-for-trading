#!/usr/bin/env python3
"""
Download Individual (Non-Continuous) Futures Contracts from Databento

Config-driven download of raw, per-contract hourly OHLCV bars plus contract
definitions (real expiration dates) for ES and CL. This is what
`02_financial_data_universe/04_cme_futures_eda.py` and
`06_futures_continuous.py` need to demonstrate roll mechanics — the
continuous series that `download.py` fetches are already pre-rolled and
hide exactly the roll gaps those notebooks are built to show.

Two artifacts are produced:
  1. futures/market/individual/{PRODUCT}/data.parquet
     Per-contract hourly OHLCV bars for every configured contract month,
     stacked together (one row per bar, real numeric `instrument_id`).
  2. futures/market/contract_definitions.parquet
     One row per contract (product, symbol, instrument_id, expiration),
     shared across all individual-contract products.

The expiration used to bound each contract's OHLCV download window comes
from Databento's `definition` schema (queried once per product), not from
a hardcoded day-of-month guess — CL in particular expires roughly a month
before its delivery-month label, so a fixed offset would be wrong.

Usage:
    # Estimate cost only (no download)
    python databento_individual.py --estimate

    # Download all products from config (idempotent)
    python databento_individual.py

    # Download a specific product
    python databento_individual.py --product ES

    # Dry run (show what would be downloaded)
    python databento_individual.py --dry-run

    # Force re-download even if data exists
    python databento_individual.py --force

Author: ML4T Third Edition
"""

from __future__ import annotations

import argparse
import tempfile
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import yaml

from utils.downloading import (
    databento_acknowledge,
    databento_estimate_only_notice,
    patch_databento_symbology,
    resolve_data_dir,
)


def _retry(fn, *, attempts: int = 3, base_delay: float = 2.0, label: str = ""):
    """Retry a Databento API call on transient streaming errors.

    Databento's HTTP streaming occasionally drops mid-response ("Response
    ended prematurely") with no correlation to the request itself — observed
    in practice after 3+ successful identical calls in a row. A short retry
    with linear backoff clears it without needing --force / a full re-run
    that would re-download (and re-pay for) everything already fetched.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < attempts:
                delay = base_delay * attempt
                print(f"    Retrying {label} after error ({attempt}/{attempts}): {e}")
                time.sleep(delay)
    raise last_exc

# ============================================================================
# Configuration
# ============================================================================

_MONTH_CODE = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}

CANONICAL_COLUMNS = [
    "timestamp",
    "rtype",
    "publisher_id",
    "instrument_id",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "product",
]

CANONICAL_DTYPES = {
    "timestamp": pl.Datetime("ns", time_zone="UTC"),
    "rtype": pl.UInt8,
    "publisher_id": pl.UInt16,
    "instrument_id": pl.UInt32,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.UInt64,
}


@dataclass
class ProductConfig:
    """One product's entry under the `individual:` section of config.yaml."""

    name: str
    months: list[int]
    download_window_months: int


@dataclass
class IndividualConfig:
    """Individual-contract download configuration."""

    dataset: str
    schema: str
    stype_in: str
    output_dir: str
    years: list[int]
    products: dict[str, ProductConfig]

    @classmethod
    def load(cls, config_path: Path, dataset: str) -> IndividualConfig:
        with open(config_path) as f:
            data = yaml.safe_load(f)

        section = data["individual"]
        products = {
            code: ProductConfig(
                name=cfg["name"],
                months=cfg["months"],
                download_window_months=cfg["download_window_months"],
            )
            for code, cfg in section["products"].items()
        }

        return cls(
            dataset=dataset,
            schema=section["schema"],
            stype_in=section["stype_in"],
            output_dir=section["output_dir"],
            years=section["years"],
            products=products,
        )


def get_config_path() -> Path:
    """Get path to config file (shared with download.py)."""
    return Path(__file__).parent / "config.yaml"


# ============================================================================
# Contract Symbol Generation
# ============================================================================


@dataclass
class ContractSpec:
    """A single contract we want data for, before real expiration is known.

    Two symbol spellings are tracked because Databento's own `raw_symbol`
    convention (single-digit year, e.g. "ESH4") differs from the two-digit
    convention the notebooks use for the human-readable `symbol` column in
    contract_definitions.parquet (e.g. "ESH24", matching
    06_futures_continuous.py's `parse_contract_symbol`). `raw_symbol` is what
    Databento's API accepts; `symbol` is what gets written to disk.
    """

    product: str
    symbol: str  # e.g. "ESH24" — canonical, written to contract_definitions.parquet
    raw_symbol: str  # e.g. "ESH4" — Databento's stype_in="raw_symbol" convention
    month: int
    year: int
    approx_expiration: date  # 15th-of-contract-month placeholder


def build_contract_specs(
    product: str, cfg: ProductConfig, years: list[int]
) -> list[ContractSpec]:
    """Enumerate contract symbols for a product across the configured years."""
    specs = []
    for year in sorted(years):
        for month in cfg.months:
            code = _MONTH_CODE[month]
            specs.append(
                ContractSpec(
                    product=product,
                    symbol=f"{product}{code}{year % 100:02d}",
                    raw_symbol=f"{product}{code}{year % 10}",
                    month=month,
                    year=year,
                    approx_expiration=date(year, month, 15),
                )
            )
    return specs


def _to_polars(databento_result) -> pl.DataFrame:
    """Convert a databento API result to a Polars DataFrame via parquet round-trip.

    A zero-row result (e.g. a definitions query whose window misses the
    contract's actual trading dates) makes `to_parquet` write a file with no
    valid header/footer, which `pl.read_parquet` rejects. Treat that as "no
    data" rather than letting it crash the caller.
    """
    patch_databento_symbology()
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        databento_result.to_parquet(tmp_path)
        if tmp_path.stat().st_size < 12:
            return pl.DataFrame()
        return pl.read_parquet(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


# ============================================================================
# Contract Definitions (real expiration dates)
# ============================================================================


_DEFINITION_EMPTY_SCHEMA = {
    "product": pl.Utf8,
    "symbol": pl.Utf8,
    "instrument_id": pl.Int64,
    "expiration": pl.Datetime("ns", time_zone="UTC"),
}


def fetch_contract_definition(client, config: IndividualConfig, spec: ContractSpec) -> pl.DataFrame:
    """Fetch the definition (real expiration, instrument_id) for a single contract.

    Queries with the contract's own raw_symbol and a narrow +/-10 day window
    around the 15th-of-month placeholder, rather than one broad multi-year
    "{product}.FUT" parent query. The parent query pulls in every
    calendar-spread and far-dated instrument Databento has ever listed for the
    product family (a single day of ES.FUT returns 40+ instruments); over a
    multi-year window that response is orders of magnitude larger than what we
    need and can take a very long time to stream. One narrow raw_symbol query
    per contract returns just that contract's own definition rows and is fast
    (empirically well under a second).

    Returns:
        DataFrame with columns: product, symbol, instrument_id, expiration.
        Empty (but correctly typed) if the contract isn't listed yet or
        Databento returns nothing.
    """
    # Asymmetric window: CL's real last-trade date falls ~1 month *before* its
    # delivery-month label (CLF24 = Jan 2024 delivery, but trading stops in
    # mid/late December 2023), while ES expires within its own contract month.
    # -45/+10 days around the 15th-of-month placeholder covers both.
    window_start = spec.approx_expiration - timedelta(days=45)
    window_end = min(spec.approx_expiration + timedelta(days=10), date.today())
    if window_start >= window_end:
        return pl.DataFrame(schema=_DEFINITION_EMPTY_SCHEMA)

    data = _retry(
        lambda: client.timeseries.get_range(
            dataset=config.dataset,
            symbols=[spec.raw_symbol],
            schema="definition",
            start=window_start.isoformat(),
            end=window_end.isoformat(),
            stype_in="raw_symbol",
        ),
        label=f"definition for {spec.symbol}",
    )
    df = _to_polars(data)
    if df.height == 0:
        return pl.DataFrame(schema=_DEFINITION_EMPTY_SCHEMA)

    if "instrument_id" not in df.columns or "expiration" not in df.columns:
        print(f"    Warning: definition response missing columns (got: {df.columns})")
        return pl.DataFrame(schema=_DEFINITION_EMPTY_SCHEMA)

    return (
        df.unique(subset=["instrument_id"], keep="last")
        .select(
            pl.lit(spec.product).alias("product"),
            pl.lit(spec.symbol).alias("symbol"),
            pl.col("instrument_id").cast(pl.Int64),
            pl.col("expiration").cast(pl.Datetime("ns", time_zone="UTC")),
        )
        .head(1)
    )


def fetch_definitions(client, config: IndividualConfig, product: str) -> pl.DataFrame:
    """Fetch real contract definitions for every configured contract of a product.

    Returns:
        DataFrame with columns: product, symbol, instrument_id, expiration.
        Empty (but correctly typed) if nothing could be resolved.
    """
    cfg = config.products[product]
    specs = build_contract_specs(product, cfg, config.years)

    parts = []
    for spec in specs:
        try:
            df = fetch_contract_definition(client, config, spec)
        except Exception as e:
            print(f"    Warning: definition lookup failed for {spec.symbol}, using "
                  f"15th-of-month placeholder for its download window: {e}")
            continue
        if df.height > 0:
            parts.append(df)
        else:
            print(f"    No definition found for {spec.symbol} (not yet listed or expired long ago)")

    if not parts:
        return pl.DataFrame(schema=_DEFINITION_EMPTY_SCHEMA)

    return pl.concat(parts).sort("symbol")


def merge_definitions(data_dir: Path, new_defs: pl.DataFrame) -> Path:
    """Merge newly fetched definitions into the shared contract_definitions.parquet."""
    output_path = data_dir / "futures" / "market" / "contract_definitions.parquet"

    if output_path.exists():
        existing = pl.read_parquet(output_path)
        combined = pl.concat([existing, new_defs], how="diagonal_relaxed")
        combined = combined.unique(subset=["product", "symbol"], keep="last").sort(
            ["product", "symbol"]
        )
    else:
        combined = new_defs.sort(["product", "symbol"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.parent / f".{output_path.name}.tmp"
    combined.write_parquet(tmp_path)
    tmp_path.replace(output_path)

    return output_path


# ============================================================================
# Cost Estimation
# ============================================================================


def estimate_cost(
    client, config: IndividualConfig, products: list[str], expirations: dict[str, dict[str, date]]
) -> float:
    """Estimate total download cost (definitions + per-contract OHLCV) in USD."""
    total = 0.0

    for product in products:
        cfg = config.products[product]
        specs = build_contract_specs(product, cfg, config.years)

        # Definitions: one narrow (+/-10 day) raw_symbol query per contract.
        # Databento's definition schema is priced by row count, not payload
        # size, and these queries return a handful of rows each — empirically
        # ~$0.0001 for a single day of one instrument, i.e. negligible even
        # across all configured contracts. Not worth a get_cost() round trip
        # per contract just to estimate; the real download timing is what
        # matters here, not the cost.

        # Per-contract OHLCV calls
        for spec in specs:
            window_start, window_end = _contract_window(spec, cfg, expirations.get(product, {}))
            if window_start >= window_end:
                continue
            try:
                total += client.metadata.get_cost(
                    dataset=config.dataset,
                    symbols=[spec.raw_symbol],
                    schema=config.schema,
                    start=window_start.isoformat(),
                    end=window_end.isoformat(),
                    stype_in=config.stype_in,
                )
            except Exception as e:
                print(f"    Warning: cost estimate failed for {spec.symbol}: {e}")

    return total


def _contract_window(
    spec: ContractSpec, cfg: ProductConfig, real_expirations: dict[str, date]
) -> tuple[date, date]:
    """Resolve the [start, end) OHLCV download window for one contract.

    Prefers the real expiration date (from `fetch_definitions`) over the
    15th-of-month placeholder, since actual last-trade dates vary by product
    (CL expires ~1 month before its delivery-month label; ES expires the
    3rd Friday of its contract month).
    """
    expiration = real_expirations.get(spec.symbol, spec.approx_expiration)
    window_start = expiration - timedelta(days=31 * cfg.download_window_months)
    window_end = min(expiration + timedelta(days=2), date.today())
    return window_start, window_end


# ============================================================================
# Download Functions
# ============================================================================


def download_contract(
    client, config: IndividualConfig, spec: ContractSpec, window_start: date, window_end: date
) -> tuple[pl.DataFrame | None, str]:
    """Download hourly OHLCV bars for a single contract."""
    try:
        data = _retry(
            lambda: client.timeseries.get_range(
                dataset=config.dataset,
                symbols=[spec.raw_symbol],
                schema=config.schema,
                start=window_start.isoformat(),
                end=window_end.isoformat(),
                stype_in=config.stype_in,
            ),
            label=f"OHLCV for {spec.symbol}",
        )
        df = _to_polars(data)

        if df.height == 0:
            return None, f"No data returned for {spec.symbol}"

        if "ts_event" in df.columns:
            df = df.rename({"ts_event": "timestamp"})

        df = df.with_columns(pl.lit(spec.product).alias("product"))
        df = df.select([c for c in CANONICAL_COLUMNS if c in df.columns])
        missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
        if missing:
            return None, f"{spec.symbol}: response missing columns {missing}"

        df = df.cast(CANONICAL_DTYPES)

        return df, f"Downloaded {spec.symbol}: {df.height:,} rows"

    except Exception as e:
        return None, f"Error downloading {spec.symbol}: {e}"


def download_product(
    client,
    config: IndividualConfig,
    product: str,
    data_dir: Path,
    dry_run: bool,
) -> dict:
    """Download definitions + all configured contracts for one product."""
    cfg = config.products[product]
    print(f"\n  Fetching contract definitions for {product}...", flush=True)

    if dry_run:
        specs = build_contract_specs(product, cfg, config.years)
        print(f"    [DRY RUN] Would fetch definitions and {len(specs)} contracts for {product}")
        return {"downloaded": 0, "failed": 0, "rows": 0, "skipped": len(specs)}

    definitions = fetch_definitions(client, config, product)
    if definitions.height > 0:
        merge_definitions(data_dir, definitions)
        print(f"    Got {definitions.height} contract definitions")
    else:
        print(f"    Warning: no definitions returned for {product} — falling back to "
              f"15th-of-month expiration placeholders for download windows")

    real_expirations = {
        row["symbol"]: row["expiration"].date() for row in definitions.iter_rows(named=True)
    }

    specs = build_contract_specs(product, cfg, config.years)
    stats = {"downloaded": 0, "failed": 0, "rows": 0, "skipped": 0}
    contract_dfs = []

    for spec in specs:
        window_start, window_end = _contract_window(spec, cfg, real_expirations)
        if window_start >= window_end:
            stats["skipped"] += 1
            print(f"    Skipping {spec.symbol}: not yet tradable (window starts in the future)")
            continue

        df, msg = download_contract(client, config, spec, window_start, window_end)
        print(f"    {msg}")

        if df is not None:
            stats["downloaded"] += 1
            stats["rows"] += df.height
            contract_dfs.append(df)
        else:
            stats["failed"] += 1

    if contract_dfs:
        new_data = pl.concat(contract_dfs)
        output_path = data_dir / config.output_dir / product / "data.parquet"

        if output_path.exists():
            existing = pl.read_parquet(output_path)
            new_data = pl.concat([existing, new_data], how="diagonal_relaxed")

        new_data = new_data.unique(subset=["timestamp", "instrument_id"], keep="last").sort(
            "timestamp"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.parent / f".{output_path.name}.tmp"
        new_data.write_parquet(tmp_path)
        tmp_path.replace(output_path)
        print(f"    Wrote {new_data.height:,} total rows -> {output_path}")

    return stats


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Download individual (non-continuous) futures contracts from Databento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check coverage and estimate cost
    python databento_individual.py --estimate

    # Download all products from config (idempotent)
    python databento_individual.py

    # Download a specific product
    python databento_individual.py --product ES

    # Dry run (show what would be downloaded)
    python databento_individual.py --dry-run

    # Force re-download even if data exists
    python databento_individual.py --force
        """,
    )
    parser.add_argument(
        "--product",
        "-p",
        action="append",
        dest="products",
        help="Specific product(s) to download (can repeat). Default: all from config (ES, CL)",
    )
    parser.add_argument(
        "--estimate",
        "--estimate-only",
        "-e",
        action="store_true",
        help="Only estimate costs, don't download",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be downloaded without downloading",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-download even if data exists",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config YAML (default: config.yaml next to this script)",
    )

    args = parser.parse_args()

    config_path = args.config or get_config_path()
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return 1

    with open(config_path) as f:
        dataset = yaml.safe_load(f)["dataset"]
    config = IndividualConfig.load(config_path, dataset=dataset)

    data_dir = resolve_data_dir(None)
    products = args.products or list(config.products.keys())

    print("=" * 70)
    print("DATABENTO INDIVIDUAL CONTRACTS DOWNLOAD (Config-Driven)")
    print("=" * 70)
    print(f"Config: {config_path}")
    print(f"Data directory: {data_dir}")
    print(f"Dataset: {config.dataset} | Schema: {config.schema} | stype_in: {config.stype_in}")
    print(f"Products: {products}")
    print(f"Years: {config.years}")
    print()

    # Coverage check — idempotent unless --force
    products_needing_update = []
    for product in products:
        output_path = data_dir / config.output_dir / product / "data.parquet"
        if output_path.exists() and not args.force:
            print(f"  {product}: already have {output_path} (use --force to re-download)")
        else:
            products_needing_update.append(product)

    if not products_needing_update:
        print("\nAll requested products are already downloaded. Use --force to re-download.")
        return 0

    import databento as db

    client = db.Historical()

    # Cost estimation — ALWAYS estimate before any download
    print("\nEstimating download cost (definitions + per-contract OHLCV)...")
    expirations_for_estimate: dict[str, dict[str, date]] = {p: {} for p in products_needing_update}
    cost = estimate_cost(client, config, products_needing_update, expirations_for_estimate)

    if args.estimate:
        databento_estimate_only_notice(cost)
        return 0

    if args.dry_run:
        print(f"\n[DRY RUN] Estimated cost: ${cost:.2f}")
        for product in products_needing_update:
            download_product(client, config, product, data_dir, dry_run=True)
        return 0

    if not databento_acknowledge(cost, force=args.force):
        print("Download cancelled.")
        return 0

    print()
    print("=" * 70)
    print("DOWNLOADING")
    print("=" * 70)

    totals = {"downloaded": 0, "failed": 0, "rows": 0, "skipped": 0}
    for product in products_needing_update:
        stats = download_product(client, config, product, data_dir, dry_run=False)
        for key in totals:
            totals[key] += stats[key]

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Contracts downloaded: {totals['downloaded']}")
    print(f"Contracts skipped:    {totals['skipped']}")
    print(f"Contracts failed:     {totals['failed']}")
    print(f"Total rows:           {totals['rows']:,}")

    return 0


if __name__ == "__main__":
    exit(main())
