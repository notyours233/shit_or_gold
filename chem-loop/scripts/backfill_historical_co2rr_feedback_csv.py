from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


INSERTED_COLUMNS = [
    "faradaic_efficiency",
    "faradaic_efficiency_unit",
    "partial_current_density",
    "partial_current_density_unit",
]


@dataclass(frozen=True)
class MissingFeEntry:
    job_id: str
    job_status: str
    csv_path: str
    csv_row_index: int
    recommendation_job_id: str
    product: str
    partial_current_density: str
    partial_current_density_unit: str
    faradaic_efficiency: str
    faradaic_efficiency_unit: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _map_upload_path(upload_path: str, repo_root: Path) -> Path:
    path = str(upload_path or "").strip()
    if not path:
        return Path("")
    absolute = Path(path)
    if absolute.is_absolute() and absolute.exists():
        return absolute
    if path.startswith("/state/"):
        return repo_root / "state" / path.removeprefix("/state/")
    if absolute.is_absolute():
        return absolute
    return repo_root / absolute


def _state_root(repo_root: Path) -> Path:
    if Path("/state").exists():
        return Path("/state")
    return repo_root / "state"


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except Exception:
        return str(path)


def _load_job_jsons(jobs_root: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for job_json in sorted(jobs_root.glob("*/job.json")):
        try:
            jobs.append(json.loads(job_json.read_text(encoding="utf-8")))
        except Exception:
            continue
    return jobs


def _build_new_headers(headers: list[str]) -> list[str]:
    existing = list(headers)
    missing = [col for col in INSERTED_COLUMNS if col not in existing]
    if not missing:
        return existing
    if "value" in existing:
        idx = existing.index("value")
        return existing[:idx] + missing + existing[idx:]
    return existing + missing


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def _is_co2rr_row(row: dict[str, str]) -> bool:
    return str(row.get("reaction_type") or "").strip().upper() == "CO2RR"


def backfill_jobs(
    *,
    jobs_root: Path,
    repo_root: Path,
    write: bool,
) -> tuple[list[dict[str, Any]], list[MissingFeEntry]]:
    summary: list[dict[str, Any]] = []
    missing_entries: list[MissingFeEntry] = []

    for job in _load_job_jsons(jobs_root):
        if job.get("job_type") != "experience_update":
            continue
        payload = job.get("payload") or {}
        csv_path = _map_upload_path(str(payload.get("upload_path") or ""), repo_root)
        if not csv_path.exists():
            continue

        headers, rows = _read_csv(csv_path)
        co2rr_rows = [row for row in rows if _is_co2rr_row(row)]
        if not co2rr_rows:
            continue

        new_headers = _build_new_headers(headers)
        changed = new_headers != headers
        missing_fe_rows = 0

        for csv_row_index, row in enumerate(rows, start=2):
            if not _is_co2rr_row(row):
                for col in INSERTED_COLUMNS:
                    row.setdefault(col, "")
                continue

            row.setdefault("faradaic_efficiency", "")
            row.setdefault("faradaic_efficiency_unit", "%")
            row.setdefault("partial_current_density", "")
            row.setdefault("partial_current_density_unit", "")

            value = str(row.get("value") or "").strip()
            unit = str(row.get("unit") or "").strip()
            if not str(row.get("partial_current_density") or "").strip() and value:
                row["partial_current_density"] = value
                changed = True
            if not str(row.get("partial_current_density_unit") or "").strip() and unit:
                row["partial_current_density_unit"] = unit
                changed = True
            if not str(row.get("faradaic_efficiency_unit") or "").strip():
                row["faradaic_efficiency_unit"] = "%"
                changed = True

            if not str(row.get("faradaic_efficiency") or "").strip():
                missing_fe_rows += 1
                missing_entries.append(
                    MissingFeEntry(
                        job_id=str(job.get("id") or ""),
                        job_status=str(job.get("status") or ""),
                        csv_path=_display_path(csv_path, repo_root),
                        csv_row_index=csv_row_index,
                        recommendation_job_id=str(row.get("recommendation_job_id") or "").strip(),
                        product=str(row.get("product") or "").strip(),
                        partial_current_density=str(row.get("partial_current_density") or "").strip(),
                        partial_current_density_unit=str(row.get("partial_current_density_unit") or "").strip(),
                        faradaic_efficiency="",
                        faradaic_efficiency_unit=str(row.get("faradaic_efficiency_unit") or "").strip(),
                    )
                )

        backup_path = csv_path.with_suffix(csv_path.suffix + ".pre_co2rr_fe_backfill.bak")
        if write and changed:
            if not backup_path.exists():
                backup_path.write_text(csv_path.read_text(encoding="utf-8-sig"), encoding="utf-8")
            _write_csv(csv_path, new_headers, rows)

        summary.append(
            {
                "job_id": str(job.get("id") or ""),
                "job_status": str(job.get("status") or ""),
                "csv_path": _display_path(csv_path, repo_root),
                "backup_path": _display_path(backup_path, repo_root) if backup_path.exists() else None,
                "co2rr_rows": len(co2rr_rows),
                "missing_fe_rows": missing_fe_rows,
                "headers_before": headers,
                "headers_after": new_headers,
                "changed": changed,
            }
        )

    return summary, missing_entries


def _write_reports(repo_root: Path, summary: list[dict[str, Any]], missing_entries: list[MissingFeEntry]) -> dict[str, str]:
    reports_dir = _state_root(repo_root) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_path = reports_dir / "co2rr_feedback_backfill_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    missing_json_path = reports_dir / "co2rr_feedback_missing_fe_rows.json"
    missing_json_path.write_text(
        json.dumps([asdict(entry) for entry in missing_entries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    missing_csv_path = reports_dir / "co2rr_feedback_missing_fe_rows.csv"
    with missing_csv_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(asdict(missing_entries[0]).keys()) if missing_entries else list(MissingFeEntry.__dataclass_fields__.keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in missing_entries:
            writer.writerow(asdict(entry))

    return {
        "summary_json": str(summary_path),
        "missing_fe_json": str(missing_json_path),
        "missing_fe_csv": str(missing_csv_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical CO2RR feedback CSVs with FE/PCD schema columns.")
    parser.add_argument("--jobs-root", default="state/jobs", help="Path to the jobs root (default: state/jobs)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only; do not modify CSV files")
    args = parser.parse_args()

    repo_root = _repo_root()
    jobs_root = (repo_root / args.jobs_root).resolve()
    summary, missing_entries = backfill_jobs(jobs_root=jobs_root, repo_root=repo_root, write=not args.dry_run)
    report_paths = _write_reports(repo_root, summary, missing_entries)
    print(
        json.dumps(
            {
                "jobs_scanned": len(summary),
                "missing_fe_rows": len(missing_entries),
                "dry_run": bool(args.dry_run),
                "reports": report_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
