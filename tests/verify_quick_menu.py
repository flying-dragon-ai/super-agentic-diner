from __future__ import annotations

import _test_env
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def dump(labels):
    # Console on this host defaults to GBK; render emoji safely.
    return [label.encode("unicode_escape").decode("ascii") for label in labels]


def quick_labels(page):
    return page.eval_on_selector_all(
        "#quickMenu button",
        "els => els.map(e => e.textContent.trim())",
    )


def quick_prompts(page):
    return page.eval_on_selector_all(
        "#quickMenu button",
        "els => els.map(e => e.dataset.intent + ':' + e.title)",
    )


def run_case(page, name, setup, expected_any_of, avoid=()):
    setup(page)
    labels = quick_labels(page)
    print(f"[{name}] labels={dump(labels)}")
    assert labels, f"{name}: 菜单为空"
    matched = any(any(token in label for token in expected_any_of) for label in labels)
    assert matched, f"{name}: 未命中期望词 {expected_any_of}, 实际 {labels}"
    if avoid:
        leaked = [label for label in labels for token in avoid if token in label]
        assert not leaked, f"{name}: 不应出现 {avoid}, 但命中 {leaked}"


def main() -> None:
    config = _test_env.require_live_test_config()
    base_url = f"{config.base_url}/"
    parsed = urlsplit(config.base_url)
    live_origin = f"{parsed.scheme}://{parsed.netloc}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        chat_responses = {}

        def handle(route, request):
            payload = chat_responses.get(request.post_data)
            if payload is not None:
                route.fulfill(status=200, content_type="application/json", body=payload)
            else:
                route.continue_()

        page.route("**/chat", handle)
        page.route(
            "**/*",
            lambda route, request: (
                route.continue_()
                if live_origin not in request.url
                else route.fallback()
            ),
        )
        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_selector("#quickMenu button")

        welcome_labels = quick_labels(page)
        print("[initial] labels=", dump(welcome_labels))
        assert any("果香" in label or "菜单" in label for label in welcome_labels), welcome_labels

        # 输入"清甜水果味"后，菜单应切到 fruit 分支
        def type_fruit(page):
            page.fill("#msgInput", "店长，我想喝点清甜水果味的，但不要加牛奶。")
            page.wait_for_function("document.querySelectorAll('#quickMenu button').length")

        run_case(page, "fruit", type_fruit, ["无奶", "冷萃"], avoid=["椰香"])

        # 输入椰子味后，菜单切到 coconut 分支
        def type_coconut(page):
            page.fill("#msgInput", "有没有椰子味的？不要太苦。")
            page.wait_for_function("document.querySelectorAll('#quickMenu button').length")

        run_case(page, "coconut", type_coconut, ["椰香", "冰椰", "甜感"], avoid=["黑咖啡"])

        # 模拟店长给出推荐 + 用户发送下单 -> confirming 分支
        reco_reply = '{"reply":"推荐您试试「椰香冷萃」，¥28，清爽又不发苦。回复「确认」即可下单。","order_id":null}'
        chat_responses[None] = None

        def send_for_confirm(page):
            request_body = page.evaluate(
                "baseUrl => JSON.stringify({user_id: 1, message: '我想喝椰子味的，不要太苦。', consumer_url: baseUrl})",
                base_url,
            )
            chat_responses[request_body] = reco_reply
            page.fill("#msgInput", "我想喝椰子味的，不要太苦。")
            page.click("#sendBtn")
            page.wait_for_function("document.querySelectorAll('#quickMenu button').length")

        # confirming 分支特有按钮（半糖/换口味/先等等），且确认按钮会被上下文改写成“买<咖啡名>”
        run_case(page, "confirming", send_for_confirm, ["确认", "买", "半糖", "换口味", "先等等"])

        # 清空对话回到 welcome
        page.click("text=清空对话")
        page.wait_for_function("document.querySelectorAll('#quickMenu button').length")
        cleared = quick_labels(page)
        print("[cleared] labels=", dump(cleared))
        assert any("果香" in label or "菜单" in label for label in cleared), cleared

        # 模拟下单完成 -> paid 分支
        paid_reply = '{"reply":"好嘞！已为您下单「椰香冷萃」，扣款 ¥28。祝您品尝愉快~","order_id":42}'

        def send_paid(page):
            request_body = page.evaluate(
                "baseUrl => JSON.stringify({user_id: 1, message: '确认下单。', consumer_url: baseUrl})",
                base_url,
            )
            chat_responses[request_body] = paid_reply
            page.fill("#msgInput", "确认下单。")
            page.click("#sendBtn")
            page.wait_for_function("document.querySelectorAll('#quickMenu button').length")

        # paid 分支会先经过 sending/waiting，给点时间
        page.wait_for_timeout(400)
        run_case(page, "paid", send_paid, ["再来一杯", "查看订单", "评价", "搭配"])

        browser.close()
        print("OK: quick menu reacts to user intent and order lifecycle")


if __name__ == "__main__":
    main()
