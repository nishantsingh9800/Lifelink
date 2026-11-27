from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LifeLink"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    dev_auth_mode: bool = True
    app_jwt_secret: str = "lifelink-local-dev-secret-change-before-production-use"
    dev_db_path: str = str(PROJECT_ROOT / "backend" / "lifelink_dev.db")
    upload_dir: str = str(PROJECT_ROOT / "backend" / "uploads" / "donor_documents")
    max_document_size_bytes: int = 5 * 1024 * 1024
    access_token_expire_minutes: int = 60 * 12

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_phone_otp_enabled: bool = False
    aadhaar_kyc_enabled: bool = False
    require_aadhaar_for_actions: bool = False
    aadhaar_kyc_api_url: str = ""
    aadhaar_kyc_api_key: str = ""

    geocoding_api_key: str = ""
    eraktkosh_api_url: str = ""
    eraktkosh_api_key: str = ""
    masked_calling_api_url: str = ""
    masked_calling_api_key: str = ""
    push_notification_api_url: str = ""
    push_notification_api_key: str = ""
    hospital_sso_metadata_url: str = ""

    google_drive_folder_url: str = ""
    google_drive_folder_id: str = ""
    google_drive_service_account_file: str = ""

    # Configurable coordination & safety review rules (not medical eligibility determinations)
    donor_review_interval_days: int = 90
    expiry_hours_emergency: int = 24
    expiry_hours_urgent: int = 48
    expiry_hours_normal: int = 72
    stage1_max_donors: int = 5
    stage2_max_donors: int = 12
    rate_limit_requests_per_minute: int = 60
    face_match_threshold: float = 0.80

    @property
    def is_supabase_configured(self) -> bool:
        return bool(
            self.supabase_url.strip()
            and self.supabase_anon_key.strip()
            and self.supabase_service_role_key.strip()
        )

    @property
    def storage_mode(self) -> str:
        return "supabase" if self.is_supabase_configured else "local_dev_sqlite"

    @property
    def auth_mode(self) -> str:
        return "supabase" if self.is_supabase_configured else "dev_only"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_google_drive_folder_id(self) -> str:
        if self.google_drive_folder_id.strip():
            return self.google_drive_folder_id.strip()
        url = self.google_drive_folder_url.strip().rstrip("\\/")
        if "/folders/" in url:
            return url.split("/folders/")[-1].split("?")[0].strip("\\/")
        return ""

    @property
    def is_google_drive_upload_enabled(self) -> bool:
        sa_path = self.google_drive_service_account_file.strip()
        return bool(
            sa_path
            and Path(sa_path).is_file()
            and self.resolved_google_drive_folder_id
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
