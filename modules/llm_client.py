"""共享 LLM 调用层：统一 chat.completions 的网络瞬时错误退避重试。

背景：rule_generator / audit_llm_analysis 此前各自复制了一份"对
APITimeoutError / APIConnectionError 指数退避重试"的循环。此处收敛为
单一实现，调用方只需在耗尽重试后把原始异常映射成各自的用户文案 / 降级逻辑。

边界说明：
- 本 helper 只对**网络类瞬时错误**退避重试，耗尽后重新抛出原始异常，
  由调用方决定映射成 TimeoutError / ConnectionError 等用户文案。
- 非网络异常**不在此处吞没**，直接上抛，让调用方做各自的降级
  （如 audit 的 response_format 移除重试）。
- llm_verifier 采用"对任意异常都重试"的不同语义，刻意不接入本 helper，
  以免改变其既有行为。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError

from modules.llm_quota import record_llm_call

logger = logging.getLogger(__name__)

# 网络类瞬时错误：退避重试的唯一触发条件
TRANSIENT_ERRORS = (APITimeoutError, APIConnectionError)


def chat_with_retry(
    client: Any,
    request_kwargs: dict[str, Any],
    *,
    operation: str,
    max_retries: int,
    backoff_base: float,
) -> Any:
    """围绕 client.chat.completions.create 的指数退避重试。

    每次尝试前调用 record_llm_call(operation)（与历史行为一致）。
    成功返回 create() 的原始 response 对象；网络瞬时错误耗尽重试后
    重新抛出最后一次原始异常。

    Args:
        client: OpenAI 兼容客户端。
        request_kwargs: 传给 chat.completions.create 的关键字参数。
        operation: 配额跟踪用的操作名（namespace）。
        max_retries: 最大重试次数（总尝试 = max_retries + 1）。
        backoff_base: 退避底数，第 n 次等待 backoff_base ** n 秒。
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        record_llm_call(operation)
        try:
            return client.chat.completions.create(**request_kwargs)
        except TRANSIENT_ERRORS as exc:
            last_exc = exc
            logger.warning(
                "LLM %s 网络瞬时错误（第 %d/%d 次）：%s",
                operation, attempt + 1, max_retries + 1, exc,
            )
            if attempt < max_retries:
                time.sleep(backoff_base ** attempt)
                continue
            raise
    # 循环要么 return 要么 raise，理论不可达
    raise last_exc  # type: ignore[misc]
