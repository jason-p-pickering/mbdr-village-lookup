from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    DHIS2_BASE_URL: str = ""
    DHIS2_USERNAME: str = ""
    DHIS2_PASSWORD: str = ""
    TOWNSHIP_OPTIONSET_UID: str = ""
    WARD_OPTIONSET_UID: str = ""
    VILLAGE_OPTIONSET_UID: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
