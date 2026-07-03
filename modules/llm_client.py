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

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

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


def ping(
    api_key: str,
    *,
    model: str,
    base_url: str,
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """轻量连通性测试：发一条最小请求，验证 Key/Base URL/模型三者是否可用。

    在分析阶段真正调用 LLM 之前，让用户能一键确认配置可用，避免到核实/校准
    环节才报「LLM 调用错误」。返回 ``(ok, message)``，message 已按错误类型
    归类为可读的中文提示。

    设计：
    - ``max_retries=0`` —— 测试要快速给出结果，不做退避重试。
    - 不计入 LLM 配额（不调用 ``record_llm_call``）：连通性测试属基础设施动作，
      不应消耗当日分析额度。
    - ``max_tokens=1`` —— 只要服务端正常返回结构即视为连通。
    """
    if not (api_key or "").strip():
        return False, "未配置 API Key，先在上方填入或设置环境变量。"
    if not (model or "").strip():
        return False, "未填写模型名。"
    if not (base_url or "").strip():
        return False, "未填写 Base URL。"

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except AuthenticationError:
        return False, "认证失败：API Key 无效或已过期。"
    except PermissionDeniedError:
        return False, "无权限：该 Key 无权访问此模型或接口。"
    except NotFoundError:
        return False, f"未找到：检查模型名「{model}」与 Base URL「{base_url}」是否匹配。"
    except RateLimitError:
        return False, "限流/欠费：触发 429，可能余额不足或调用过于频繁。"
    except APITimeoutError:
        return False, f"超时（>{timeout:.0f}s）：检查网络或 Base URL「{base_url}」。"
    except APIConnectionError as exc:
        return False, f"连接失败：无法连到「{base_url}」（{exc}）。"
    except Exception as exc:  # noqa: BLE001 —— 测试入口需把任意错误转成用户文案
        return False, f"调用失败：{type(exc).__name__}: {exc}"

    if getattr(response, "choices", None):
        return True, f"连接成功：模型「{model}」响应正常。"
    return True, f"已连通「{base_url}」，但返回结构异常，请抽查一次实际分析。"
