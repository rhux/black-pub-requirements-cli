"""Orchestrates ONE scout's acquisition: opens a gateway session, fetches the schedule, dedupes
classes, fetches+validates each class's requirements with per-request retry, and returns a
ScoutResult. Preserves DOM name discovery, the full raw envelopes, the requirement-status check,
and HTML-cleaned descriptions -- all of which process_scout's current body does and which an
earlier draft of this service silently dropped.

Every raw/ write goes through the injected ArtifactSink (self.sink.publish_text), never
Path.write_text() directly -- matching exactly how features/reporting/service.py's
ReportingService routes every content write through its own injected sink while still calling
.mkdir(parents=True, exist_ok=True) itself (directory creation is orchestration; writing content
is the adapter's job).

Does NOT own the circuit breaker's check_closed()/record_failure()/record_success() calls, and
does NOT touch the checkpoint store -- both are batch-level decisions (features/acquisition/
batch.py, Task B5.5) that only make sense with visibility across an entire run's scouts, not one
scout in isolation.

Does NOT import scoutmb.adapters.scoutevent.schema (or any adapter) -- an earlier draft called
validate_requirement_row directly from this features/ module, which is a features->adapters
edge the dependency rule forbids. Row validation now happens INSIDE the gateway
(adapters/scoutevent/playwright_gateway.py's fetch_requirements, an adapter-to-adapter import,
which is allowed); this service receives an already-validated RequirementFetchResult and only
folds its row_errors into ScoutResult.errors -- it never touches a raw requirement row."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scoutmb.core.identity import AttendeeId, RunIdentity, attendee_filename_stem, safe_slug
from scoutmb.core.models import ClassRecord, RequirementRecord, ScoutInput, ScoutResult
from scoutmb.features.acquisition.retry import RetryPolicy
from scoutmb.ports.artifact_sink import ArtifactSink
from scoutmb.ports.scoutevent import RequirementFetchResult, ScoutingEventGateway


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _days_from_class_name(class_name: str) -> str:
    if " - " in class_name:
        return class_name.split(" - ", 1)[0].strip()
    return ""


def _json_dump(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    timeout_seconds: int
    request_delay_ms: int


@dataclass(frozen=True, slots=True)
class AcquisitionService:
    gateway: ScoutingEventGateway
    retry_policy: RetryPolicy
    sink: ArtifactSink

    async def process(
        self,
        *,
        scout: ScoutInput,
        config: AcquisitionConfig,
        raw_dir: Path,
        run_identity: RunIdentity,
    ) -> ScoutResult:
        name = scout.name or "Unknown Scout"
        attendee_id = ""
        classes: list[ClassRecord] = []
        requirements: list[RequirementRecord] = []
        errors: list[str] = []

        try:
            async with self.gateway.open_session() as session:
                schedule = await session.fetch_schedule(
                    scout.url, config.timeout_seconds, scout.name
                )
                attendee_id = schedule.attendee_id
                if not attendee_id:
                    raise RuntimeError("The schedule request did not contain attendeeID")
                name = schedule.display_name

                raw_dir.mkdir(parents=True, exist_ok=True)
                output_id = run_identity.output_id(AttendeeId.parse(attendee_id, name))
                slug = attendee_filename_stem(name, output_id)
                self.sink.publish_text(
                    raw_dir / f"{slug}-schedule.json", _json_dump(schedule.payload), encoding="utf-8"
                )

                if int((schedule.payload.get("status") or {}).get("status", 0)) != 1:
                    raise RuntimeError(
                        f"Schedule API returned failure: {schedule.payload.get('status')}"
                    )

                schedule_rows = schedule.payload.get("data") or []
                deduped: dict[str, dict[str, Any]] = {}
                order: list[str] = []
                for item in schedule_rows:
                    key = str(item.get("classP4ID") or "")
                    if not key:
                        key = f"__no_id_{len(order)}"
                        deduped[key] = dict(item)
                        order.append(key)
                    elif key not in deduped:
                        deduped[key] = dict(item)
                        order.append(key)
                    elif _truthy(item.get("CLASS_COMPLETED")) and not _truthy(
                        deduped[key].get("CLASS_COMPLETED")
                    ):
                        deduped[key] = dict(item)

                for item in (deduped[key] for key in order):
                    raw_class_name = str(item.get("CLASS_NAME") or "")
                    class_record = ClassRecord(
                        scout_name=name,
                        attendee_id=attendee_id,
                        class_number=str(item.get("CLASS_NBR") or ""),
                        class_p4_id=str(item.get("classP4ID") or ""),
                        class_name=str(item.get("CLASS_NAME_ONLY") or ""),
                        days=_days_from_class_name(raw_class_name),
                        period_name=str(item.get("PERIOD_NAME") or ""),
                        start_time=str(item.get("CLASS_STIME") or ""),
                        start_time_24h=str(item.get("STIME") or ""),
                        location=str(item.get("LOCATION_ROOM_NAME") or ""),
                        has_requirements=_truthy(item.get("HAS_REQ")),
                        class_completed=_truthy(item.get("CLASS_COMPLETED")),
                        raw_class_name=raw_class_name,
                    )
                    classes.append(class_record)

                    # ACQ-HASREQ-002: skip the requirement fetch entirely when HAS_REQ='0',
                    # instead of issuing it and relying on the response being empty.
                    if not class_record.class_p4_id or not class_record.has_requirements:
                        continue

                    requirement_result: RequirementFetchResult | None = None
                    last_error: Exception | None = None
                    for attempt in range(1, 4):
                        try:
                            requirement_result = await session.fetch_requirements(
                                attendee_id, class_record.class_p4_id
                            )
                            break
                        except TypeError:
                            # Not a network/fetch failure -- e.g. a non-list "data" value in an
                            # otherwise-successful response (ACQ-REQ-006). Legacy's retry loop
                            # only ever wraps the network call itself; row iteration happens
                            # AFTER that loop succeeds, so a shape error there escapes uncaught
                            # to process_scout's OUTER handler, aborting the whole scout rather
                            # than being retried. Re-raising here (instead of retrying) matches
                            # that split exactly.
                            raise
                        except Exception as exc:
                            last_error = exc
                            await self.retry_policy.wait_after_failure(attempt)

                    if requirement_result is None:
                        errors.append(
                            f"{class_record.class_name}: requirement request failed: {last_error}"
                        )
                        continue

                    self.sink.publish_text(
                        raw_dir
                        / f"{slug}-{safe_slug(class_record.class_number or class_record.class_p4_id)}-requirements.json",
                        _json_dump(requirement_result.payload),
                        encoding="utf-8",
                    )

                    if int((requirement_result.payload.get("status") or {}).get("status", 0)) != 1:
                        errors.append(
                            f"{class_record.class_name}: requirement API returned failure: "
                            f"{requirement_result.payload.get('status')}"
                        )
                        continue

                    errors.extend(f"{class_record.class_name}: {msg}" for msg in requirement_result.row_errors)

                    for validated in requirement_result.validated_rows:
                        requirements.append(
                            RequirementRecord(
                                scout_name=name,
                                attendee_id=attendee_id,
                                class_number=class_record.class_number,
                                class_p4_id=class_record.class_p4_id,
                                merit_badge_name=validated["merit_badge_name"],
                                requirement_id=validated["requirement_id"],
                                requirement_type_id=validated["requirement_type_id"],
                                requirement_number=validated["requirement_number"],
                                description=validated["description"],
                                completed_requirement=validated["completed_requirement"],
                                completed_class=validated["completed_class"],
                                requirement_on_event=validated["requirement_on_event"],
                                present_days=validated["present_days"],
                            )
                        )

                    if config.request_delay_ms > 0:
                        await self.retry_policy.sleeper.sleep(config.request_delay_ms / 1000)

        except Exception as exc:
            errors.append(str(exc))

        return ScoutResult(
            name=name,
            qr_url=scout.url,
            attendee_id=attendee_id,
            classes=tuple(classes),
            requirements=tuple(requirements),
            errors=tuple(errors),
        )
