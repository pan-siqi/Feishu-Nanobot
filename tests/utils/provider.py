from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.providers.base import GenerationSettings
# API_KEY = 'ark-ac09661c-4790-4392-ac7d-5f8e4bda0552-c01dd'
# BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'
# MODEL = 'ep-20260423223104-568xj'
API_KEY = 'sk-agAQ8pJi0esBUbb71Q5Db3oHFghpAdLJJ4pejiZ3QG2qw1Fy'
BASE_URL = 'https://www.dmxapi.cn/v1'
MODEL = 'gpt-4o-mini'

def make_provider() -> OpenAICompatProvider:
    provider = OpenAICompatProvider(
        api_key=API_KEY,
        api_base=BASE_URL,
        default_model=MODEL,
        extra_headers=None,
        spec=None,
    )
    provider.generation= GenerationSettings(
        temperature=0.1,
        max_tokens=8192,
        reasoning_effort=None,
    )
    return provider