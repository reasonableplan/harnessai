"""Task B2: ha-review mobile 보안 룰 검증.

ha-review/run.py 의 _check_mobile_* 함수들을 직접 import해서 테스트.
mobile 룰은 mobile profile 이 활성일 때만 동작, backend 프로젝트엔 영향 없음.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    """ha-review/run.py 를 모듈로 로드."""
    loader = SourceFileLoader("ha_review_run_b2", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_run_b2", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_run_b2"] = mod
    loader.exec_module(mod)
    return mod


# ── B2-1: AsyncStorage.setItem token → BLOCK ──────────────────────────


def test_async_storage_token_block(ha_review: ModuleType) -> None:
    """AsyncStorage.setItem('auth_token', ...) → BLOCK finding 반환."""
    diff = (
        "+  await AsyncStorage.setItem('auth_token', token);\n"
        "+  await AsyncStorage.setItem('access_token', response.data.token);\n"
    )
    findings = ha_review._check_mobile_secret_storage(diff, "react-native-expo")
    assert len(findings) >= 1, f"expected BLOCK finding, got: {findings}"
    severities = {f["severity"] for f in findings}
    assert "BLOCK" in severities, f"expected BLOCK severity, got: {findings}"


# ── B2-2: 일반 AsyncStorage.setItem (non-token) → 통과 ────────────────


def test_async_storage_non_token_pass(ha_review: ModuleType) -> None:
    """AsyncStorage.setItem('locale', ...) → BLOCK finding 없음."""
    diff = "+  await AsyncStorage.setItem('locale', 'ko');\n"
    findings = ha_review._check_mobile_secret_storage(diff, "react-native-expo")
    block_findings = [f for f in findings if f["severity"] == "BLOCK"]
    assert len(block_findings) == 0, f"unexpected BLOCK for non-token key: {findings}"


# ── B2-3: requestPermissions 3개 이상 → WARN ──────────────────────────


def test_permission_burst_warn(ha_review: ModuleType) -> None:
    """requestPermissions([CAMERA, LOCATION, NOTIFICATION]) → WARN finding."""
    diff = (
        "+  const granted = await PermissionsAndroid.requestMultiple([\n"
        "+    PermissionsAndroid.PERMISSIONS.CAMERA,\n"
        "+    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,\n"
        "+    PermissionsAndroid.PERMISSIONS.READ_CONTACTS,\n"
        "+  ]);\n"
    )
    findings = ha_review._check_mobile_permission_burst(diff, "android-kotlin")
    assert len(findings) >= 1, f"expected WARN finding for permission burst, got: {findings}"
    severities = {f["severity"] for f in findings}
    assert "WARN" in severities, f"expected WARN severity, got: {findings}"


# ── B2-4: ios-swift profile + Podfile 신규 pod 추가 → WARN ────────────


def test_cocoapods_new_warn(ha_review: ModuleType) -> None:
    """ios-swift profile 에서 Podfile 에 새 pod 추가 → WARN."""
    diff = (
        "diff --git a/Podfile b/Podfile\n"
        "+++ b/Podfile\n"
        "+  pod 'Alamofire'\n"
    )
    findings = ha_review._check_cocoapods_new(diff, "ios-swift")
    assert len(findings) >= 1, f"expected WARN for new CocoaPod, got: {findings}"
    severities = {f["severity"] for f in findings}
    assert "WARN" in severities, f"expected WARN severity, got: {findings}"


# ── B2-5: react-native-expo + react-native run-android → WARN ─────────


def test_rn_cli_direct_warn(ha_review: ModuleType) -> None:
    """react-native-expo profile 에서 react-native run-android 사용 → WARN."""
    diff = "+  react-native run-android\n"
    findings = ha_review._check_rn_cli(diff, "react-native-expo")
    assert len(findings) >= 1, f"expected WARN for RN CLI direct use, got: {findings}"
    severities = {f["severity"] for f in findings}
    assert "WARN" in severities, f"expected WARN severity, got: {findings}"


# ── B2-6: backend 프로젝트 → mobile 룰 영향 없음 ──────────────────────


def test_backend_profile_no_mobile_findings(ha_review: ModuleType) -> None:
    """fastapi profile 에서 mobile 룰 전부 finding 0."""
    diff = (
        "+  await AsyncStorage.setItem('auth_token', token);\n"
        "+  pod 'Alamofire'\n"
        "+  react-native run-android\n"
    )
    # mobile 룰 함수들은 non-mobile profile_id 전달 시 빈 리스트 반환해야 함
    findings: list = []
    findings += ha_review._check_mobile_secret_storage(diff, "fastapi")
    findings += ha_review._check_mobile_permission_burst(diff, "fastapi")
    findings += ha_review._check_cocoapods_new(diff, "fastapi")
    findings += ha_review._check_rn_cli(diff, "fastapi")
    assert len(findings) == 0, (
        f"backend profile should not trigger mobile rules, got: {findings}"
    )
