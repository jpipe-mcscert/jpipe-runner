"""Step library for complex_success: the vaccination campaign.

Evidence observes the campaign's documents under mock/ and reports what it finds;
strategies judge those observations. The six sub-conclusions and the conclusion are not
bound: each derives its status from its predecessors.
"""

import csv
import json
from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

MOCK = Path("mock")

# Thresholds (v3 read pass_size and min_lines from config.yaml; the others were inline).
MIN_DOCUMENT_SIZE = 50
MIN_SCHEDULE_SIZE = 20
MIN_EVENTS = 3
MIN_SPEAKERS = 2
MIN_FLEET_SIZE = 3
MIN_STAFF = 5


def _missing(path: Path) -> Fail:
    return Fail(f"{path} not found")


def _row_count(path: Path) -> int:
    """Number of data rows in a CSV file with a header line."""
    with path.open(encoding="utf-8", newline="") as stream:
        return sum(1 for row in csv.DictReader(stream) if any(row.values()))


# Evidence: what the campaign has on file.


@evidence("press_release", produces=["press_release_size"])
def approved_press_release_document() -> Outcome:
    """An approved press release is on file."""
    path = MOCK / "press_release.txt"
    if not path.is_file():
        return _missing(path)
    return Pass(press_release_size=path.stat().st_size)


@evidence("social_posts", produces=["social_posts_size"])
def set_of_preapproved_social_media_posts_and_graphics() -> Outcome:
    """A set of pre-approved social media posts is on file."""
    path = MOCK / "social_posts.json"
    if not path.is_file():
        return _missing(path)
    return Pass(social_posts_size=path.stat().st_size)


@evidence("event_calendar", produces=["event_count"])
def list_of_scheduled_events_with_dates_and_venues() -> Outcome:
    """A calendar of scheduled events is on file."""
    path = MOCK / "event_calendar.csv"
    if not path.is_file():
        return _missing(path)
    return Pass(event_count=_row_count(path))


@evidence("speakers_list", produces=["speaker_count"])
def list_of_trained_community_speakers() -> Outcome:
    """A list of trained community speakers is on file."""
    path = MOCK / "speakers_list.csv"
    if not path.is_file():
        return _missing(path)
    return Pass(speaker_count=_row_count(path))


@evidence("fleet_available", produces=["fleet_size"])
def three_operational_mobile_medical_units() -> Outcome:
    """The mobile fleet is described, with its size."""
    path = MOCK / "fleet_info.json"
    if not path.is_file():
        return _missing(path)
    fleet = json.loads(path.read_text(encoding="utf-8"))
    return Pass(fleet_size=fleet["fleet_size"])


@evidence("trained_staff", produces=["staff_count"])
def roster_of_trained_vaccination_staff_for_mobile_units() -> Outcome:
    """A roster of trained vaccination staff is on file."""
    path = MOCK / "staff_roster.csv"
    if not path.is_file():
        return _missing(path)
    return Pass(staff_count=_row_count(path))


@evidence("schedule_plan", produces=["schedule_plan_size"])
def approved_extendedhours_operation_schedule() -> Outcome:
    """An extended-hours operation schedule is on file."""
    path = MOCK / "schedule_plan.txt"
    if not path.is_file():
        return _missing(path)
    return Pass(schedule_plan_size=path.stat().st_size)


@evidence("leader_commitments", produces=["leader_commitments_size"])
def written_commitments_from_local_leaders_to_participate() -> Outcome:
    """Written commitments from local leaders are on file."""
    path = MOCK / "leader_commitments.txt"
    if not path.is_file():
        return _missing(path)
    return Pass(leader_commitments_size=path.stat().st_size)


@evidence("testimonial_videos", produces=["testimonial_count"])
def recorded_testimonials_from_trusted_figures() -> Outcome:
    """A list of recorded testimonials is on file."""
    path = MOCK / "testimonial_videos_list.txt"
    if not path.is_file():
        return _missing(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    return Pass(testimonial_count=sum(1 for line in lines if line.strip()))


@evidence("safety_report", produces=["safety_report_format"])
def public_safety_report_approved_by_health_authority() -> Outcome:
    """A public safety report is on file, in some format."""
    reports = sorted(MOCK.glob("safety_report.*"))
    if not reports:
        return _missing(MOCK / "safety_report.*")
    return Pass(safety_report_format=reports[0].suffix.lower())


@evidence("faq_document", produces=["faq_document_size"])
def frequently_asked_questions_document() -> Outcome:
    """A frequently-asked-questions document is on file."""
    path = MOCK / "faq_document.txt"
    if not path.is_file():
        return _missing(path)
    return Pass(faq_document_size=path.stat().st_size)


# Strategies: is what is on file enough?


@strategy("media_outreach", consumes=["press_release_size", "social_posts_size"])
def distribute_information_through_local_media_and_social_channels(
    press_release_size: int, social_posts_size: int
) -> Outcome:
    """The press release and the social posts are substantial enough to publish."""
    if press_release_size <= MIN_DOCUMENT_SIZE:
        return Fail(f"the press release is only {press_release_size} bytes")
    if social_posts_size <= MIN_DOCUMENT_SIZE:
        return Fail(f"the social posts are only {social_posts_size} bytes")
    return Pass()


@strategy("community_events", consumes=["event_count", "speaker_count"])
def host_informational_events_in_public_gathering_spaces(
    event_count: int, speaker_count: int
) -> Outcome:
    """There are enough events, and enough speakers to staff them."""
    if event_count < MIN_EVENTS:
        return Fail(f"only {event_count} events are scheduled, {MIN_EVENTS} are needed")
    if speaker_count < MIN_SPEAKERS:
        return Fail(f"only {speaker_count} speakers are trained, {MIN_SPEAKERS} are needed")
    return Pass()


@strategy("mobile_units", consumes=["fleet_size", "staff_count"])
def deploy_mobile_vaccination_units_to_remote_areas(fleet_size: int, staff_count: int) -> Outcome:
    """There are enough mobile units, and enough trained staff to run them."""
    if fleet_size < MIN_FLEET_SIZE:
        return Fail(f"only {fleet_size} mobile units, {MIN_FLEET_SIZE} are needed")
    if staff_count < MIN_STAFF:
        return Fail(f"only {staff_count} trained staff, {MIN_STAFF} are needed")
    return Pass()


@strategy("extended_hours", consumes=["schedule_plan_size"])
def keep_vaccination_centers_open_during_evenings_and_weekends(
    schedule_plan_size: int,
) -> Outcome:
    """The extended-hours schedule is more than a placeholder."""
    if schedule_plan_size <= MIN_SCHEDULE_SIZE:
        return Fail(f"the schedule plan is only {schedule_plan_size} bytes")
    return Pass()


@strategy("trusted_voices", consumes=["leader_commitments_size", "testimonial_count"])
def involve_respected_local_leaders_in_advocacy(
    leader_commitments_size: int, testimonial_count: int
) -> Outcome:
    """Local leaders have committed in writing, and testimonials are recorded."""
    if leader_commitments_size == 0:
        return Fail("the leader commitments are empty")
    if testimonial_count == 0:
        return Fail("no testimonial is recorded")
    return Pass()


@strategy("transparent_info", consumes=["safety_report_format", "faq_document_size"])
def publish_transparent_and_accessible_safety_data(
    safety_report_format: str, faq_document_size: int
) -> Outcome:
    """The safety report is a PDF and the FAQ is substantial enough to publish."""
    if safety_report_format != ".pdf":
        return Fail(f"the safety report is a {safety_report_format} file, not a PDF")
    if faq_document_size <= MIN_DOCUMENT_SIZE:
        return Fail(f"the FAQ is only {faq_document_size} bytes")
    return Pass()


@strategy("multi_pronged")
def use_multiple_coordinated_outreach_and_delivery_approaches() -> Outcome:
    """The six lines of action combine into one campaign.

    It runs only when its six sub-conclusions passed, so it has nothing left to check.
    """
    return Pass()
