from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    """所有请求 / 响应模型的基类：JSON 中使用 camelCase，Python 中使用 snake_case。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
