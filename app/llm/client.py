"""LLM 客户端：OpenAI 兼容协议，用 httpx 直连

原则：LLM 只负责「理解」和「说话」，绝不直接操作数据库。
所有写库动作（扣款、下单）都由 services 层在事务里完成。

采用 httpx 直连而非 openai SDK，避免 SDK 与 httpx 版本冲突。
"""
from __future__ import annotations

import json
import queue
import threading
import time

import httpx

from app.config import settings

_client: httpx.Client | None = None


def _timeout(read_timeout_seconds: float) -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.llm_connect_timeout_seconds,
        read=read_timeout_seconds,
        write=read_timeout_seconds,
        pool=read_timeout_seconds,
    )


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        # 超时从 config(配置) 读取：默认 15s，避免单次 LLM 调用卡死整个请求
        _client = httpx.Client(timeout=_timeout(settings.llm_timeout_seconds))
    return _client


def reset_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def has_real_key() -> bool:
    """是否配置了真实 LLM key（非占位符）"""
    return bool(settings.effective_llm_api_key)


def _chat_completions_url() -> str:
    base_url = settings.llm_base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return base_url + "/chat/completions"


def _post_chat_completion(messages, temperature=0.7, timeout_seconds: float | None = None) -> str:
    """统一调用入口：POST {base_url}/chat/completions

    temperature 默认 0.7（推荐/聊天）；意图分类/JSON 输出传 0.0 更稳定。
    遇到 429 限流时自动重试 1 次（等 1.5 秒）。
    """
    url = _chat_completions_url()
    headers = {
        "Authorization": f"Bearer {settings.effective_llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.llm_model, "messages": messages, "temperature": temperature}
    read_timeout = settings.llm_generation_timeout_seconds if timeout_seconds is None else timeout_seconds

    last_response: httpx.Response | None = None
    for attempt in range(2):  # 最多 2 次（首次 + 1 次重试）
        try:
            resp = get_client().post(
                url,
                headers=headers,
                json=payload,
                timeout=_timeout(read_timeout),
            )
        except httpx.HTTPError:
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise
        last_response = resp
        # 429 限流：等一下重试一次
        if resp.status_code == 429 and attempt == 0:
            time.sleep(1.5)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    # 两次都 429
    if last_response is not None:
        raise httpx.HTTPStatusError(
            "rate limited (429)",
            request=last_response.request,
            response=last_response,
        )
    raise TimeoutError("LLM request did not complete")


def _run_with_wall_clock_timeout(func, timeout_seconds: float):
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put(("ok", func()))
        except BaseException as exc:  # propagate the provider/client exception
            result_queue.put(("err", exc))

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise TimeoutError(f"LLM call exceeded {timeout_seconds} seconds")
    status, payload = result_queue.get_nowait()
    if status == "err":
        raise payload
    return payload


def _call_llm(messages, temperature=0.7, timeout_seconds: float | None = None):
    budget = settings.llm_generation_timeout_seconds if timeout_seconds is None else timeout_seconds
    return _run_with_wall_clock_timeout(
        lambda: _post_chat_completion(messages, temperature=temperature, timeout_seconds=budget),
        budget,
    )


# ============================================================
# 【面试题·四个基础组件之一：LLM 大语言模型】
#
# LLM 的两个核心职责：
#   1. 理解用户意图（parse_intent）：是下单？是求推荐？还是闲聊？
#   2. 生成对话回复（chat）：基于 RAG 检索到的资料，生成自然语言推荐
#
# 安全原则：LLM 只负责"理解"和"说话"，绝不直接操作数据库。
#           所有写库动作（扣款、下单）都由 order_service 在事务里完成。
# ============================================================

# 【任务二·LLM】系统提示词：定义 AI 店长的人设和行为规则
# 包含禁编造规则，防止 LLM 凭空创造不存在的咖啡/套餐/价格
SYSTEM_PROMPT = (
    "你是「EvoMap 进化咖啡馆 AI 店长」，性格热情、幽默、健谈，像真实咖啡馆里那个总能记住熟客口味的店长。"
    "你会收到用户的最新消息、最近几轮对话上下文，以及从《咖啡风味手册》检索到的咖啡知识段落。"
    "\n\n【可以做的事】"
    "1. 自由地和顾客闲聊、开玩笑、聊天气/心情/咖啡冷知识，让对话温暖自然，不必每句话都推销咖啡。"
    "2. 基于检索到的资料推荐咖啡，给出名称、价格、风味说明、以及为什么适合 ta。"
    "3. 顾客问的饮品/套餐/服务我们没有时，先大方承认「我们这没有 XXX」，然后主动推荐 1-2 款风味最接近的菜单咖啡作为替代（例：「我们没有抹茶拿铁，但有奶香顺滑的【生椰拿铁】，你可以试试」）。"
    "4. 顾客描述模糊（如「想喝点暖的」「提神的」「不要太苦」）时，结合检索资料主动追问 1 个关键点或直接给 1-2 个最贴近的推荐。"
    "5. 顾客聊到和咖啡无关的话题时（天气/新闻/心情/工作等），先简短回应表示在听（最多1句），再用一句话自然地桥接回咖啡，不要生硬推销或每次都转——如果顾客只是随口一提，可以聊两句再回来。例：顾客说「今天好热」→「是啊这种天最适合来杯冰萃了，要试试我们的柑橘冷萃吗？」"
    "\n\n【绝不能做的事】"
    "1. 不得编造知识库里没有的咖啡名/价格/套餐/会员卡/外卖/赠品/轻食。如果不确定，宁可说「这个我们暂时没有」。"
    "2. 不得报错价格——价格必须与检索段落里写的一致，不要自己算优惠。"
    "3. 不要冷冰冰地只丢一句「没有」就结束——必须配套推荐替代品或追问需求。"
    "\n\n【风格】回复 150 字以内，自然口语，可以用 1-2 个表情，避免机械式列表（除非顾客明确要看菜单）。"
)


def chat(history, user_msg, context):
    """【任务二·LLM】基于 RAG 检索到的资料 + 对话历史，生成自然语言回复

    参数：
      history: Redis 读取的最近5轮对话（让 AI 有短期记忆）
      user_msg: 用户当前消息
      context: RAG 检索到的咖啡知识段落（来自 MySQL 的 CoffeeKB 表）

    流程：system提示 + RAG资料 + 对话历史 + 用户消息 → LLM 生成回复
    LLM 限流/失败时 → 优雅降级到 RAG 模板（用户无感）
    """
    if not has_real_key():
        return _mock_chat(context)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append(
            {"role": "system", "content": f"《咖啡风味手册》相关段落：\n{context}"}
        )
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    try:
        return _call_llm(messages, timeout_seconds=settings.llm_generation_timeout_seconds)
    except Exception:
        # LLM 限流/失败时，回退到用 RAG 检索结果直接回复（用户无感）
        return _mock_chat(context)


def _mock_chat(context: str) -> str:
    """无 LLM key 时的降级：给自然的店长回复，绝不 dump raw context"""
    return "您好~ 我是 EvoMap 进化咖啡馆 AI 店长☕ 今天想喝点什么口味的？可以告诉我喜欢的风味或者忌口，我来帮您挑一杯~"


# 【任务三·LLM】意图分类提示词（精简版：~150 字，省 ~170 tokens/次）
INTENT_PROMPT = """你是 EvoMap 进化咖啡馆意图分类器。结合对话历史，判断用户最新消息的意图，只输出JSON：
{"intent":"order|recommend|chat","reason":"简述","coffee_name":"咖啡名或空","quantity":1}

- order：明确要买/下单/确认（"来一杯""下单""就买它""好的""行"）+ 历史有推荐
- recommend：描述口味/求推荐/看菜单（"果味的""不要牛奶""有什么推荐"）
- chat：其他闲聊/询问（"几点关门""可以加冰吗"）"""

# LLM 不可用时的兜底词。覆盖最常见的中文下单表达，避免 LLM 不可用时
# 把"来一杯/要一杯/来个"这类明确的下单意图误判为闲聊。
# 注意：不包含"推荐/有什么/多少钱"等闲聊或求推荐词，这些仍应落入 chat/recommend。
_FALLBACK_ORDER_WORDS = (
    "买", "下单", "结账",
    "来一杯", "来个", "来两杯",
    "要一杯", "要个", "要两杯",
    "点一杯", "点个", "来份",
    "给我来", "整一杯", "整一个",
)


def parse_intent(history, user_msg):
    """【任务三·第2步】LLM 意图解析 —— 理解用户想干什么（不碰数据库）

    返回示例：
        {"intent":"order","coffee_name":"柑橘冷萃","quantity":1}   ← 用户想下单
        {"intent":"recommend"}                                      ← 用户想看推荐
        {"intent":"chat"}                                           ← 闲聊/询问

    这是纯 LLM 语义驱动（不再用硬编码触发词），能理解：
      "可以"（推荐后）→ order
      "可以加冰吗" → chat（有附加需求，不是纯确认）
      "这两杯了" → order
    """
    # LLM 可用：完全信任语义理解
    if has_real_key():
        messages = [{"role": "system", "content": INTENT_PROMPT}]
        # 意图分类只需最近 2 轮（4 条消息），省 ~300 tokens
        recent_history = history[-4:] if len(history) > 4 else history
        messages.extend(recent_history)
        messages.append({"role": "user", "content": user_msg})
        try:
            text = _call_llm(
                messages,
                temperature=0.0,
                timeout_seconds=settings.llm_intent_timeout_seconds,
            )
            text = _strip_code_fence(text)
            result = json.loads(text)
            # 规范化 intent 字段（兼容旧值 place_order）
            intent = result.get("intent", "")
            if intent in ("place_order", "order"):
                result["intent"] = "order"
            elif intent not in ("order", "recommend", "chat"):
                result["intent"] = "chat"
            return result
        except Exception:
            pass  # LLM 调用/解析失败，走兜底

    # 兜底：LLM 不可用时只用最硬的词判断
    # 明确排除求推荐/询价/闲聊词，避免"来推荐一下"被误判为下单
    _NON_ORDER_WORDS = ("推荐", "有什么", "多少钱", "介绍一下", "区别", "哪种")
    if any(w in user_msg for w in _NON_ORDER_WORDS):
        return {"intent": "chat"}
    if any(w in user_msg for w in _FALLBACK_ORDER_WORDS):
        return {"intent": "order"}
    return {"intent": "chat"}


def _strip_code_fence(text):
    """去掉 LLM 输出可能的 ```json 包裹"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


# ============================================================
# 多 Agent 协作提示词
# ============================================================

# 推荐 Agent(推荐): 基于 RAG 检索 + 历史经验，生成有理由的推荐
RECOMMENDER_PROMPT = (
    "你是EvoMap 进化咖啡馆的「推荐 Agent」，擅长把顾客的模糊口味需求精准匹配到具体咖啡。"
    "你会收到：用户最新消息、最近对话、从《咖啡风味手册》检索到的候选咖啡、以及「历史经验」段落。"
    "【重要规则】"
    "1. 只能推荐候选列表里出现的咖啡，不得编造知识库里没有的饮品。"
    "2. 价格必须与候选列表一致，不得自行拼凑优惠。"
    "3. 如果「历史经验」提示该用户曾对某类推荐不满，必须主动避开或调整，并在推荐理由中提及。"
    "4. 推荐时给出咖啡名称、价格、一句风味说明、一句为什么适合该用户。回复 120 字以内。"
)

# 复盘 Agent(事后复盘): 当用户表达「不是我要的 / 判断失误」时触发
# 分析 AI(人工智能) 推荐哪里出错，输出结构化教训
REVIEWER_PROMPT = """你是EvoMap 进化咖啡馆的「复盘 Agent」。当顾客对上一轮推荐表示不满或纠正时，你的任务是分析 AI(人工智能) 推荐哪里出了错，并把教训提炼成一条可复用的经验。

你会收到：上一轮推荐了什么、用户最新消息（表达不满或纠正）、最近对话。

请输出 JSON（只输出 JSON，不要其他文字）：
{
  "mistake_type": "失误类型，从以下选一个：wrong_flavor(口味误判) / missed_negation(漏听否定词) / wrong_category(选错品类) / wrong_price(价格误判) / other(其他)",
  "recommended_item": "上一轮推荐的咖啡名",
  "user_wanted": "根据用户纠正推断出他实际想要的口味或咖啡",
  "insight": "一条给下次推荐的行动建议，30 字以内，用大白话",
  "rating": 1到5的整数，1=完全误判，5=轻微偏差
}
"""

# 经验继承 Agent(经验积累): 把复盘教训格式化为推荐 Agent 可用的简短指引
EXPERIENCE_SYNTHESIS_PROMPT = (
    "你是EvoMap 进化咖啡馆的「经验继承 Agent」。你会收到一条复盘教训（失误类型+用户实际想要的+行动建议）。"
    "请把它压缩成 40 字以内的「推荐前必读」提示，让推荐 Agent(推荐) 下次面对同一用户时能直接避开这个坑。"
    "只输出提示文本，不要 JSON 或额外说明。"
)

# 用户画像 Agent(用户画像): 基于聊天+订单归纳口味偏好，供推荐 Agent 软引导
# 输入：新对话片段 + 最近订单 + 旧画像（累积式，演化不丢历史）
# 输出：JSON 结构化画像（summary/favorite_tags/avoid_tags/price_tier/persona）
USER_PROFILE_PROMPT = """你是EvoMap 进化咖啡馆的「用户画像 Agent」。你会收到：该用户最近的聊天对话、最近下单的咖啡、以及（若有）旧画像摘要。请归纳这位顾客的口味偏好画像。

【重要规则】
1. 只基于提供的数据归纳，数据不足的字段留空数组或"未知"，不得编造。
2. 与旧画像累积融合：保留旧画像里仍然成立的偏好，叠加本次新发现的偏好。
3. summary 是给推荐 Agent 看的自然语言摘要，120 字以内，用大白话描述"这位顾客喜欢/忌口什么、价格偏好、点单风格"。

请输出 JSON（只输出 JSON，不要其他文字）：
{
  "summary": "自然语言画像摘要，120 字以内",
  "favorite_tags": ["喜欢的口味/品类 tag，如 果香、热饮"],
  "avoid_tags": ["忌口的口味/品类 tag，如 甜、牛奶"],
  "price_tier": "价格偏好，从以下选一个：budget(偏实惠≤22) / mid(中档23-28) / premium(偏高端≥29) / unknown(数据不足)",
  "persona": "点单人设，20 字以内，如 纯粹苦味党 / 果香冷萃爱好者"
}
"""


def chat_with_role(system_prompt: str, context: str, history, user_msg: str, timeout_seconds: float | None = None) -> str:
    """通用多 Agent 调用入口：传入指定角色的 system prompt + 上下文 + 历史 + 用户消息。

    和 chat() 不同：chat() 固定使用 SYSTEM_PROMPT（店长人设），本函数允许传入任意角色提示词，
    供推荐 Agent / 复盘 Agent / 经验继承 Agent 复用同一套 _call_llm 基础设施。

    参数 timeout_seconds：可选的单次调用超时（复盘/经验压缩用较短超时），不传则用默认生成超时。
    """
    if not has_real_key():
        return ""
    messages = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({"role": "system", "content": context})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    try:
        actual_timeout = (
            timeout_seconds if timeout_seconds is not None else settings.llm_generation_timeout_seconds
        )
        return _call_llm(messages, timeout_seconds=actual_timeout)
    except Exception:
        return ""


def parse_json_response(text: str) -> dict | None:
    """把 LLM(大模型) 输出解析成 dict，去掉代码围栏后 JSON.loads；失败返回 None。"""
    if not text:
        return None
    try:
        return json.loads(_strip_code_fence(text))
    except (json.JSONDecodeError, TypeError):
        return None
