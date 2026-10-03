import threading
from collections.abc import Iterator

import pytest
from sound_effects_studio.config import Paths
from sound_effects_studio.db import Database
from sound_effects_studio.errors import ConflictError, InvalidError, NotFoundError
from sound_effects_studio.models import (
    AuditionTarget,
    BulkSet,
    CategoryCreate,
    CategoryUpdate,
    OriginalInfo,
    ProfileCreate,
    ProfileUpdate,
    Published,
    Recipe,
    SeasonCreate,
    SeasonUpdate,
    SelectionEvent,
    Settings,
    Sound,
    SoundUpdate,
)
from sound_effects_studio.repository import Repository

pytestmark = pytest.mark.studio


@pytest.fixture
def repo(paths: Paths) -> Iterator[Repository]:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(paths.database_path)
    yield Repository(db)
    db.close()


def make_sound(repo: Repository, **overrides: object) -> Sound:
    args: dict[str, object] = {
        "category_id": "general",
        "title": "Boo",
        "key": "boo.mp3",
        "tags": [],
        "seasons": ["regular"],
        "all_seasons": False,
        "recipe": Recipe(),
        "original": None,
    }
    args.update(overrides)
    return repo.create_sound(**args)  # type: ignore[arg-type]


def make_published(revision: int = 1) -> Published:
    return Published(
        revision=revision,
        filename=f"x-r{revision}.mp3",
        duration=1.5,
        loudness_lufs=-16.0,
        true_peak_db=-1.5,
        size=1234,
        published_at="2026-10-03T12:00:00Z",
    )


def make_original() -> OriginalInfo:
    return OriginalInfo(
        filename="boo.mp3",
        size=1000,
        format="mp3",
        codec="mp3",
        duration=3.0,
        sample_rate=44100,
        channels=2,
    )


# --- seeds -----------------------------------------------------------------------------------


def test_seeds(repo: Repository) -> None:
    assert [s.id for s in repo.list_seasons()] == ["regular"]
    assert {p.id for p in repo.list_profiles()} == {"standard", "loud", "soft", "voice"}
    assert [c.id for c in repo.list_categories()] == ["general"]
    assert repo.catalog_revision() == 0


def test_seed_values(repo: Repository) -> None:
    regular = repo.get_season("regular")
    assert (regular.name, regular.color, regular.icon) == (
        "Regular",
        "#64748b",
        "mdi:calendar-blank",
    )
    assert (regular.start, regular.end, regular.priority, regular.builtin) == (None, None, 0, True)
    profiles = {p.id: (p.target_lufs, p.true_peak, p.lra) for p in repo.list_profiles()}
    assert profiles == {
        "standard": (-16, -1.5, 11),
        "loud": (-13, -1.0, 11),
        "soft": (-20, -1.5, 11),
        "voice": (-18, -1.5, 7),
    }
    general = repo.get_category("general")
    assert (general.name, general.icon, general.color) == ("General", "mdi:music-note", "#8b5cf6")
    assert general.default_profile_id is None
    assert repo.get_settings() == Settings(
        max_upload_mb=100, max_duration_s=600, audition_targets=[], media_base_url=""
    )


# --- revision and notifications --------------------------------------------------------------


def test_category_slug_and_revision(repo: Repository) -> None:
    seen: list[int] = []
    repo._on_catalog_change = seen.append  # type: ignore[attr-defined]
    category = repo.create_category(CategoryCreate(name="León Infinito"))
    assert category.id == "leon_infinito"
    assert repo.catalog_revision() == 1
    assert seen == [1]
    with pytest.raises(ConflictError):
        repo.create_category(CategoryCreate(name="León Infinito"))
    assert seen == [1]


def test_category_slug_with_spaces(repo: Repository) -> None:
    assert repo.create_category(CategoryCreate(name="Intro Entrada")).id == "intro_entrada"


def test_revision_increments_on_catalog_writes(repo: Repository) -> None:
    repo.create_category(CategoryCreate(name="Doors"))
    assert repo.catalog_revision() == 1

    repo.update_season("regular", SeasonUpdate(name="Everyday"))
    assert repo.catalog_revision() == 2

    sound = make_sound(repo)
    before = repo.catalog_revision()
    repo.set_published(sound.id, make_published())
    assert repo.catalog_revision() == before + 1

    before = repo.catalog_revision()
    assert repo.bulk_update([sound.id], BulkSet(enabled=False)) == 1
    assert repo.catalog_revision() == before + 1

    before = repo.catalog_revision()
    repo.delete_sound(sound.id)
    assert repo.catalog_revision() == before + 1


def test_revision_not_bumped_by_selections_profiles_settings_and_transient_states(
    repo: Repository,
) -> None:
    sound = make_sound(repo)
    revision = repo.catalog_revision()
    repo.record_selections(
        [
            SelectionEvent(
                sound_id=sound.id,
                category_id="general",
                season_id="regular",
                selected_at="2026-10-03T12:00:00Z",
            )
        ]
    )
    repo.update_profile("standard", ProfileUpdate(name="Std"))
    repo.create_profile(ProfileCreate(name="Mine", target_lufs=-15, true_peak=-1, lra=9))
    repo.delete_profile("mine")
    repo.update_settings(Settings(max_upload_mb=5))
    repo.set_status(sound.id, "processing")
    repo.set_status(sound.id, "rendering")
    repo.set_has_preview(sound.id, True)
    assert repo.catalog_revision() == revision


def test_on_catalog_change_runs_after_commit(paths: Paths) -> None:
    db = Database(paths.database_path)
    observed: list[tuple[int, int]] = []

    def on_change(revision: int) -> None:
        stored = db.connection.execute(
            "SELECT value FROM meta WHERE key = 'catalog_revision'"
        ).fetchone()
        observed.append((revision, int(stored["value"])))
        assert not db.connection.in_transaction

    repo = Repository(db, on_change)
    repo.create_category(CategoryCreate(name="Doors"))
    repo.create_season(SeasonCreate(name="Spring", start="03-20", end="06-20"))
    assert observed == [(1, 1), (2, 2)]
    db.close()


def test_failed_write_does_not_bump_or_notify(repo: Repository) -> None:
    seen: list[int] = []
    repo._on_catalog_change = seen.append  # type: ignore[attr-defined]
    with pytest.raises(InvalidError):
        repo.create_season(SeasonCreate(name="Bad", start="13-40", end="10-31"))
    assert repo.catalog_revision() == 0
    assert seen == []


def test_failing_notification_callback_does_not_break_writes(repo: Repository) -> None:
    def boom(revision: int) -> None:
        raise RuntimeError("listener failed")

    repo._on_catalog_change = boom  # type: ignore[attr-defined]
    assert repo.create_category(CategoryCreate(name="Doors")).id == "doors"
    assert repo.catalog_revision() == 1


# --- seasons ---------------------------------------------------------------------------------


def test_create_season_roundtrip_and_order(repo: Repository) -> None:
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31", priority=10))
    repo.create_season(SeasonCreate(name="Christmas", start="12-01", end="01-06", priority=20))
    repo.create_season(SeasonCreate(name="Anniversary", start="02-29", end="03-01", priority=10))
    seasons = repo.list_seasons()
    assert [s.id for s in seasons] == ["regular", "christmas", "anniversary", "halloween"]
    halloween = repo.get_season("halloween")
    assert (halloween.start, halloween.end, halloween.priority, halloween.builtin) == (
        "10-01",
        "10-31",
        10,
        False,
    )


def test_season_explicit_id_and_duplicates(repo: Repository) -> None:
    season = repo.create_season(SeasonCreate(id="xmas", name="Xmas", start="12-01", end="12-31"))
    assert season.id == "xmas"
    with pytest.raises(ConflictError):
        repo.create_season(SeasonCreate(id="xmas", name="Other", start="01-01", end="01-02"))
    with pytest.raises(ConflictError):
        repo.create_season(SeasonCreate(name="Regular", start="01-01", end="01-02"))
    with pytest.raises(InvalidError):
        repo.create_season(SeasonCreate(id="Not A Slug!", name="x", start="01-01", end="01-02"))


def test_invalid_season_dates(repo: Repository) -> None:
    with pytest.raises(InvalidError):
        repo.create_season(SeasonCreate(name="Bad", start="13-40", end="10-31"))
    with pytest.raises(InvalidError):
        repo.create_season(SeasonCreate(name="Bad", start="10-01", end="1-5"))
    with pytest.raises(InvalidError):
        repo.create_season(SeasonCreate(name="Bad", start="02-30", end="03-01"))
    repo.create_season(SeasonCreate(name="Leap", start="02-29", end="02-29"))
    with pytest.raises(InvalidError):
        repo.update_season("leap", SeasonUpdate(start="13-40"))
    with pytest.raises(InvalidError):
        repo.update_season("leap", SeasonUpdate(end=None))


def test_update_season(repo: Repository) -> None:
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31", priority=10))
    updated = repo.update_season(
        "halloween", SeasonUpdate(name="Spooky", color="#f97316", end="11-02", priority=15)
    )
    assert (updated.name, updated.color, updated.start, updated.end, updated.priority) == (
        "Spooky",
        "#f97316",
        "10-01",
        "11-02",
        15,
    )
    with pytest.raises(NotFoundError):
        repo.update_season("nope", SeasonUpdate(name="x"))


def test_regular_season_only_allows_cosmetic_updates(repo: Repository) -> None:
    updated = repo.update_season("regular", SeasonUpdate(name="Everyday", color="#111111"))
    assert (updated.name, updated.color, updated.start, updated.end) == (
        "Everyday",
        "#111111",
        None,
        None,
    )
    with pytest.raises(InvalidError):
        repo.update_season("regular", SeasonUpdate(start="01-01", end="12-31"))
    with pytest.raises(InvalidError):
        repo.update_season("regular", SeasonUpdate(priority=5))
    # Sending the unchanged values is harmless.
    assert repo.update_season("regular", SeasonUpdate(start=None, priority=0)).id == "regular"


def test_regular_cannot_be_deleted(repo: Repository) -> None:
    with pytest.raises(InvalidError):
        repo.delete_season("regular")


def test_delete_unknown_season(repo: Repository) -> None:
    with pytest.raises(NotFoundError):
        repo.delete_season("nope")


def test_deleting_season_falls_back_to_regular(repo: Repository) -> None:
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31", priority=10))
    sound = repo.create_sound(
        category_id="general",
        title="Boo",
        key="boo.mp3",
        tags=[],
        seasons=["halloween"],
        all_seasons=False,
        recipe=Recipe(),
        original=None,
    )
    repo.delete_season("halloween")
    assert repo.get_sound(sound.id).seasons == ["regular"]


def test_deleting_season_keeps_other_seasons(repo: Repository) -> None:
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31"))
    both = make_sound(repo, seasons=["regular", "halloween"])
    untouched = make_sound(repo, seasons=["regular"])
    everywhere = make_sound(repo, seasons=[], all_seasons=True)
    repo.delete_season("halloween")
    assert repo.get_sound(both.id).seasons == ["regular"]
    assert repo.get_sound(untouched.id).seasons == ["regular"]
    assert repo.get_sound(everywhere.id).seasons == []


# --- categories ------------------------------------------------------------------------------


def test_category_defaults_and_order(repo: Repository) -> None:
    doors = repo.create_category(CategoryCreate(name="Doors"))
    assert (doors.icon, doors.color, doors.description, doors.default_profile_id) == (
        "mdi:music-note",
        "#8b5cf6",
        "",
        None,
    )
    alarms = repo.create_category(CategoryCreate(name="Alarms", default_profile_id="loud"))
    assert alarms.default_profile_id == "loud"
    assert [c.id for c in repo.list_categories()] == ["general", "doors", "alarms"]
    assert [c.sort_order for c in repo.list_categories()] == [0, 1, 2]


def test_update_category(repo: Repository) -> None:
    repo.create_category(CategoryCreate(name="Doors", default_profile_id="loud"))
    updated = repo.update_category(
        "doors", CategoryUpdate(name="Gates", description="Open and close")
    )
    assert (updated.name, updated.description, updated.default_profile_id) == (
        "Gates",
        "Open and close",
        "loud",
    )
    cleared = repo.update_category("doors", CategoryUpdate(default_profile_id=None))
    assert cleared.default_profile_id is None
    with pytest.raises(InvalidError):
        repo.update_category("doors", CategoryUpdate(default_profile_id="missing"))
    with pytest.raises(NotFoundError):
        repo.update_category("missing", CategoryUpdate(name="x"))


def test_category_with_unknown_default_profile(repo: Repository) -> None:
    with pytest.raises(InvalidError):
        repo.create_category(CategoryCreate(name="Doors", default_profile_id="missing"))


def test_reorder_categories(repo: Repository) -> None:
    repo.create_category(CategoryCreate(name="Doors"))
    repo.create_category(CategoryCreate(name="Alarms"))
    reordered = repo.reorder_categories(["alarms", "general"])
    assert [c.id for c in reordered] == ["alarms", "general", "doors"]
    assert [c.sort_order for c in reordered] == [0, 1, 2]
    with pytest.raises(NotFoundError):
        repo.reorder_categories(["missing"])
    with pytest.raises(InvalidError):
        repo.reorder_categories(["doors", "doors"])


def test_delete_category_with_sounds_conflicts(repo: Repository) -> None:
    sound = make_sound(repo)
    with pytest.raises(ConflictError):
        repo.delete_category("general")
    repo.delete_sound(sound.id)
    repo.delete_category("general")
    assert repo.list_categories() == []
    with pytest.raises(NotFoundError):
        repo.delete_category("general")


# --- profiles --------------------------------------------------------------------------------


def test_profile_crud(repo: Repository) -> None:
    profile = repo.create_profile(
        ProfileCreate(name="Night Mode", target_lufs=-22, true_peak=-2, lra=8)
    )
    assert (profile.id, profile.target_lufs, profile.true_peak, profile.lra) == (
        "night_mode",
        -22,
        -2,
        8,
    )
    with pytest.raises(ConflictError):
        repo.create_profile(ProfileCreate(name="Night Mode", target_lufs=-22, true_peak=-2, lra=8))
    updated, affected = repo.update_profile("night_mode", ProfileUpdate(target_lufs=-23))
    assert updated.target_lufs == -23
    assert affected == []
    repo.delete_profile("night_mode")
    with pytest.raises(NotFoundError):
        repo.get_profile("night_mode")


def test_profile_delete_conflicts_when_used(repo: Repository) -> None:
    sound = make_sound(repo, recipe=Recipe(profile_id="loud"))
    with pytest.raises(ConflictError):
        repo.delete_profile("loud")
    repo.set_recipe(sound.id, Recipe())
    repo.delete_profile("loud")

    repo.create_category(CategoryCreate(name="Doors", default_profile_id="soft"))
    with pytest.raises(ConflictError):
        repo.delete_profile("soft")


def test_update_profile_returns_affected_sound_ids(repo: Repository) -> None:
    first = make_sound(repo, recipe=Recipe(profile_id="voice"))
    second = make_sound(repo, recipe=Recipe(profile_id="voice", gain_db=2))
    make_sound(repo, recipe=Recipe(profile_id="loud"))
    make_sound(repo)
    profile, affected = repo.update_profile("voice", ProfileUpdate(lra=9))
    assert profile.lra == 9
    assert affected == [first.id, second.id]
    assert repo.sounds_using_profile("voice") == [first.id, second.id]


# --- sounds ----------------------------------------------------------------------------------


def test_create_sound_defaults(repo: Repository) -> None:
    sound = make_sound(repo, original=make_original(), recipe=Recipe(profile_id="standard"))
    assert len(sound.id) == 12
    assert sound.status == "processing"
    assert sound.enabled is True
    assert (sound.notes, sound.error, sound.published) == ("", None, None)
    assert (sound.selection_count, sound.last_selected_at, sound.has_preview) == (0, None, False)
    assert sound.created_at == sound.updated_at
    assert sound.original == make_original()
    assert sound.recipe.profile_id == "standard"
    assert repo.get_sound(sound.id) == sound
    assert repo.list_sounds() == [sound]


def test_sound_validation(repo: Repository) -> None:
    with pytest.raises(InvalidError):
        make_sound(repo, category_id="missing")
    with pytest.raises(InvalidError):
        make_sound(repo, seasons=["missing"])
    with pytest.raises(InvalidError):
        make_sound(repo, seasons=[], all_seasons=False)
    with pytest.raises(InvalidError):
        make_sound(repo, recipe=Recipe(profile_id="missing"))
    with pytest.raises(InvalidError):
        make_sound(repo, title="   ")
    assert make_sound(repo, seasons=[], all_seasons=True).all_seasons is True
    assert repo.list_sounds()[0].seasons == []


def test_tags_normalized(repo: Repository) -> None:
    sound = make_sound(repo, tags=["ES", "es", " En ", ""])
    assert sound.tags == ["en", "es"]
    updated = repo.update_sound(sound.id, SoundUpdate(tags=["Pt Br", "ES"]))
    assert updated.tags == ["es", "pt_br"]


def test_get_unknown_sound(repo: Repository) -> None:
    with pytest.raises(NotFoundError):
        repo.get_sound("nope")
    with pytest.raises(NotFoundError):
        repo.delete_sound("nope")
    with pytest.raises(NotFoundError):
        repo.set_status("nope", "ready")


def test_update_sound(repo: Repository) -> None:
    repo.create_category(CategoryCreate(name="Doors"))
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31"))
    sound = make_sound(repo)
    updated = repo.update_sound(
        sound.id,
        SoundUpdate(
            title="Creak",
            category_id="doors",
            key="creak.wav",
            seasons=["halloween", "regular", "halloween"],
            enabled=False,
            notes="  spooky ",
        ),
    )
    assert (updated.title, updated.category_id, updated.key) == ("Creak", "doors", "creak.wav")
    assert updated.seasons == ["halloween", "regular"]
    assert (updated.enabled, updated.notes, updated.all_seasons) == (False, "  spooky ", False)
    assert updated.updated_at >= sound.updated_at
    with pytest.raises(InvalidError):
        repo.update_sound(sound.id, SoundUpdate(category_id="missing"))
    with pytest.raises(InvalidError):
        repo.update_sound(sound.id, SoundUpdate(seasons=[]))
    with pytest.raises(InvalidError):
        repo.update_sound(sound.id, SoundUpdate(seasons=["missing"]))
    assert repo.update_sound(sound.id, SoundUpdate(seasons=[], all_seasons=True)).seasons == []


def test_set_recipe_original_status_and_preview(repo: Repository) -> None:
    sound = make_sound(repo)
    assert repo.set_recipe(sound.id, Recipe(trim_start=1, gain_db=3)).recipe.gain_db == 3
    with pytest.raises(InvalidError):
        repo.set_recipe(sound.id, Recipe(profile_id="missing"))
    assert repo.set_original(sound.id, make_original()).original == make_original()
    failed = repo.set_status(sound.id, "failed", "ffmpeg exploded")
    assert (failed.status, failed.error) == ("failed", "ffmpeg exploded")
    rendering = repo.set_status(sound.id, "rendering")
    assert (rendering.status, rendering.error) == ("rendering", None)
    repo.set_has_preview(sound.id, True)
    assert repo.get_sound(sound.id).has_preview is True
    repo.set_has_preview(sound.id, False)
    assert repo.get_sound(sound.id).has_preview is False


def test_set_published_marks_ready(repo: Repository) -> None:
    sound = make_sound(repo)
    repo.set_status(sound.id, "failed", "boom")
    published = repo.set_published(sound.id, make_published(2))
    assert published.status == "ready"
    assert published.error is None
    assert published.published == make_published(2)
    assert published.published is not None
    assert published.published.mime_type == "audio/mpeg"


def test_bulk_update(repo: Repository) -> None:
    repo.create_category(CategoryCreate(name="Doors"))
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31"))
    first = make_sound(repo, tags=["es", "old"])
    second = make_sound(repo, tags=["en"])
    updated = repo.bulk_update(
        [first.id, second.id, "missing"],
        BulkSet(
            category_id="doors",
            seasons=["halloween"],
            add_tags=["New", "es"],
            remove_tags=["old"],
            enabled=False,
        ),
    )
    assert updated == 2
    for sound_id in (first.id, second.id):
        sound = repo.get_sound(sound_id)
        assert (sound.category_id, sound.seasons, sound.enabled) == ("doors", ["halloween"], False)
    assert repo.get_sound(first.id).tags == ["es", "new"]
    assert repo.get_sound(second.id).tags == ["en", "es", "new"]


def test_bulk_update_is_atomic(repo: Repository) -> None:
    first = make_sound(repo, tags=["a"])
    revision = repo.catalog_revision()
    with pytest.raises(InvalidError):
        repo.bulk_update([first.id], BulkSet(category_id="missing", add_tags=["b"]))
    assert repo.get_sound(first.id).tags == ["a"]
    assert repo.catalog_revision() == revision


def test_bulk_update_without_metadata_changes_nothing(repo: Repository) -> None:
    first = make_sound(repo)
    revision = repo.catalog_revision()
    assert repo.bulk_update([first.id, "missing"], BulkSet(profile_id="loud")) == 1
    assert repo.bulk_update([], BulkSet(enabled=False)) == 0
    assert repo.catalog_revision() == revision


def test_record_selections(repo: Repository) -> None:
    sound = make_sound(repo)

    def event(sound_id: str, at: str) -> SelectionEvent:
        return SelectionEvent(
            sound_id=sound_id, category_id="general", season_id="regular", selected_at=at
        )

    repo.record_selections(
        [
            event(sound.id, "2026-10-03T12:00:00Z"),
            event(sound.id, "2026-10-03T13:00:00Z"),
            event("missing", "2026-10-03T13:00:00Z"),
            event(sound.id, "2026-10-03T11:00:00Z"),
        ]
    )
    stored = repo.get_sound(sound.id)
    assert stored.selection_count == 3
    assert stored.last_selected_at == "2026-10-03T13:00:00Z"


# --- settings --------------------------------------------------------------------------------


def test_settings_roundtrip(repo: Repository) -> None:
    settings = Settings(
        max_upload_mb=20,
        max_duration_s=60,
        audition_targets=[
            AuditionTarget(
                id="kitchen",
                label="Kitchen",
                kind="media_player",
                entity_id="media_player.kitchen",
                volume=0.4,
            )
        ],
        media_base_url="http://ha.local:8123",
    )
    assert repo.update_settings(settings) == settings
    assert repo.get_settings() == settings


# --- catalog document ------------------------------------------------------------------------


def test_catalog_document_shape(repo: Repository) -> None:
    repo.create_season(SeasonCreate(name="Halloween", start="10-01", end="10-31", priority=10))
    published = make_sound(repo, title="Published", seasons=["halloween"], tags=["es"])
    make_sound(repo, title="Draft")
    repo.set_published(published.id, make_published(3))
    document = repo.catalog_document()

    assert set(document) == {"revision", "generated_at", "seasons", "categories", "sounds"}
    assert document["revision"] == repo.catalog_revision()
    generated_at = document["generated_at"]
    assert isinstance(generated_at, str)
    assert generated_at.endswith("Z")
    assert len(generated_at) == 20

    seasons = document["seasons"]
    assert isinstance(seasons, list)
    assert [s["id"] for s in seasons] == ["regular", "halloween"]
    for season in seasons:
        assert set(season) == {"id", "name", "color", "icon", "start", "end", "priority"}

    categories = document["categories"]
    assert isinstance(categories, list)
    assert set(categories[0]) == {"id", "name", "icon", "color", "description", "sort_order"}

    sounds = document["sounds"]
    assert isinstance(sounds, list)
    assert len(sounds) == 1
    assert sounds[0] == {
        "id": published.id,
        "category_id": "general",
        "title": "Published",
        "key": "boo.mp3",
        "tags": ["es"],
        "seasons": ["halloween"],
        "all_seasons": False,
        "enabled": True,
        "published": {
            "revision": 3,
            "filename": "x-r3.mp3",
            "duration": 1.5,
            "mime_type": "audio/mpeg",
        },
    }


def test_catalog_document_keeps_disabled_sounds(repo: Repository) -> None:
    sound = make_sound(repo)
    repo.set_published(sound.id, make_published())
    repo.update_sound(sound.id, SoundUpdate(enabled=False))
    sounds = repo.catalog_document()["sounds"]
    assert isinstance(sounds, list)
    assert [(s["id"], s["enabled"]) for s in sounds] == [(sound.id, False)]


# --- Recipe ----------------------------------------------------------------------------------


def test_recipe_identity() -> None:
    assert Recipe().is_identity() is True
    assert Recipe(gain_db=1).is_identity() is False
    assert Recipe(profile_id="loud").is_identity() is False
    assert Recipe(trim_end=2).is_identity() is False
    assert Recipe(fade_in=0.1).is_identity() is False


def test_recipe_validate_for_accepts_valid_recipes() -> None:
    Recipe().validate_for(10)
    Recipe(trim_start=1, trim_end=9, fade_in=4, fade_out=4).validate_for(10)
    Recipe(fade_in=5, fade_out=5).validate_for(10)
    Recipe(trim_end=10.04).validate_for(10)


@pytest.mark.parametrize(
    "recipe",
    [
        Recipe(trim_start=5, trim_end=5),
        Recipe(trim_start=6, trim_end=5),
        Recipe(trim_end=10.06),
        Recipe(trim_start=10),
        Recipe(trim_start=12),
        Recipe(fade_in=6, fade_out=5),
        Recipe(trim_start=2, trim_end=6, fade_in=2.5, fade_out=2.5),
    ],
)
def test_recipe_validate_for_rejects(recipe: Recipe) -> None:
    with pytest.raises(InvalidError) as caught:
        recipe.validate_for(10)
    assert str(caught.value)


# --- threading -------------------------------------------------------------------------------


def test_repository_is_safe_from_worker_threads(repo: Repository) -> None:
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for item in range(10):
                make_sound(repo, title=f"t{index}-{item}")
                repo.list_sounds()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(repo.list_sounds()) == 40
    assert repo.catalog_revision() == 40
