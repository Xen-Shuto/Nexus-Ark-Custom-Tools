# custom_tools/user_message_tools.py
# AIペルソナがユーザーに画像とメッセージを送るためのツール
# ※事前にDiscordまたはPushoverの設定を完了し、通知送信までできている必要があります。

import requests
import os
import json
from langchain_core.tools import tool
import config_manager
import utils
import room_manager

def _send_discord_message_local(webhook_url, message_text, room_name, image_path):
    """Discord Webhookに画像とテキストを送信する"""

    if not webhook_url:
        print("警告: Discord Webhook URL が空のため、Discord/Slack形式のWebhook通知を送信できませんでした。")
        return

    try:
        # どこから送信されたのか判別できるよう、メッセージにルーム名を追加
        send_text = f"{room_name}\n\n{message_text}\n"

        # 画像がある場合はマルチパート形式で送信
        # image_path が None や空文字でなく、かつファイルが存在する場合のみ画像送信
        if image_path and isinstance(image_path, str) and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                # ファイルとテキストを同時に送る
                payload = {'content': send_text}
                files = {'file': (os.path.basename(image_path), f, 'image/png')}
                # 注意: filesを使う場合、headersにContent-Type: application/jsonを指定してはいけません
                response = requests.post(webhook_url, data=payload, files=files, timeout=15)
        else:
            # 画像がない場合はテキストのみ送信
            headers = {'Content-Type': 'application/json'}
            payload = json.dumps({'content': send_text})
            response = requests.post(webhook_url, headers=headers, data=payload, timeout=10)

        response.raise_for_status()
        print(f"Discord/Slack形式のWebhook通知を送信しました。{' (画像あり)' if image_path else ''}")
    except Exception as e:
        print(f"Discord/Slack形式のWebhook通知送信エラー: {e}")

def _send_pushover_message_local(app_token, user_key, message_text, room_name, image_path):
    """Pushoverに画像とテキストを送信する"""

    if not app_token or not user_key:
        print("警告: app_token または user_key が空のため、Pushover通知を送信できませんでした。")
        return

    try:
        payload = {
            "token": app_token,
            "user": user_key,
            "title": f"{room_name}",
            "message": message_text
        }
 
        # Pushoverで画像を送る場合は attachment パラメータを使用
        # image_path が None や空文字でなく、かつファイルが存在する場合のみ画像送信
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                files = {"attachment": (os.path.basename(image_path), f, "image/png")}
                response = requests.post("https://api.pushover.net/1/messages.json", data=payload, files=files, timeout=15)
        else:
            response = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)

        response.raise_for_status()
        print(f"Pushover通知を送信しました。{' (画像あり)' if image_path else ''}")
    except Exception as e:
        print(f"Pushover通知送信エラー: {e}")

def _send_message_with_image(room_name: str, message_text: str, image_path: str) -> str:
    """設定に応じて、適切なサービスにメッセージ（＋画像）を送信する"""

    # その瞬間の config.json を読み込む
    latest_config = config_manager.load_config_file()

    # サービス設定を取得（デフォルトは discord）
    service = latest_config.get("notification_service", "discord").lower()

    if service == "pushover":
        print(f"--- 通知サービス: Pushover を選択 ---")

        _send_pushover_message_local(
            latest_config.get("pushover_app_token"),
            latest_config.get("pushover_user_key"),
            message_text,
            room_name,
            image_path
        )
    else: # デフォルトはDiscord
        print(f"--- 通知サービス: Discord を選択 ---")

        # Webhook URLもファイルから直接取得する
        webhook_url = latest_config.get("notification_webhook_url")

        _send_discord_message_local(
            webhook_url,
            message_text,
            room_name,
            image_path
        )

@tool
def send_message_local_with_image(message: str, room_name: str, image_path: str) -> str:
    """
    ユーザーにメッセージと一緒に画像をDiscord通知として送信します。
    
    自律行動中に生成した画像や、見せたい景色がある場合に使用してください。
    
    ※ 通知禁止時間帯（Quiet Hours）の場合は送信されません。
    
    引数:
    - message (str): ユーザーに送りたいメッセージ内容
    - room_name (str): システム上のルーム名。
    - image_path (str): 送信したい画像ファイルのローカル絶対パス
    """

    print("\n" + "="*50)
    print(f"[USER_MESSAGE_TOOL_PLUGIN] 画像付きメッセージ送信リクエスト開始")
    print(f"  - メッセージ: {message}")
    print(f"  - ルーム名: {room_name}")
    print(f"  - 画像の絶対パス: {image_path}")
    print("="*50)

    # 設定取得
    effective_settings = config_manager.get_effective_settings(room_name)
    auto_settings = effective_settings.get("autonomous_settings", {})
    quiet_start = auto_settings.get("quiet_hours_start", "00:00")
    quiet_end = auto_settings.get("quiet_hours_end", "07:00")

    # ログファイルパス
    log_f, _, _, _, _, _, _ = room_manager.get_room_files_paths(room_name)

    # 静かな時間帯チェック
    if utils.is_in_quiet_hours(quiet_start, quiet_end):
        if log_f:
            utils.save_message_to_log(log_f, "## SYSTEM:notification_blocked", f"📱 **画像通知（待機中）**\n\n{message}\n(Path: {image_path})")
        return f"現在は通知禁止時間帯（{quiet_start}〜{quiet_end}）のため、通知はスキップされました。"

    # 画像パスの正規化（AIが \ を混ぜてくる可能性への対策）
    clean_path = image_path.replace('"', '').replace("'", "").strip()

    # 送信実行
    _send_message_with_image(room_name, message, clean_path)

    # チャットログに記録
    if log_f:
        utils.save_message_to_log(log_f, "## SYSTEM:notification_sent", f"📱 **画像通知を送信しました**\n\n{message}\n(Path: {image_path})")

    print(f"[USER_MESSAGE_TOOL_PLUGIN] 画像付きメッセージ送信完了")
    print("="*50)

    return f"メッセージを送信しました: {message[:30]}..."

@tool
def send_message_local(message: str, room_name: str) -> str:
    """
    ユーザーにメッセージを送信します。
    
    自律行動中、ユーザーに伝えたいことがある場合に使用してください。
    
    ※ 通知禁止時間帯（Quiet Hours）の場合は送信されません。
    
    
    引数:
    - message (str): ユーザーに送りたいメッセージ内容
    - room_name (str): システム上のルーム名。
    """

    print("\n" + "="*50)
    print(f"[USER_MESSAGE_TOOL_PLUGIN] メッセージ送信リクエスト開始")
    print(f"  - メッセージ: {message}")
    print(f"  - ルーム名: {room_name}")
    print("="*50)

    # 設定取得
    effective_settings = config_manager.get_effective_settings(room_name)
    auto_settings = effective_settings.get("autonomous_settings", {})
    quiet_start = auto_settings.get("quiet_hours_start", "00:00")
    quiet_end = auto_settings.get("quiet_hours_end", "07:00")

    # ログファイルパス
    log_f, _, _, _, _, _, _ = room_manager.get_room_files_paths(room_name)

    # 静かな時間帯チェック
    if utils.is_in_quiet_hours(quiet_start, quiet_end):
        if log_f:
            utils.save_message_to_log(log_f, "## SYSTEM:notification_blocked", f"📱 **通知（待機中）**\n\n{message}")
        return f"現在は通知禁止時間帯（{quiet_start}〜{quiet_end}）のため、通知はスキップされました。"

    # 送信実行
    _send_message_with_image(room_name, message, None)

    # チャットログに記録
    if log_f:
        utils.save_message_to_log(log_f, "## SYSTEM:notification_sent", f"📱 **通知を送信しました**\n\n{message}")

    print(f"[USER_MESSAGE_TOOL_PLUGIN] メッセージ送信完了")
    print("="*50)

    return f"メッセージを送信しました: {message[:30]}..."