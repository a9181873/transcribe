from asr_catalog import (
    ASR_PROFILES,
    available_profile_keys,
    default_profile_key,
    detect_runtime_family,
)


def test_apple_silicon_defaults_to_memory_safe_turbo():
    runtime = detect_runtime_family(system="Darwin", machine="arm64")

    assert runtime == "apple_silicon"
    assert default_profile_key(runtime) == "mlx_whisper_turbo"
    assert available_profile_keys(runtime)[0] == "mlx_whisper_turbo"


def test_cpu_server_only_exposes_runnable_sensevoice():
    runtime = detect_runtime_family(system="Linux", machine="aarch64")

    assert runtime == "cpu_server"
    assert available_profile_keys(runtime) == ["sensevoice_cpu"]
    assert default_profile_key(runtime) == "sensevoice_cpu"


def test_all_profiles_have_scenario_and_memory_guidance():
    for profile in ASR_PROFILES.values():
        assert profile.scenario
        assert profile.hardware
        assert profile.memory
        assert profile.accuracy
