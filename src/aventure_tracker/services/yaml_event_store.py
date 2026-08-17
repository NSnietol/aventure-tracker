"""YAML persistence service for extracted events.

Provides human-readable storage of events with confidence scores,
organized by agency/year/month.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from aventure_tracker.models.extracted_event import ExtractedEvent, FieldConfidence


class YAMLEventStore:
    """Stores and retrieves events in YAML format for human review."""

    def __init__(self, base_dir: Path):
        """Initialize the YAML event store.

        Args:
            base_dir: Base directory for storing events (e.g., data/agencies).
        """
        self.base_dir = Path(base_dir)

    def _get_events_file(self, agency: str, year: int, month: str) -> Path:
        """Get path to events YAML file for agency/year/month.

        Args:
            agency: Agency name (normalized).
            year: Year (e.g., 2026).
            month: Month name in Spanish (e.g., "agosto").

        Returns:
            Path to the events.yaml file.
        """
        return self.base_dir / agency / str(year) / month / "events.yaml"

    def save_events(
        self,
        events: list[ExtractedEvent],
        agency: str,
        year: int,
        month: str,
        merge: bool = True,
    ) -> Path:
        """Save events to YAML file.

        Args:
            events: List of events to save.
            agency: Agency name.
            year: Year.
            month: Month name.
            merge: If True, merge with existing events. If False, overwrite.

        Returns:
            Path to the saved file.
        """
        file_path = self._get_events_file(agency, year, month)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing events if merging
        existing_events: dict[str, ExtractedEvent] = {}
        if merge and file_path.exists():
            loaded = self.load_events(agency, year, month)
            existing_events = {e.event_id: e for e in loaded}

        # Merge new events (new events override existing by event_id)
        for event in events:
            existing_events[event.event_id] = event

        # Sort events by date
        sorted_events = sorted(existing_events.values(), key=lambda e: e.date_start)

        # Build YAML structure with human-readable format
        yaml_data = self._build_yaml_structure(sorted_events, agency, year, month)

        # Write with custom formatting
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self._format_yaml(yaml_data))

        return file_path

    def load_events(self, agency: str, year: int, month: str) -> list[ExtractedEvent]:
        """Load events from YAML file.

        Args:
            agency: Agency name.
            year: Year.
            month: Month name.

        Returns:
            List of ExtractedEvent instances.
        """
        file_path = self._get_events_file(agency, year, month)

        if not file_path.exists():
            return []

        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "events" not in data:
            return []

        events: list[ExtractedEvent] = []
        for event_data in data["events"]:
            events.append(self._parse_event(event_data, agency))

        return events

    def get_event_by_id(
        self, event_id: str, agency: str, year: int, month: str
    ) -> ExtractedEvent | None:
        """Get a specific event by ID.

        Args:
            event_id: Event ID.
            agency: Agency name.
            year: Year.
            month: Month name.

        Returns:
            ExtractedEvent if found, None otherwise.
        """
        events = self.load_events(agency, year, month)
        for event in events:
            if event.event_id == event_id:
                return event
        return None

    def delete_event(self, event_id: str, agency: str, year: int, month: str) -> bool:
        """Delete an event by ID.

        Args:
            event_id: Event ID to delete.
            agency: Agency name.
            year: Year.
            month: Month name.

        Returns:
            True if event was deleted, False if not found.
        """
        events = self.load_events(agency, year, month)
        original_count = len(events)
        events = [e for e in events if e.event_id != event_id]

        if len(events) == original_count:
            return False

        # Save without merge to overwrite
        self.save_events(events, agency, year, month, merge=False)
        return True

    def list_available_months(self, agency: str, year: int | None = None) -> list[dict]:
        """List available months with event counts.

        Args:
            agency: Agency name.
            year: Optional year filter.

        Returns:
            List of dicts with year, month, event_count.
        """
        agency_dir = self.base_dir / agency
        if not agency_dir.exists():
            return []

        results: list[dict] = []

        for year_dir in agency_dir.iterdir():
            if not year_dir.is_dir():
                continue

            try:
                dir_year = int(year_dir.name)
            except ValueError:
                continue

            if year is not None and dir_year != year:
                continue

            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue

                events_file = month_dir / "events.yaml"
                if events_file.exists():
                    events = self.load_events(agency, dir_year, month_dir.name)
                    results.append(
                        {
                            "agency": agency,
                            "year": dir_year,
                            "month": month_dir.name,
                            "event_count": len(events),
                        }
                    )

        return sorted(results, key=lambda x: (x["year"], x["month"]))

    def _build_yaml_structure(
        self,
        events: list[ExtractedEvent],
        agency: str,
        year: int,
        month: str,
    ) -> dict[str, Any]:
        """Build YAML structure with metadata.

        Args:
            events: List of events.
            agency: Agency name.
            year: Year.
            month: Month.

        Returns:
            Dictionary for YAML serialization.
        """
        # Calculate statistics
        total_events = len(events)
        sold_out_count = sum(1 for e in events if e.sold_out)
        needs_review_count = sum(1 for e in events if e.needs_review)

        avg_confidence = 0.0
        if events:
            confidences = [e.overall_confidence for e in events if e.confidence]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)

        return {
            "metadata": {
                "agency": agency,
                "year": year,
                "month": month,
                "generated_at": datetime.now().isoformat(),
                "total_events": total_events,
                "sold_out_count": sold_out_count,
                "needs_review_count": needs_review_count,
                "average_confidence": round(avg_confidence, 2),
            },
            "events": [self._event_to_yaml_dict(e) for e in events],
        }

    def _event_to_yaml_dict(self, event: ExtractedEvent) -> dict[str, Any]:
        """Convert event to YAML-friendly dictionary.

        Args:
            event: Event to convert.

        Returns:
            Dictionary for YAML serialization.
        """
        # Format dates nicely
        if event.is_multi_day:
            date_display = f"{event.date_start.strftime('%d %b')} - {event.date_end.strftime('%d %b %Y')}"
        else:
            date_display = event.date_start.strftime("%d %b %Y")

        result: dict[str, Any] = {
            "name": event.name,
            "date_start": event.date_start.isoformat(),
            "date_end": event.date_end.isoformat(),
            "date_display": date_display,
            "price": event.price,
            "price_display": event.price_formatted,
            "sold_out": event.sold_out,
        }

        # Add confidence info if available
        if event.confidence:
            result["confidence"] = {}
            for field_name, conf in event.confidence.items():
                conf_entry: dict[str, Any] = {
                    "score": conf.percentage,
                    "level": conf.level.value,
                }
                if conf.raw_value:
                    conf_entry["raw"] = conf.raw_value
                if conf.notes:
                    conf_entry["notes"] = conf.notes
                result["confidence"][field_name] = conf_entry

            result["overall_confidence"] = round(event.overall_confidence * 100)
            result["needs_review"] = event.needs_review

        if event.source_image:
            result["source_image"] = str(event.source_image.name)

        return result

    def _parse_event(self, data: dict[str, Any], agency: str) -> ExtractedEvent:
        """Parse event from YAML data.

        Args:
            data: Event data from YAML.
            agency: Agency name.

        Returns:
            ExtractedEvent instance.
        """
        # Parse dates
        date_start = data["date_start"]
        if isinstance(date_start, str):
            date_start = date.fromisoformat(date_start)

        date_end = data.get("date_end", date_start)
        if isinstance(date_end, str):
            date_end = date.fromisoformat(date_end)

        # Parse confidence
        confidence: dict[str, FieldConfidence] = {}
        if "confidence" in data:
            for field_name, conf_data in data["confidence"].items():
                # Score in YAML is percentage (0-100), convert to 0-1
                score = conf_data["score"]
                if score > 1:
                    score = score / 100

                confidence[field_name] = FieldConfidence(
                    field_name=field_name,
                    score=score,
                    raw_value=conf_data.get("raw"),
                    notes=conf_data.get("notes"),
                )

        # Parse source image
        source_image = None
        if "source_image" in data:
            source_image = Path(data["source_image"])

        return ExtractedEvent(
            name=data["name"],
            date_start=date_start,
            date_end=date_end,
            price=data["price"],
            agency=agency,
            sold_out=data.get("sold_out", False),
            confidence=confidence,
            source_image=source_image,
        )

    def _format_yaml(self, data: dict[str, Any]) -> str:
        """Format YAML with custom styling for readability.

        Args:
            data: Data to format.

        Returns:
            Formatted YAML string.
        """
        # Add header comment
        header = """# =============================================================================
# Eventos Extraídos - {agency} - {month} {year}
# =============================================================================
# Este archivo fue generado automáticamente.
# Puedes editar manualmente si encuentras errores.
# Los campos con needs_review: true necesitan verificación.
# =============================================================================

""".format(
            agency=data["metadata"]["agency"].title(),
            month=data["metadata"]["month"].title(),
            year=data["metadata"]["year"],
        )

        yaml_content = yaml.dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

        return header + yaml_content
