"""
自動コンテンツ投稿サービス
- 月・水・金 09:00 → note記事を自動生成して投稿（末尾にGumroad CTA付き）
- 火・木    10:00 → 直近のnote記事をRedditに英語要約で投稿（末尾にGumroad CTA付き）
- 毎日      07:00 → X（Twitter）朝投稿: AI Tips + Gumroad商品リンク
- 毎日      19:00 → X（Twitter）夜投稿: note記事要約 + note リンク
- 毎月1日   09:00 → Gumroad商品紹介の無料note記事を投稿（最大集客）
- 毎月15日  10:00 → Gumroad新商品を自動生成・登録
"""
import asyncio
import random
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

NOTE_TOPICS = [
    "ai_productivity",
    "side_hustle",
    "marketing",
    "investing",
    "programming",
]

REDDIT_SUBREDDITS = [
    "juststart",        # 小規模・ブログ/コンテンツ系（karma制限ゆるい）
    "digitalnomad",     # 小〜中規模・外部リンク許容あり
    "sidehustle",       # 副業系・新規でも投稿しやすい
    "Entrepreneur",     # 大型だが一応残す
    "artificial",       # AI系
]

# 毎日（量産フェーズ: 20〜30本到達まで毎日投稿）
NOTE_DAYS = {0, 1, 2, 3, 4, 5, 6}
NOTE_HOUR = 9
# 火・木
REDDIT_DAYS = {1, 3}
REDDIT_HOUR = 10
# 月次プロモ
PROMO_DAY = 1
PROMO_HOUR = 9
# 月次新商品生成
NEW_PRODUCT_DAY = 15
NEW_PRODUCT_HOUR = 10
# X（Twitter）
X_MORNING_HOUR = 7
X_EVENING_HOUR = 19


class AutoPublisher:
    def __init__(self, org, task_results: dict, persist_fn, memory=None):
        self._org = org
        self._task_results = task_results
        self._persist = persist_fn
        self._mem = memory
        self._task: asyncio.Task | None = None
        self._running = False
        self._note_topic_idx = 0
        self._reddit_sub_idx = 0
        self._qiita_last_post_date: str = ""  # YYYY-Www 形式（週番号）
        self._log: list[dict] = []

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            print("[AutoPublisher] 起動 - note(月水金09:00) Reddit(火木10:00) X(毎日07:00/19:00) プロモ(毎月1日) 新商品(毎月15日)")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    def status(self) -> dict:
        return {
            "running": self._running,
            "note_topic_idx": self._note_topic_idx,
            "next_note_topic": NOTE_TOPICS[self._note_topic_idx % len(NOTE_TOPICS)],
            "next_reddit_sub": REDDIT_SUBREDDITS[self._reddit_sub_idx % len(REDDIT_SUBREDDITS)],
            "recent_log": self._log[-10:],
        }

    def _log_event(self, msg: str):
        entry = {"time": datetime.now().isoformat(), "msg": msg}
        self._log.append(entry)
        print(f"[AutoPublisher] {msg}")

    async def _loop(self):
        last_note_date = ""
        last_reddit_date = ""
        last_promo_month = ""
        last_product_month = ""
        last_x_morning_date = ""
        last_x_evening_date = ""
        while self._running:
            await asyncio.sleep(60)
            try:
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                month = now.strftime("%Y-%m")
                weekday = now.weekday()
                hour = now.hour
                minute = now.minute
                day = now.day

                # note投稿チェック（月・水・金 09:00）
                if weekday in NOTE_DAYS and hour == NOTE_HOUR and minute == 0 and last_note_date != today:
                    last_note_date = today
                    asyncio.create_task(self._run_note_post())

                # Reddit投稿チェック（火・木 10:00）
                if weekday in REDDIT_DAYS and hour == REDDIT_HOUR and minute == 0 and last_reddit_date != today:
                    last_reddit_date = today
                    asyncio.create_task(self._run_reddit_post())

                # X 朝投稿（毎日 07:00）
                if hour == X_MORNING_HOUR and minute == 0 and last_x_morning_date != today:
                    last_x_morning_date = today
                    asyncio.create_task(self._run_x_morning_post())

                # X 夜投稿（毎日 19:00）
                if hour == X_EVENING_HOUR and minute == 0 and last_x_evening_date != today:
                    last_x_evening_date = today
                    asyncio.create_task(self._run_x_evening_post())

                # 月次プロモ記事（毎月1日 09:00）
                if day == PROMO_DAY and hour == PROMO_HOUR and minute == 0 and last_promo_month != month:
                    last_promo_month = month
                    asyncio.create_task(self._run_promo_note_post())

                # 月次新商品生成（毎月15日 10:00）
                if day == NEW_PRODUCT_DAY and hour == NEW_PRODUCT_HOUR and minute == 0 and last_product_month != month:
                    last_product_month = month
                    asyncio.create_task(self._run_new_product())

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log_event(f"ループエラー: {e}")

    async def _run_note_post(self):
        topic = NOTE_TOPICS[self._note_topic_idx % len(NOTE_TOPICS)]
        self._note_topic_idx += 1
        self._log_event(f"note記事生成開始: {topic}")

        import uuid
        from datetime import datetime as dt
        task_id = uuid.uuid4().hex[:8]
        from services.note_poster import NotePoster
        from core.llm import call_llm

        NOTE_LABEL = {
            "ai_productivity": "AI・ChatGPT活用術",
            "side_hustle": "副業・フリーランス収入",
            "marketing": "SNS集客・マーケティング",
            "investing": "資産運用・投資入門",
            "programming": "プログラミング・IT副業",
        }
        from api.app import NOTE_TEMPLATES
        from agents.research_agent import get_trending_context
        t = NOTE_TEMPLATES[topic]
        theme = t["theme"]
        trend_context = get_trending_context(topic)
        if trend_context:
            self._log_event(f"[Research] トレンド取得: {len(trend_context)}字")
        prompt = self._build_note_prompt(theme, 500, trend_context=trend_context)

        self._task_results[task_id] = {
            "task_id": task_id,
            "description": f"[note自動] {NOTE_LABEL.get(topic, topic)}",
            "plan": None, "result": None, "suggestions": [],
            "submitted_at": dt.now().isoformat(),
            "completed_at": None, "status": "processing",
        }
        self._persist(task_id)

        from agents.qa_agent import score_article, build_regeneration_prompt

        raw_text = None
        current_prompt = prompt
        for attempt in range(3):  # 最大3回（初回 + 再生成2回）
            try:
                async with asyncio.timeout(480):
                    raw_text = await call_llm(
                        current_prompt,
                        system="あなたは日本語でnote.com向けの高品質な有料記事を書くプロのライターです。",
                        tier="worker",
                    )
            except Exception as e:
                self._task_results[task_id].update({
                    "status": "failed", "result": f"エラー: {e}",
                    "completed_at": dt.now().isoformat(),
                })
                self._persist(task_id)
                self._log_event(f"記事生成失敗: {e}")
                return

            if not raw_text:
                self._log_event("記事生成失敗: 空のレスポンス")
                return

            # QA採点
            qa = await score_article(raw_text)
            self._log_event(f"QA採点: {qa['score']}/10 {'✅' if qa['pass'] else '→ 再生成'}")
            if qa["pass"]:
                break
            if attempt < 2:
                current_prompt = build_regeneration_prompt(prompt, qa["feedback"])
        else:
            # 3回とも不合格でも最後の生成物で続行
            self._log_event("QA: 3回不合格 → 最後の生成物で続行")

        self._task_results[task_id].update({
            "status": "completed", "result": raw_text,
            "completed_at": dt.now().isoformat(),
        })
        self._persist(task_id)
        self._log_event(f"記事生成完了 → note.comに投稿中...")

        loop = asyncio.get_event_loop()

        # note.com に投稿
        try:
            poster = NotePoster()
            result = await poster.post(raw_text, price_yen=500)
            if result["status"] == "published":
                self._log_event(f"✅ note投稿完了: {result.get('url', '')}")
            else:
                self._log_event(f"❌ note投稿失敗: {result.get('error', '')}")
        except Exception as e:
            self._log_event(f"note投稿エラー: {e}")

        # Zenn.dev に同時投稿（SEO強化のため）
        try:
            from services.zenn_poster import ZennPoster, is_configured as zenn_ok
            if zenn_ok():
                zenn = ZennPoster()
                zr = await loop.run_in_executor(None, lambda: zenn.post(raw_text))
                if zr["status"] == "published":
                    self._log_event(f"✅ Zenn投稿完了: {zr.get('url', '')}")
                else:
                    self._log_event(f"⚠️ Zenn投稿失敗: {zr.get('error', '')[:80]}")
        except Exception as e:
            self._log_event(f"Zenn投稿エラー: {e}")

        # Qiita に同時投稿（週1回のみ：スパム判定対策）
        try:
            from services.qiita_poster import QiitaPoster, is_configured as qiita_ok
            this_week = datetime.now().strftime("%Y-W%W")
            if qiita_ok() and self._qiita_last_post_date != this_week:
                products = self._mem.get_gumroad_products() if self._mem else []
                qiita = QiitaPoster()
                qr = await loop.run_in_executor(None, lambda: qiita.post(raw_text, products=products))
                if qr["status"] == "published":
                    self._qiita_last_post_date = this_week
                    self._log_event(f"✅ Qiita投稿完了: {qr.get('url', '')}")
                else:
                    self._log_event(f"⚠️ Qiita投稿失敗: {qr.get('error', '')[:80]}")
            elif self._qiita_last_post_date == this_week:
                self._log_event("Qiita今週投稿済み → スキップ（週1回制限）")
        except Exception as e:
            self._log_event(f"Qiita投稿エラー: {e}")

    async def _run_reddit_post(self):
        note_task = None
        for tid, t in reversed(list(self._task_results.items())):
            if t.get("status") == "completed" and "[note" in t.get("description", "") and t.get("result"):
                note_task = t
                break

        if not note_task:
            self._log_event("Reddit投稿スキップ: 完了済みnote記事なし")
            return

        subreddit = REDDIT_SUBREDDITS[self._reddit_sub_idx % len(REDDIT_SUBREDDITS)]
        self._reddit_sub_idx += 1
        self._log_event(f"Reddit投稿開始: r/{subreddit}")

        # Gumroad CTAをテキストに挿入（有料マーカーの直前）
        raw_text = note_task["result"]
        if self._mem:
            products = self._mem.get_gumroad_products()
            if products:
                p = random.choice(products)
                gumroad_url = f"https://springharu.gumroad.com/l/{p['short_url']}"
                cta_line = f"\n\n---\nRelated resource: [{p['name']}]({gumroad_url})\n\n"
                for marker in ["## 🔒 ここから有料", "ここから有料", "【有料部分】"]:
                    if marker in raw_text:
                        idx = raw_text.index(marker)
                        raw_text = raw_text[:idx] + cta_line + raw_text[idx:]
                        break
                else:
                    raw_text += cta_line

        try:
            from services.reddit_poster import RedditPoster
            poster = RedditPoster()
            result = await poster.post_async(raw_text, subreddit=subreddit)
            if result["status"] == "posted":
                self._log_event(f"✅ Reddit投稿完了: {result.get('url', '')}")
            else:
                self._log_event(f"❌ Reddit投稿失敗: {result.get('error', '')}")
        except Exception as e:
            self._log_event(f"Redditエラー: {e}")

    async def _run_promo_note_post(self):
        """月1回 Gumroad商品プロモ記事を無料note記事として投稿"""
        if not self._mem:
            self._log_event("プロモ記事スキップ: memory未設定")
            return
        products = self._mem.get_gumroad_products()
        if not products:
            self._log_event("プロモ記事スキップ: Gumroad商品なし")
            return

        product = random.choice(products)
        name = product["name"]
        url = f"https://springharu.gumroad.com/l/{product['short_url']}"
        price_yen = int(product["price_usd"]) * 160

        promo_prompt = f"""あなたは日本のnoteクリエイターです。
以下のデジタル商品を紹介する無料note記事を書いてください。
商品名: {name}
商品URL: {url}
価格: ¥{price_yen}

【記事の構成（必ずこの順番で）】

## タイトル
「【無料公開】」で始まるタイトルを1つ（例: 「【無料公開】AIを使って副業収入を増やす実践ガイド」）

## はじめに（300字）
この商品を作った背景・きっかけ。読者の悩みに共感する書き出し。

## この商品で得られること（箇条書き5点）
具体的な数字や成果を含める。

## 内容のサンプル（500字）
商品の一部を無料で公開して価値を示す。

## まとめ・購入リンク（200字）
この記事を読んでくれた方へのメッセージ。
必ず以下の文を含めてください:
「詳しくはこちらから: [{name}]({url})（¥{price_yen}）」

【ルール】全文日本語、合計2000字以上、読者が価値を感じる具体的な内容"""

        from core.llm import call_llm
        self._log_event(f"プロモ記事生成開始: {name}")
        try:
            async with asyncio.timeout(300):
                promo_text = await call_llm(
                    promo_prompt,
                    system="あなたは日本語で魅力的なプロモーション記事を書くエキスパートです。",
                    tier="worker",
                )
        except Exception as e:
            self._log_event(f"プロモ記事生成失敗: {e}")
            return

        if not promo_text:
            self._log_event("プロモ記事生成失敗: 空のレスポンス")
            return

        # note.comに無料記事として投稿
        from services.note_poster import NotePoster
        try:
            poster = NotePoster()
            result = await poster.post(promo_text, price_yen=0)
            if result["status"] == "published":
                self._log_event(f"✅ プロモ記事note投稿完了: {result.get('url', '')}")
            else:
                self._log_event(f"❌ プロモ記事note投稿失敗: {result.get('error', '')}")
        except Exception as e:
            self._log_event(f"プロモ記事note投稿エラー: {e}")

        # Redditにも英語要約を投稿
        try:
            from services.reddit_poster import RedditPoster
            reddit = RedditPoster()
            result = await reddit.post_async(promo_text, subreddit="SideProject")
            if result["status"] == "posted":
                self._log_event(f"✅ プロモ記事Reddit投稿完了: {result.get('url', '')}")
            else:
                self._log_event(f"❌ プロモ記事Reddit投稿失敗: {result.get('error', '')}")
        except Exception as e:
            self._log_event(f"プロモ記事Redditエラー: {e}")

    async def _run_x_morning_post(self):
        """毎日 07:00 X朝投稿: AI Tips + Gumroad商品リンク"""
        from services.x_poster import XPoster, HASHTAGS_JA
        poster = XPoster()
        if not poster.is_configured():
            self._log_event("X朝投稿スキップ: 未ログイン（python services/x_auth.py を実行）")
            return

        # Gumroad商品を選んで CTA 生成
        product_line = ""
        if self._mem:
            products = self._mem.get_gumroad_products()
            if products:
                p = random.choice(products)
                gumroad_url = f"https://springharu.gumroad.com/l/{p['short_url']}"
                price_j = int(p["price_usd"]) * 160
                product_line = f"\n\n👉 {p['name']}（¥{price_j}）\n{gumroad_url}"

        # Tips ツイートを LLM で生成（140字以内）
        tips_topics = [
            "ChatGPTで副業収入を増やす1つの習慣",
            "AIツールで作業時間を半分にする方法",
            "note.comで記事が読まれるタイトルの法則",
            "フリーランスで月5万円稼ぐための最初の1歩",
            "生成AIを使ったコンテンツ販売の始め方",
        ]
        topic = random.choice(tips_topics)

        from core.llm import call_llm
        prompt = f"""以下のテーマで、Xに投稿するツイートを1つ書いてください。
テーマ: {topic}
条件:
- 120字以内
- 具体的なTipsや数字を含める
- 読者が「役立つ！」と思える内容
- ハッシュタグは含めない（後で追加する）
ツイート本文のみ出力してください（前置き不要）。"""

        try:
            async with asyncio.timeout(60):
                tips_text = await call_llm(prompt, tier="worker")
        except Exception as e:
            self._log_event(f"X朝投稿 LLM失敗: {e}")
            return

        tweet = f"{tips_text.strip()}{product_line}\n\n{HASHTAGS_JA}"
        self._log_event(f"X朝投稿開始")
        result = await poster.post_async(tweet)
        if result["status"] == "posted":
            self._log_event(f"✅ X朝投稿完了: {result.get('url', '')}")
        else:
            self._log_event(f"❌ X朝投稿失敗: {result.get('error', '')}")

    async def _run_x_evening_post(self):
        """毎日 19:00 X夜投稿: 直近note記事の要約"""
        from services.x_poster import XPoster, HASHTAGS_JA
        poster = XPoster()
        if not poster.is_configured():
            self._log_event("X夜投稿スキップ: 未ログイン")
            return

        # 最近のnote記事を取得
        note_task = None
        for tid, t in reversed(list(self._task_results.items())):
            if t.get("status") == "completed" and "[note" in t.get("description", "") and t.get("result"):
                note_task = t
                break

        if not note_task:
            self._log_event("X夜投稿スキップ: note記事なし")
            return

        from core.llm import call_llm
        summary_prompt = f"""以下のnote記事を、Xのツイート用に要約してください。
条件:
- 100字以内
- 「この記事では〜」という始め方ではなく、価値を直接伝える
- note.com で読めることを示唆する一文を入れる
- ハッシュタグは含めない

記事内容（冒頭）:
{note_task['result'][:500]}

ツイート本文のみ出力してください。"""

        try:
            async with asyncio.timeout(60):
                summary = await call_llm(summary_prompt, tier="worker")
        except Exception as e:
            self._log_event(f"X夜投稿 LLM失敗: {e}")
            return

        tweet = f"{summary.strip()}\n\n{HASHTAGS_JA}"
        self._log_event("X夜投稿開始")
        result = await poster.post_async(tweet)
        if result["status"] == "posted":
            self._log_event(f"✅ X夜投稿完了: {result.get('url', '')}")
        else:
            self._log_event(f"❌ X夜投稿失敗: {result.get('error', '')}")

    async def _run_new_product(self):
        """月1回 Gumroad新商品を自動生成"""
        from api.app import _run_gumroad_product, GUMROAD_PRODUCT_TYPES
        import uuid
        from datetime import datetime as dt

        product_types = list(GUMROAD_PRODUCT_TYPES.keys())
        current_idx = int(self._mem.get_config("gumroad_product_type_idx", "0")) if self._mem else 0
        product_type = product_types[current_idx % len(product_types)]
        if self._mem:
            self._mem.set_config("gumroad_product_type_idx", str(current_idx + 1))

        task_id = uuid.uuid4().hex[:8]
        self._task_results[task_id] = {
            "task_id": task_id,
            "description": f"[月次自動] Gumroad新商品: {product_type}",
            "plan": None, "result": None, "suggestions": [],
            "submitted_at": dt.now().isoformat(),
            "completed_at": None, "status": "processing",
        }
        self._persist(task_id)

        self._log_event(f"月次新商品生成開始: {product_type}")
        await _run_gumroad_product(task_id, product_type)
        self._log_event(f"月次新商品生成完了: {self._task_results[task_id]['status']}")

    def _build_note_prompt(self, theme: str, price_yen: int, trend_context: str = "") -> str:
        # Gumroad CTA（商品がある場合のみ）
        cta_block = ""
        if self._mem:
            products = self._mem.get_gumroad_products()
            if products:
                p = random.choice(products)
                gumroad_url = f"https://springharu.gumroad.com/l/{p['short_url']}"
                price_j = int(p["price_usd"]) * 160
                cta_block = f"""
## 🎁 コピペで使える実践テンプレートを手に入れる

この記事の内容をすぐ実践に移したい方へ、すぐ使えるツールを用意しています。

**→ [{p["name"]}]({gumroad_url})**
✅ コピペで今日から使える　✅ ¥{price_j}（コーヒー1杯分）

---
"""

        trend_block = f"\n{trend_context}\n" if trend_context else ""

        return f"""あなたは副業・AI活用分野のnote.com公認クリエイターです。
以下の指示に100%従い、読者を「読んで良かった。続きを買いたい」と思わせる有料記事を書いてください。

テーマ: {theme}
想定読者: 副業・AI活用に挑戦中だが成果が出ていない20〜40代の会社員
記事価格: {price_yen}円
{trend_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【タイトル】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
以下の条件を満たすタイトルを1つだけ書いてください（## タイトル: 〇〇 の形式）：
- ロングテールキーワード（具体的な悩みや状況）を含む
- 数字・年号・期間・金額のうち2つ以上を含む
- 結果が想像できる（例：「月3万円」「2週間で」「7割削減」）
- 40字以内

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【無料部分：以下の構成を厳守すること】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## なぜ多くの人が{theme}で結果を出せないのか（350〜400字）

「〇〇を試したのに、なぜか上手くいかない」——そんな経験はありませんか？　から始める。
読者が共感する失敗パターンを2〜3つ、具体的なシーン付きで描写する。
「実はその悩みには、明確な理由があります」と次のセクションへ引き込む。

## {theme}で成果を出す人が密かにやっている3つのこと（900〜1000字）

各項目を以下のフォーマットで書く：

**① 〇〇する（見出し）**
- なぜ効くのか：（50字以内で根拠を説明）
- 具体的にやること：（実際の手順を2〜3文）
- 実践例：「〇〇さんはこの方法で△日後に□□の結果を出しました」
- すぐできる一歩：「今日の15分でできること：〇〇する」

**② 〇〇を先に決める（見出し）**
（同じフォーマット）

**③ 〇〇だけに集中する（見出し）**
（同じフォーマット）

セクション末尾に：「ここまでは基本です。ただ、ほとんどの人はここで止まります。」と書く。
{cta_block}
## 🔒 ここから有料（{price_yen}円）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【有料部分：以下の構成を厳守すること】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 【完全版】今日から使える実践マニュアル（1500字以上）

### STEP 1〜STEP 5（番号付きリスト）
各ステップは：何をするか・なぜするか・具体的な数値目安 を含める。

### すぐ使えるテンプレート
コードブロック（```）形式で、コピペして使えるテンプレートを1つ以上提示する。

### よくある疑問 Q&A
Q1：〇〇の場合はどうすればいいですか？
A1：（具体的な回答）
（3問以上）

### 今週できる最初の一歩
読んだ直後に30分以内で完了できるアクションを1つだけ書く。
「まず〇〇して、次に△△するだけです。それだけで□□が変わります。」で締める。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【執筆の絶対ルール】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- **一人称・体験談口調で書く**：「私が実際に試した結果〜」「最初は全然うまくいかなかったんですが〜」「正直に言うと〜」「やってみて気づいたのは〜」という語り口を随所に入れる
- **失敗談を必ず1つ入れる**：完璧な成功談より「こういう失敗をしてから気づいた」の方が読者に刺さる
- **断定より語りかけ**：「〜できます」より「〜できるようになりました」「〜してみたら意外と〜でした」
- 全文日本語、話しかけるような口語調（「〜ですよね」「〜じゃないですか」も使ってOK）
- 具体的な数字・期間・金額を必ず入れる（「約2週間」「月3万円」「30分で」）
- 曖昧な表現禁止：「〜かもしれません」は使わない
- 無料部分と有料部分を合わせて合計3,000字以上書く
- ## タイトル: の直後から記事本文を始める（前置きや説明文は不要）"""
