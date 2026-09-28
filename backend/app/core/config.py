from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/travel_planner?charset=utf8mb4"
    JWT_SECRET_KEY: str = "change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REDIS_URL: str = "redis://localhost:6379/0"
    CORS_ORIGINS: str = "http://localhost:5173"

    # 业务时区。库里统一存 UTC（MySQL 容器就是 UTC），只有「今天是几号」这类
    # 跟用户直觉有关的判断才需要换算到这个时区
    APP_TIMEZONE: str = "Asia/Shanghai"

    # DeepSeek 配置
    DEEPSEEK_API_KEY: str = ""
    # 默认模型：需要强制结构化输出的场景（行程生成、价格抽取）
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # 思考模型：多轮工具调用与自然语言对话（思考模式不支持强制 tool_choice）
    DEEPSEEK_MODEL_THINKING: str = "deepseek-flash"

    # Tavily 联网搜索
    TAVILY_API_KEY: str = ""

    # 和风天气（专属 API Host，形如 xxxx.re.qweatherapi.com）
    QWEATHER_API_HOST: str = ""
    QWEATHER_API_KEY: str = ""

    # 高德地图 Web 服务（REST）Key
    AMAP_API_KEY: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()