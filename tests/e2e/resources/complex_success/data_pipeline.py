import os

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe


###### Justification: vaccination_campaign ######

# -------------------------
# 1) Evidence functions (defined first)
# -------------------------
@jpipe(consume=["press_release_path", "settings"], produce=["press_release"])
def approved_press_release_document(press_release_path: str, settings: dict, produce) -> bool:
    threshold = settings["thresholds"]["pass_size"]
    result = os.path.isfile(press_release_path) and os.path.getsize(press_release_path) > threshold
    produce("press_release", result)
    return result


@jpipe(consume=["social_posts_path", "settings"], produce=["social_posts"])
def set_of_preapproved_social_media_posts_and_graphics(social_posts_path: str, settings: dict, produce) -> bool:
    threshold = settings["thresholds"]["pass_size"]
    result = os.path.isfile(social_posts_path) and os.path.getsize(social_posts_path) > threshold
    produce("social_posts", result)
    return result


@jpipe(consume=["event_calendar_path", "settings"], produce=["event_calendar"])
def list_of_scheduled_events_with_dates_and_venues(event_calendar_path: str, settings: dict, produce) -> bool:
    min_lines = settings["thresholds"]["min_lines"]
    if not os.path.isfile(event_calendar_path):
        produce("event_calendar", False)
        return False
    with open(event_calendar_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    result = len(lines) >= min_lines
    produce("event_calendar", result)
    return result


@jpipe(consume=["speakers_list_path"], produce=["speakers_list"])
def list_of_trained_community_speakers(speakers_list_path: str, produce) -> bool:
    if not os.path.isfile(speakers_list_path):
        produce("speakers_list", False)
        return False
    with open(speakers_list_path, "r", encoding="utf-8") as f:
        speakers = [line.strip() for line in f if line.strip()]
    result = len(speakers) >= 2
    produce("speakers_list", result)
    return result


@jpipe(consume=["fleet_info_path"], produce=["fleet_available"])
def three_operational_mobile_medical_units(fleet_info_path: str, produce) -> bool:
    if not os.path.isfile(fleet_info_path):
        produce("fleet_available", False)
        return False
    with open(fleet_info_path, "r", encoding="utf-8") as f:
        content = f.read().lower()
    result = "3" in content or "three" in content
    produce("fleet_available", result)
    return result


@jpipe(consume=["staff_roster_path"], produce=["trained_staff"])
def roster_of_trained_vaccination_staff_for_mobile_units(staff_roster_path: str, produce) -> bool:
    if not os.path.isfile(staff_roster_path):
        produce("trained_staff", False)
        return False
    with open(staff_roster_path, "r", encoding="utf-8") as f:
        staff = [line.strip() for line in f if line.strip()]
    result = len(staff) >= 5
    produce("trained_staff", result)
    return result


@jpipe(consume=["schedule_plan_path"], produce=["schedule_plan"])
def approved_extendedhours_operation_schedule(schedule_plan_path: str, produce) -> bool:
    result = os.path.isfile(schedule_plan_path) and os.path.getsize(schedule_plan_path) > 20
    produce("schedule_plan", result)
    return result


@jpipe(consume=["leader_commitments_path"], produce=["leader_commitments"])
def written_commitments_from_local_leaders_to_participate(leader_commitments_path: str, produce) -> bool:
    result = os.path.isfile(leader_commitments_path)
    produce("leader_commitments", result)
    return result


@jpipe(consume=["testimonial_videos_path"], produce=["testimonial_videos"])
def recorded_testimonials_from_trusted_figures(testimonial_videos_path: str, produce) -> bool:
    result = os.path.isfile(testimonial_videos_path)
    produce("testimonial_videos", result)
    return result


@jpipe(consume=["safety_report_path"], produce=["safety_report"])
def public_safety_report_approved_by_health_authority(safety_report_path: str, produce) -> bool:
    result = os.path.isfile(safety_report_path) and safety_report_path.lower().endswith(".pdf")
    produce("safety_report", result)
    return result


@jpipe(consume=["faq_document_path"], produce=["faq_document"])
def frequently_asked_questions_document(faq_document_path: str, produce) -> bool:
    result = os.path.isfile(faq_document_path) and os.path.getsize(faq_document_path) > 50
    produce("faq_document", result)
    return result


# -------------------------
# 2) Strategy functions (consume evidence -> produce strategy outputs)
# -------------------------
@jpipe(consume=["press_release", "social_posts"], produce=["media_outreach"])
def distribute_information_through_local_media_and_social_channels(press_release: bool, social_posts: bool,
                                                                   produce) -> bool:
    result = press_release and social_posts
    produce("media_outreach", result)
    return result


@jpipe(consume=["event_calendar", "speakers_list"], produce=["community_events"])
def host_informational_events_in_public_gathering_spaces(event_calendar: bool, speakers_list: bool, produce) -> bool:
    result = event_calendar and speakers_list
    produce("community_events", result)
    return result


@jpipe(consume=["fleet_available", "trained_staff"], produce=["mobile_units"])
def deploy_mobile_vaccination_units_to_remote_areas(fleet_available: bool, trained_staff: bool, produce) -> bool:
    result = fleet_available and trained_staff
    produce("mobile_units", result)
    return result


@jpipe(consume=["schedule_plan"], produce=["extended_hours"])
def keep_vaccination_centers_open_during_evenings_and_weekends(schedule_plan: bool, produce) -> bool:
    produce("extended_hours", schedule_plan)
    return schedule_plan


@jpipe(consume=["leader_commitments", "testimonial_videos"], produce=["trusted_voices"])
def involve_respected_local_leaders_in_advocacy(leader_commitments: bool, testimonial_videos: bool, produce) -> bool:
    result = leader_commitments and testimonial_videos
    produce("trusted_voices", result)
    return result


@jpipe(consume=["safety_report", "faq_document"], produce=["transparent_info"])
def publish_transparent_and_accessible_safety_data(safety_report: bool, faq_document: bool, produce) -> bool:
    result = safety_report and faq_document
    produce("transparent_info", result)
    return result


# -------------------------
# 4) Aggregation strategy (consumes sub-conclusions -> produces multi_pronged)
# -------------------------
@jpipe(
    consume=[
        "media_outreach",
        "community_events",
        "mobile_units",
        "extended_hours",
        "trusted_voices",
        "transparent_info",
    ],
    produce=["multi_pronged"],
)
def use_multiple_coordinated_outreach_and_delivery_approaches(
        media_outreach: bool,
        community_events: bool,
        mobile_units: bool,
        extended_hours: bool,
        trusted_voices: bool,
        transparent_info: bool,
        produce,
) -> bool:
    result = all([
        media_outreach,
        community_events,
        mobile_units,
        extended_hours,
        trusted_voices,
        transparent_info,
    ])
    produce("multi_pronged", result)
    return result


# -------------------------
# 5) Final conclusion
# -------------------------
@jpipe(consume=["multi_pronged"])
def community_vaccination_rate_reaches_85_within_6_months(multi_pronged: bool) -> bool:
    return multi_pronged
