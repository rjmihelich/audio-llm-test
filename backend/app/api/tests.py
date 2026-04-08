"""Test suite configuration API endpoints."""

from __future__ import annotations

import hashlib
import json
import uuid
from itertools import product

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_session
from backend.app.models.speech import SpeechSample
from backend.app.models.test import SweepConfig, TestCase, TestSuite

router = APIRouter()


class FilterSpecConfig(BaseModel):
    filter_type: str  # lpf, hpf, peaking, lowshelf, highshelf
    frequency: float
    Q: float = 0.7071
    gain_db: float = 0.0


class EchoProfileConfig(BaseModel):
    delay_ms_values: list[float] = Field(default=[0, 50, 100, 200])
    gain_db_values: list[float] = Field(default=[-60, -40, -20])
    eq_chains: list[list[FilterSpecConfig]] = Field(default_factory=list)


class AGCConfigRequest(BaseModel):
    target_rms_db: float = -18.0
    attack_ms: float = 50.0
    release_ms: float = 200.0
    max_gain_db: float = 30.0
    compression_ratio: float = 4.0


class AECResidualConfigRequest(BaseModel):
    suppression_db: float = -25.0
    residual_type: str = "mixed"
    nonlinear_distortion: float = 0.3


class NetworkConfigRequest(BaseModel):
    packet_loss_pct: float = 0.0
    packet_loss_pattern: str = "random"
    burst_length_ms: float = 80.0
    jitter_ms: float = 0.0
    codec_switching: bool = False


class FarEndConfig(BaseModel):
    """Far-end (2-way conversation) configuration for telephony testing."""
    enabled: bool = Field(
        default=False,
        description="Enable 2-way conversation with uncorrelated far-end speech",
    )
    speech_level_db_values: list[float] = Field(
        default=[0.0],
        description="Far-end speech gain levels to sweep (dB). 0 = original level.",
    )
    offset_ms_values: list[float] = Field(
        default=[0.0],
        description="Timing offsets (ms). Negative = far-end first (barge-in). 0 = simultaneous.",
    )


class TelephonyConfig(BaseModel):
    """Telephony sweep dimensions — only used when telephony pipeline is selected."""
    bt_codec_types: list[str] = Field(
        default=["none"],
        description='BT codec variants to sweep: "cvsd", "msbc", "none"',
    )
    agc_presets: list[str] = Field(
        default=["off"],
        description='AGC preset names: "off", "mild", "aggressive"',
    )
    aec_configs: list[AECResidualConfigRequest] = Field(
        default_factory=list,
        description="AEC residual configs to sweep. Empty = no AEC simulation.",
    )
    network_configs: list[NetworkConfigRequest] = Field(
        default_factory=list,
        description="Network degradation configs to sweep. Empty = no network impairment.",
    )
    far_end: FarEndConfig = Field(
        default_factory=FarEndConfig,
        description="2-way conversation (far-end speech) configuration.",
    )


class SweepConfigRequest(BaseModel):
    name: str
    description: str = ""
    noise_level_db_values: list[float] = Field(default=[-30, -20, -10, 0])
    speech_level_db_values: list[float] = Field(
        default=[0.0],
        description="Speech gain levels in dB. 0=original, negative=quieter/whisper, positive=louder/shout/overload.",
    )
    noise_types: list[str] = Field(default=["pink_lpf"])
    interferer_level_db_values: list[float | None] = Field(
        default=[0.0],
        description="Relative levels for speech interferer (secondary_voice/babble) in dB. 0=same as speech. null=muted. Only applied when noise_type is secondary_voice or babble.",
    )
    echo: EchoProfileConfig = Field(default_factory=EchoProfileConfig)
    pipelines: list[str] = Field(default=["direct_audio", "asr_text"])
    llm_backends: list[str] = Field(default=[])
    voice_ids: list[str] | None = None
    voice_providers: list[str] | None = None
    voice_languages: list[str] | None = None
    voice_genders: list[str] | None = None
    corpus_categories: list[str] | None = None
    corpus_entry_ids: list[str] | None = None
    system_prompt: str = "You are a helpful in-car voice assistant."
    max_samples: int | None = Field(
        default=None,
        description="Cap the number of speech samples used. None = use all matching samples.",
    )
    telephony: TelephonyConfig | None = Field(
        default=None,
        description="Telephony sweep config. Required when 'telephony' is in pipelines.",
    )


class TestSuiteResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    total_cases: int
    created_at: str
    telephony_enabled: bool = False


class SweepPreview(BaseModel):
    total_cases: int
    breakdown: dict  # e.g., {"noise_levels": 4, "echo_configs": 12, "backends": 3, ...}
    estimated_duration_minutes: float | None = None


@router.post("/suites", response_model=TestSuiteResponse)
async def create_test_suite(
    config: SweepConfigRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a new test suite from sweep configuration.

    Expands the cartesian product of all parameter ranges into
    individual test cases with deterministic IDs.
    """
    # Query ready speech samples
    from backend.app.models.speech import CorpusEntry, Voice
    sample_stmt = select(SpeechSample).where(SpeechSample.status == "ready")
    if config.voice_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.voice_id.in_([uuid.UUID(v) for v in config.voice_ids])
        )
    # Build Voice join conditions
    voice_joined = False
    if config.voice_providers:
        sample_stmt = sample_stmt.join(Voice).where(
            Voice.provider.in_(config.voice_providers)
        )
        voice_joined = True
    if config.voice_languages:
        if not voice_joined:
            sample_stmt = sample_stmt.join(Voice)
            voice_joined = True
        sample_stmt = sample_stmt.where(Voice.language.in_(config.voice_languages))
    if config.voice_genders:
        if not voice_joined:
            sample_stmt = sample_stmt.join(Voice)
            voice_joined = True
        sample_stmt = sample_stmt.where(Voice.gender.in_(config.voice_genders))
    if config.corpus_entry_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.corpus_entry_id.in_([uuid.UUID(c) for c in config.corpus_entry_ids])
        )
    # Filter by corpus categories
    if config.corpus_categories:
        sample_stmt = sample_stmt.join(CorpusEntry).where(
            CorpusEntry.category.in_(config.corpus_categories)
        )

    sample_result = await session.execute(sample_stmt)
    samples = sample_result.scalars().all()

    if not samples:
        raise HTTPException(400, "No ready speech samples match the filters")

    if config.max_samples and len(samples) > config.max_samples:
        import random
        samples = random.sample(samples, config.max_samples)

    # Create test suite
    suite = TestSuite(
        name=config.name,
        description=config.description or "",
        status="draft",
    )
    session.add(suite)
    await session.flush()  # get suite.id

    # Create sweep config
    backends = config.llm_backends if config.llm_backends else ["default"]
    eq_configs_data = [
        [f.model_dump() for f in chain] for chain in config.echo.eq_chains
    ] if config.echo.eq_chains else []

    telephony_enabled = "telephony" in config.pipelines
    tel = config.telephony

    far_end_cfg = tel.far_end if tel else None

    sweep = SweepConfig(
        test_suite_id=suite.id,
        noise_level_db_values=config.noise_level_db_values,
        speech_level_db_values=config.speech_level_db_values,
        delay_ms_values=config.echo.delay_ms_values,
        gain_db_values=config.echo.gain_db_values,
        noise_types=config.noise_types,
        interferer_level_db_values=config.interferer_level_db_values,
        pipelines=config.pipelines,
        llm_backends=backends,
        eq_configs=eq_configs_data,
        telephony_enabled=telephony_enabled,
        bt_codec_types=tel.bt_codec_types if tel else None,
        agc_configs=tel.agc_presets if tel else None,
        aec_residual_configs=[c.model_dump() for c in tel.aec_configs] if tel and tel.aec_configs else None,
        network_configs=[c.model_dump() for c in tel.network_configs] if tel and tel.network_configs else None,
        far_end_enabled=far_end_cfg.enabled if far_end_cfg else False,
        far_end_speech_level_db_values=far_end_cfg.speech_level_db_values if far_end_cfg and far_end_cfg.enabled else None,
        far_end_offset_ms_values=far_end_cfg.offset_ms_values if far_end_cfg and far_end_cfg.enabled else None,
    )
    session.add(sweep)

    # Determine which noise types need interferer level sweep
    interferer_noise_types = {"secondary_voice", "babble"}

    # Telephony dimension iterables
    tel_codecs = tel.bt_codec_types if tel else ["none"]
    tel_agc_presets = tel.agc_presets if tel else ["off"]
    tel_aec_configs = [c.model_dump() for c in tel.aec_configs] if tel and tel.aec_configs else [None]
    tel_network_configs = [c.model_dump() for c in tel.network_configs] if tel and tel.network_configs else [None]

    # Far-end dimensions (only when enabled)
    far_end_enabled = far_end_cfg.enabled if far_end_cfg else False
    far_end_level_values = far_end_cfg.speech_level_db_values if far_end_cfg and far_end_cfg.enabled else [0.0]
    far_end_offset_values = far_end_cfg.offset_ms_values if far_end_cfg and far_end_cfg.enabled else [0.0]

    # Build cartesian product and create test cases
    total_cases = 0
    for sample, noise_level, speech_level, noise, delay, gain, pipeline, backend in product(
        samples,
        config.noise_level_db_values,
        config.speech_level_db_values,
        config.noise_types,
        config.echo.delay_ms_values,
        config.echo.gain_db_values,
        config.pipelines,
        backends,
    ):
        # For interferer noise types, sweep over interferer_level_db_values
        # For other noise types, just use None (no interferer)
        if noise in interferer_noise_types:
            level_values = config.interferer_level_db_values
        else:
            level_values = [None]

        for interferer_level in level_values:
            # For telephony pipeline, add telephony dimensions to cartesian product
            if pipeline == "telephony":
                telephony_combos = [
                    (codec, agc, aec, net, fe_level, fe_offset)
                    for codec in tel_codecs
                    for agc in tel_agc_presets
                    for aec in tel_aec_configs
                    for net in tel_network_configs
                    for fe_level in far_end_level_values
                    for fe_offset in far_end_offset_values
                ]
            else:
                telephony_combos = [(None, None, None, None, 0.0, 0.0)]

            for bt_codec, agc_preset, aec_cfg, net_cfg, fe_level, fe_offset in telephony_combos:
                # Build agc_config_json from preset name
                agc_config_json = {"preset": agc_preset} if agc_preset else None

                # Deterministic hash (includes suite ID for cross-suite uniqueness)
                hash_input = json.dumps(
                    {
                        "test_suite_id": str(suite.id),
                        "speech_sample_id": str(sample.id),
                        "noise_level_db": noise_level,
                        "speech_level_db": speech_level,
                        "noise_type": noise,
                        "interferer_level_db": interferer_level,
                        "delay_ms": delay,
                        "gain_db": gain,
                        "pipeline": pipeline,
                        "llm_backend": backend,
                        "bt_codec": bt_codec,
                        "agc_preset": agc_preset,
                        "aec_config": aec_cfg,
                        "network_config": net_cfg,
                        "far_end_enabled": far_end_enabled if pipeline == "telephony" else False,
                        "far_end_speech_level_db": fe_level,
                        "far_end_offset_ms": fe_offset,
                    },
                    sort_keys=True,
                )
                deterministic_hash = hashlib.sha256(hash_input.encode()).hexdigest()

                test_case = TestCase(
                    test_suite_id=suite.id,
                    speech_sample_id=sample.id,
                    noise_level_db=noise_level,
                    speech_level_db=speech_level,
                    delay_ms=delay,
                    gain_db=gain,
                    noise_type=noise,
                    interferer_level_db=interferer_level,
                    eq_config_json=None,
                    pipeline=pipeline,
                    llm_backend=backend,
                    status="pending",
                    deterministic_hash=deterministic_hash,
                    bt_codec=bt_codec,
                    agc_config_json=agc_config_json,
                    aec_residual_config_json=aec_cfg,
                    network_config_json=net_cfg,
                    far_end_enabled=far_end_enabled if pipeline == "telephony" else False,
                    far_end_speech_level_db=fe_level if pipeline == "telephony" else None,
                    far_end_offset_ms=fe_offset if pipeline == "telephony" else None,
                )
                session.add(test_case)
                total_cases += 1

    # Update suite status
    suite.status = "ready"
    await session.commit()

    return TestSuiteResponse(
        id=str(suite.id),
        name=suite.name,
        description=suite.description or "",
        status=suite.status,
        total_cases=total_cases,
        created_at=suite.created_at.isoformat(),
        telephony_enabled=telephony_enabled,
    )


def _suite_telephony_enabled(suite: TestSuite) -> bool:
    """Check if any sweep config on this suite has telephony_enabled=True."""
    for sc in suite.sweep_configs:
        if getattr(sc, "telephony_enabled", False):
            return True
    return False


@router.get("/suites", response_model=list[TestSuiteResponse])
async def list_test_suites(session: AsyncSession = Depends(get_session)):
    """List all test suites."""
    stmt = select(TestSuite)
    result = await session.execute(stmt)
    suites = result.scalars().all()

    responses = []
    for suite in suites:
        # Count test cases
        count_stmt = select(func.count()).select_from(TestCase).where(
            TestCase.test_suite_id == suite.id
        )
        count_result = await session.execute(count_stmt)
        case_count = count_result.scalar() or 0

        responses.append(
            TestSuiteResponse(
                id=str(suite.id),
                name=suite.name,
                description=suite.description or "",
                status=suite.status,
                total_cases=case_count,
                created_at=suite.created_at.isoformat(),
                telephony_enabled=_suite_telephony_enabled(suite),
            )
        )

    return responses


class AudioSourcesResponse(BaseModel):
    providers: dict[str, int]
    categories: dict[str, int]
    languages: dict[str, int]
    genders: dict[str, int]
    total_samples: int


@router.get("/suites/audio-sources", response_model=AudioSourcesResponse)
async def get_audio_sources(session: AsyncSession = Depends(get_session)):
    """Get available audio sources with sample counts by provider, category, language, gender."""
    from backend.app.models.speech import CorpusEntry, Voice

    provider_stmt = (
        select(Voice.provider, func.count(SpeechSample.id))
        .join(Voice, SpeechSample.voice_id == Voice.id)
        .where(SpeechSample.status == "ready")
        .group_by(Voice.provider)
    )
    provider_result = await session.execute(provider_stmt)
    providers = {row[0]: row[1] for row in provider_result.all()}

    category_stmt = (
        select(CorpusEntry.category, func.count(SpeechSample.id))
        .join(CorpusEntry, SpeechSample.corpus_entry_id == CorpusEntry.id)
        .where(SpeechSample.status == "ready")
        .group_by(CorpusEntry.category)
    )
    category_result = await session.execute(category_stmt)
    categories = {row[0]: row[1] for row in category_result.all()}

    language_stmt = (
        select(Voice.language, func.count(SpeechSample.id))
        .join(Voice, SpeechSample.voice_id == Voice.id)
        .where(SpeechSample.status == "ready")
        .group_by(Voice.language)
    )
    language_result = await session.execute(language_stmt)
    languages = {row[0]: row[1] for row in language_result.all() if row[0]}

    gender_stmt = (
        select(Voice.gender, func.count(SpeechSample.id))
        .join(Voice, SpeechSample.voice_id == Voice.id)
        .where(SpeechSample.status == "ready")
        .group_by(Voice.gender)
    )
    gender_result = await session.execute(gender_stmt)
    genders = {row[0]: row[1] for row in gender_result.all() if row[0]}

    total_stmt = select(func.count()).select_from(SpeechSample).where(SpeechSample.status == "ready")
    total_result = await session.execute(total_stmt)
    total = total_result.scalar() or 0

    return AudioSourcesResponse(
        providers=providers, categories=categories,
        languages=languages, genders=genders,
        total_samples=total,
    )


@router.get("/suites/{suite_id}", response_model=TestSuiteResponse)
async def get_test_suite(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get test suite details."""
    stmt = select(TestSuite).where(TestSuite.id == uuid.UUID(suite_id))
    result = await session.execute(stmt)
    suite = result.scalar_one_or_none()

    if suite is None:
        raise HTTPException(404, "Suite not found")

    count_stmt = select(func.count()).select_from(TestCase).where(
        TestCase.test_suite_id == suite.id
    )
    count_result = await session.execute(count_stmt)
    case_count = count_result.scalar() or 0

    return TestSuiteResponse(
        id=str(suite.id),
        name=suite.name,
        description=suite.description or "",
        status=suite.status,
        total_cases=case_count,
        created_at=suite.created_at.isoformat(),
        telephony_enabled=_suite_telephony_enabled(suite),
    )


@router.post("/suites/preview", response_model=SweepPreview)
async def preview_sweep(
    config: SweepConfigRequest,
    session: AsyncSession = Depends(get_session),
):
    """Preview the number of test cases a sweep configuration would generate.

    Does not create anything -- just returns the count and breakdown.
    """
    n_noise_levels = len(config.noise_level_db_values)
    n_speech_level = len(config.speech_level_db_values)
    n_delay = len(config.echo.delay_ms_values)
    n_gain = len(config.echo.gain_db_values)
    n_backends = len(config.llm_backends) or 1
    n_interferer_levels = len(config.interferer_level_db_values)

    # Noise types that use interferer level sweep vs those that don't
    interferer_noise_types = {"secondary_voice", "babble"}
    n_interferer_noises = sum(1 for n in config.noise_types if n in interferer_noise_types)
    n_regular_noises = len(config.noise_types) - n_interferer_noises

    # Telephony dimensions (only for telephony pipeline cases)
    tel = config.telephony
    n_tel_codecs = len(tel.bt_codec_types) if tel else 1
    n_tel_agc = len(tel.agc_presets) if tel else 1
    n_tel_aec = max(len(tel.aec_configs), 1) if tel else 1
    n_tel_net = max(len(tel.network_configs), 1) if tel else 1
    # Far-end dimensions
    fe_cfg = tel.far_end if tel else None
    n_fe_levels = len(fe_cfg.speech_level_db_values) if fe_cfg and fe_cfg.enabled else 1
    n_fe_offsets = len(fe_cfg.offset_ms_values) if fe_cfg and fe_cfg.enabled else 1
    n_tel_combos = n_tel_codecs * n_tel_agc * n_tel_aec * n_tel_net * n_fe_levels * n_fe_offsets

    n_telephony_pipelines = sum(1 for p in config.pipelines if p == "telephony")
    n_other_pipelines = len(config.pipelines) - n_telephony_pipelines

    # Count ready speech samples matching filters
    from backend.app.models.speech import CorpusEntry, Voice
    sample_stmt = select(func.count()).select_from(SpeechSample).where(
        SpeechSample.status == "ready"
    )
    if config.voice_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.voice_id.in_([uuid.UUID(v) for v in config.voice_ids])
        )
    voice_joined = False
    if config.voice_providers:
        sample_stmt = sample_stmt.join(Voice).where(
            Voice.provider.in_(config.voice_providers)
        )
        voice_joined = True
    if config.voice_languages:
        if not voice_joined:
            sample_stmt = sample_stmt.join(Voice)
            voice_joined = True
        sample_stmt = sample_stmt.where(Voice.language.in_(config.voice_languages))
    if config.voice_genders:
        if not voice_joined:
            sample_stmt = sample_stmt.join(Voice)
            voice_joined = True
        sample_stmt = sample_stmt.where(Voice.gender.in_(config.voice_genders))
    if config.corpus_entry_ids:
        sample_stmt = sample_stmt.where(
            SpeechSample.corpus_entry_id.in_([uuid.UUID(c) for c in config.corpus_entry_ids])
        )
    if config.corpus_categories:
        sample_stmt = sample_stmt.join(CorpusEntry).where(
            CorpusEntry.category.in_(config.corpus_categories)
        )

    count_result = await session.execute(sample_stmt)
    n_speech = count_result.scalar() or 0

    if config.max_samples and n_speech > config.max_samples:
        n_speech = config.max_samples

    # Cases per noise combo (non-telephony pipelines)
    base_per_noise = n_speech * n_noise_levels * n_speech_level * n_delay * n_gain * n_backends
    other_cases = base_per_noise * n_other_pipelines * (
        n_regular_noises + n_interferer_noises * n_interferer_levels
    )
    # Cases per noise combo (telephony pipeline — adds telephony dimensions)
    telephony_cases = base_per_noise * n_telephony_pipelines * (
        n_regular_noises + n_interferer_noises * n_interferer_levels
    ) * n_tel_combos

    total = other_cases + telephony_cases

    return SweepPreview(
        total_cases=total,
        breakdown={
            "noise_levels": n_noise_levels,
            "speech_levels": n_speech_level,
            "noise_types": len(config.noise_types),
            "interferer_levels": n_interferer_levels,
            "echo_delays": n_delay,
            "echo_gains": n_gain,
            "pipelines": len(config.pipelines),
            "backends": n_backends,
            "speech_samples": n_speech,
            "telephony_combos": n_tel_combos if n_telephony_pipelines > 0 else 0,
            "far_end_enabled": bool(fe_cfg and fe_cfg.enabled),
            "far_end_levels": n_fe_levels if n_telephony_pipelines > 0 else 0,
            "far_end_offsets": n_fe_offsets if n_telephony_pipelines > 0 else 0,
        },
    )


@router.delete("/suites/{suite_id}")
async def delete_test_suite(
    suite_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a test suite and all its test cases."""
    suite_uuid = uuid.UUID(suite_id)

    stmt = select(TestSuite).where(TestSuite.id == suite_uuid)
    result = await session.execute(stmt)
    suite = result.scalar_one_or_none()

    if suite is None:
        raise HTTPException(404, "Suite not found")

    # Delete test cases first (cascade)
    await session.execute(
        delete(TestCase).where(TestCase.test_suite_id == suite_uuid)
    )
    # Delete sweep configs
    await session.execute(
        delete(SweepConfig).where(SweepConfig.test_suite_id == suite_uuid)
    )
    # Delete the suite itself
    await session.delete(suite)
    await session.commit()

    return {"status": "deleted", "id": suite_id}
