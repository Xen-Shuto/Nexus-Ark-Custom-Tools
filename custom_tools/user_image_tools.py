# custom_tools/user_image_tools.py
# AIペルソナがユーザーの要望や会話の文脈に応じて、情景、キャラクター、アイテムなどのイラストを生成するツール
# ※事前にAUTOMATIC1111をAPIモードで（--apiの引数を追加して）起動しておく必要があります。

import requests
import base64
import os
import uuid
import time  # タイムスタンプ用
import urllib.parse  # urlエンコード用
from datetime import datetime
from langchain_core.tools import tool

# --- クオリティ向上のための固定品質向上系プロンプト ---
# ご利用のモデルに合わせて調整してください
# ↓はIllustrious系を意識した品質向上系プロンプト(先頭に挿入)
PREPEND_POSITIVE_PROMPT = (
    "masterpiece, extremely aesthetic, newest, very vibrant colors"
)
# ↓はIllustrious系を意識した品質向上系プロンプト(末尾に追加)
APPEND_POSITIVE_PROMPT = (
    ""
)

# --- クオリティ向上のための固定ネガティブプロンプト ---
# ご利用のモデルに合わせて調整してください
# コメントアウトしてるのはGeminiがSD1.5系を意識して出してきたもの
#DEFAULT_NEGATIVE_PROMPT = (
#    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
#    "fewer digits, cropped, worst quality, low quality, normal quality, "
#    "jpeg artifacts, signature, watermark, username, blurry, missing arms, "
#    "long neck, humpbacked, broken hand, twisted fingers, deformed hands, "
#    "extra limbs, fused fingers, too many fingers, deformed, liquid hands"
#)
# ↓はIllustrious系を意識したネガティブプロンプト
DEFAULT_NEGATIVE_PROMPT = (
    "nsfw, 3d, modern, recent, old, oldest, cartoon, graphic, text, painting, "
    "crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, "
    "long body, lowres, bad anatomy, bad hands, missing fingers, extra digits, "
    "fewer digits, cropped, very displeasing, (worst quality, bad quality:1.2), "
    "bad anatomy, sketch, jpeg artifacts, signature, watermark, username, "
    "signature, conjoined, bad ai-generated"
)

@tool
def generate_image_local(room_name: str, prompt: str, aspect_ratio: str = "square"):
    """
    ローカルのAUTOMATIC1111で画像生成します。
    
    引数:
    - room_name (str): 保存先となるシステム上のルーム名。
      必ず、ルーム選択のドロップダウンリストで選ばれているルームのフォルダ名を正確に指定してください。
    - prompt (str): 生成したい画像の詳細な英語プロンプト。
      ユーザーの指示が曖昧な場合は、
      現在の情景や世界観に基づいた高品質な英語プロンプトをAIが自律的に生成して指定すること。
    - aspect_ratio (str): 画像の形状。"square" (1:1), "portrait" (縦長 2:3), "landscape" (横長 3:2) から選択。
    
    ## 動作ルール（AIは必ず遵守すること）:
    1. **解像度の使い分け**: 
       - キャラクターの立ち絵や全身像なら "portrait"
       - 背景や景色なら "landscape"
       - アイコンや簡易的な図示なら "square"
       を指定してください。
    2. **出力義務**: 実行後、返された「チャットUI表示用Markdown( ![説明](URL) )」を、必ずそのまま最終回答に含めてください。
    3. **通知の判断**: あなたが自律行動中であったり、ユーザーに即時通知すべき内容だと判断した場合は、
       続けて `send_message_with_image` ツールを呼び出してください。
       その際、このツールが返した「通知ツール用ファイルパス」をそのまま引数に渡してください。
    4. **加工禁止**: Markdown内の( )内のURL、および通知用パスは1文字も変更してはいけません。
    5. **描写の追加**: 画像を表示する際、その内容についてあなたのキャラクターらしい解説を添えてください。
    """

    print("\n" + "="*50)
    print(f"[USER_IMAGE_TOOL_PLUGIN] 生成リクエスト開始")
    print(f"  - ルーム名: {room_name}")
    print(f"  - プロンプト: {prompt}")
    print(f"  - アスペクト比: {aspect_ratio}")
    print("="*50)

    # AIが「表示名」を渡してしまった場合に備え、正解の「内部ID」へ変換します。
    # マップに存在すれば変換後のIDを、なければそのままの値を採用します。
    # これにより、「オリヴェ」と送っても「Olivie」として処理されます。
    room_mapping = {
        "オリヴェ": "Olivie",
        "Olivie": "Olivie",
        # 必要に応じて、他のキャラクターもここに追加してください。
    }
    actual_id = room_mapping.get(room_name, room_name)

    # --- AUTOMATIC1111のAPI設定（自身の環境に合わせて修正してください。） ---
    url = "http://127.0.0.1:7861/sdapi/v1/txt2img"

    # --- 解像度の設定 ---
    # SDXL系を想定して1024ベースで設定
    # モデルに合わせて調整してください
    res_map = {
        "square": (1024, 1024),
        "portrait": (848, 1280),
        "landscape": (1280, 848)
    }
    width, height = res_map.get(aspect_ratio, (1024, 1024))

    # --- プロンプトの編集 ---
    if PREPEND_POSITIVE_PROMPT and isinstance(PREPEND_POSITIVE_PROMPT, str):
        prompt = f"{PREPEND_POSITIVE_PROMPT.strip()}, {prompt.strip()}"

    if APPEND_POSITIVE_PROMPT and isinstance(APPEND_POSITIVE_PROMPT, str):
        prompt = f"{prompt.strip()}, {APPEND_POSITIVE_PROMPT.strip()}"

    # APIへ送るデータ
    payload = {
        "prompt": prompt,
        "negative_prompt": DEFAULT_NEGATIVE_PROMPT,
        "steps": 35,
        "cfg_scale": 7,
        "width": width,
        "height": height,
        "sampler_name": "Euler a" # お好みのサンプラーがあれば変更してください
    }

    try:
        # API呼び出し
        print("[USER_IMAGE_TOOL_PLUGIN] Stable Diffusion APIにリクエスト送信中...")

        res = requests.post(url, json=payload)
        data = res.json()

        # --- 画像保存 ---
        img_base64 = data["images"][0]
        img_bytes = base64.b64decode(img_base64)

        # 日付フォルダを作成
        today_str = datetime.now().strftime('%Y-%m-%d')

        # --- 画像の保存ファイル名 ---
        # uuid4の最初の8文字だけ使うなど、短くしてもユニーク性は保てます
        unique_id = uuid.uuid4().hex[:8] 

        # 保存用ファイル名をUNIXタイムスタンプにする
        # これにより「時系列順」に並び、かつAIが「時刻」として認識しにくくなります。
        # 例: 1729999999.png (2024-10-27 15:00:00相当)
        timestamp_id = int(time.time())

        # --- 保存先の存在確認（相対パス：なければ作る） ---
        save_dir = f"characters/{actual_id}/generated_images/{today_str}"
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
            print(f"[USER_IMAGE_TOOL_PLUGIN] 保存フォルダを作成しました: {save_dir}")

        # --- 画像の保存ファイル名 ---
        filename = f"{save_dir}/img_{timestamp_id}_{unique_id}.png"

        with open(filename, "wb") as f:
            f.write(img_bytes)

        # --- 相対パスを絶対パスに変換 ---
        fullpath = os.path.abspath(filename)
        print(f"[USER_IMAGE_TOOL_PLUGIN] 相対パスを絶対パスに変換完了")

        # 【重要】バックスラッシュをスラッシュに置換
        # これにより AI が \ をエスケープしようとする挙動を物理的に防ぎます
        fullpath_fixed = fullpath.replace("\\", "/")
        print(f"[USER_IMAGE_TOOL_PLUGIN] バックスラッシュをスラッシュに置換完了")

        # 【重要】パスをURLエンコードする
        # これにより、C:/Users/... が C%3A/Users/... のようになり、AIが「日付」や「パス」だと認識しにくくなります
        encoded_path = urllib.parse.quote(fullpath_fixed)
        print(f"[USER_IMAGE_TOOL_PLUGIN] パスをURLエンコード完了")

        # --- 絶対パスをイメージURLに変換 ---
        image_url = f"http://127.0.0.1:7860/gradio_api/file={encoded_path}"
        print(f"[USER_IMAGE_TOOL_PLUGIN] 絶対パスをイメージURLに変換完了")

        # --- イメージURLをMarkdown形式に変換 ---
        markdown = f"![生成画像]({image_url})" 


        print(f"[USER_IMAGE_TOOL_PLUGIN] 画像保存成功: {fullpath}")
        print(f"  - イメージURL : {image_url}")
        print(f"  - Markdown形式: {markdown}")
        print("="*50 + "\n")

        # AIが受け取る文字列で指示を行う。
        result_for_ai = (
            f"【画像生成完了】以下の内容をあなたの言葉と共にユーザーへ伝えてください。\n"
            f"1. チャットUI表示用Markdown（あなたの回答に必ず含めてください）:\n"
            f"{markdown}\n\n"
            f"2. 通知ツール用ファイルパス（send_message_with_image を使う際に使用してください）:\n"
            f"{fullpath_fixed}"
        )

        # --- 結果を返す ---
        #return image_url
        return result_for_ai

    except Exception as e:
        error_msg = f"エラーが発生しました: {str(e)}"
        print(f"[USER_IMAGE_TOOL_PLUGIN] {error_msg}")
        print("="*50 + "\n")

        # AIが受け取る文字列で指示を行う。
        result_for_ai = f"【画像生成失敗】以下のメッセージをあなたの言葉と共にユーザーへ伝えてください：\n{error_msg}"

        return result_for_ai