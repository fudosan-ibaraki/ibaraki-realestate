from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user, login_required, current_user
)
from functools import wraps
import bcrypt
import os
import sqlite3
import pandas as pd
import numpy as np
import pickle
from datetime import datetime
import stripe

app = Flask(__name__)
app.config["SECRET_KEY"]              = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

db            = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view    = "login"
login_manager.login_message = "ログインが必要です。"

REALESTATE_DB = os.path.join(os.path.dirname(__file__), "..", "ibaraki_realestate.db")

# ── Stripe設定 ────────────────────────────────────────────
stripe.api_key            = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID           = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET     = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ── Random Forest モデル読み込み（マンション・宅地 別モデル）────
_RF_MANSION_PATH = os.path.join(os.path.dirname(__file__), "model_rf_mansion.pkl")
_RF_LAND_PATH    = os.path.join(os.path.dirname(__file__), "model_rf_land.pkl")
_rf_mansion = None
_rf_land    = None

def get_rf_mansion():
    global _rf_mansion
    if _rf_mansion is None and os.path.exists(_RF_MANSION_PATH):
        with open(_RF_MANSION_PATH, "rb") as f:
            _rf_mansion = pickle.load(f)
    return _rf_mansion

def get_rf_land():
    global _rf_land
    if _rf_land is None and os.path.exists(_RF_LAND_PATH):
        with open(_RF_LAND_PATH, "rb") as f:
            _rf_land = pickle.load(f)
    return _rf_land


# ── モデル ────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id                      = db.Column(db.Integer,     primary_key=True)
    email                   = db.Column(db.String(120), unique=True, nullable=False)
    username                = db.Column(db.String(80),  unique=True, nullable=False)
    password                = db.Column(db.String(200), nullable=False)
    plan                    = db.Column(db.String(20),  default="free")
    created_at              = db.Column(db.DateTime,    default=datetime.utcnow)
    stripe_customer_id      = db.Column(db.String(100), nullable=True)
    stripe_subscription_id  = db.Column(db.String(100), nullable=True)

    def set_password(self, password):
        self.password = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password):
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password.encode("utf-8")
        )


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ── ページ定義 ────────────────────────────────────────────
PAGES = {
    "home":  {"title": "ホーム",          "icon": "🏠", "plan": "free",    "section": "menu"},
    "guide": {"title": "ガイドライン",     "icon": "📋", "plan": "free",    "section": "menu"},
    "map":   {"title": "地図",            "icon": "🗺️", "plan": "premium", "section": "menu"},
    "g01":   {"title": "価格トレンド",     "icon": "📈", "plan": "free",    "section": "graph"},
    "g02":   {"title": "築年数と価格",     "icon": "🏗️", "plan": "free",    "section": "graph"},
    "g03":   {"title": "駅距離と価格",     "icon": "🚉", "plan": "premium", "section": "graph"},
    "g04":   {"title": "間取り別価格",     "icon": "🏢", "plan": "free",    "section": "graph"},
    "g05":   {"title": "割安・割高",       "icon": "📊", "plan": "premium", "section": "graph"},
    "g06":   {"title": "利便性と価格",     "icon": "🏪", "plan": "premium", "section": "graph"},
    "g07":   {"title": "浸水リスク別",     "icon": "⚠️", "plan": "premium", "section": "graph"},
    "g08":   {"title": "乖離率推移",       "icon": "📉", "plan": "premium", "section": "graph"},
    "g09":   {"title": "エリアレポート",   "icon": "📝", "plan": "premium", "section": "graph"},
}


# ── 管理者チェック ────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.plan != "admin":
            flash("管理者権限が必要です。", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    """APIエンドポイント用: 未認証時にJSONでエラーを返す"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── 通常ルート ────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("dashboard", page="home"))


def get_page_settings():
    import json
    settings_path = os.path.join(os.path.dirname(__file__), "page_settings.json")
    default = {pid: {"visible": True, "plan": PAGES[pid]["plan"]} for pid in PAGES}
    if not os.path.exists(settings_path):
        return default
    with open(settings_path, encoding="utf-8") as f:
        loaded = json.load(f)
    for pid in PAGES:
        v = loaded.get(pid, default[pid])
        if isinstance(v, bool):
            default[pid] = {"visible": v, "plan": PAGES[pid]["plan"]}
        else:
            default[pid] = v
    return default


@app.route("/dashboard")
@app.route("/dashboard/<page>")
@login_required
def dashboard(page="home"):
    if page not in PAGES:
        page = "home"
    settings  = get_page_settings()
    page_plan = settings[page]["plan"]
    if page_plan == "premium" and current_user.plan not in ("premium", "admin"):
        flash("このページは有料会員専用です。", "warning")
        return redirect(url_for("upgrade"))
    dynamic_pages = {pid: {**info, "plan": settings[pid]["plan"]} for pid, info in PAGES.items()}
    page_info = dynamic_pages[page]
    return render_template("dashboard.html", page=page, pages=dynamic_pages, page_info=page_info)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user     = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash("メールアドレスまたはパスワードが正しくありません。", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")
        if not username or not email or not password:
            flash("すべての項目を入力してください。", "error")
        elif password != confirm:
            flash("パスワードが一致しません。", "error")
        elif len(password) < 8:
            flash("パスワードは8文字以上にしてください。", "error")
        elif User.query.filter_by(email=email).first():
            flash("このメールアドレスはすでに登録されています。", "error")
        elif User.query.filter_by(username=username).first():
            flash("このユーザー名はすでに使われています。", "error")
        else:
            user = User(username=username, email=email, plan="free")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("登録完了しました！", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ログアウトしました。", "success")
    return redirect(url_for("login"))


@app.route("/upgrade")
@login_required
def upgrade():
    return render_template("upgrade.html")


@app.route("/account")
@login_required
def account():
    return render_template("account.html")


# ── 価格推定 ──────────────────────────────────────────────
@app.route("/estimate")
@login_required
def estimate():
    conn   = sqlite3.connect(REALESTATE_DB)
    cities = [row[0] for row in conn.execute(
        "SELECT DISTINCT city_name FROM csv_transactions WHERE city_name IS NOT NULL ORDER BY city_name"
    ).fetchall()]
    conn.close()
    opt_list = []
    for c in cities:
        opt_list.append('<option value="' + c + '">' + c + '</option>')
    options   = '\n'.join(opt_list)
    html_path = os.path.join(os.path.dirname(__file__), "templates", "estimate_base.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("CITY_OPTIONS_PLACEHOLDER", options)
    return Response(html, mimetype="text/html; charset=utf-8")


@app.route("/api/estimate")
@login_required
def api_estimate():
    city_name      = request.args.get("city_name", "")
    trade_type     = request.args.get("trade_type", "")
    area           = request.args.get("area",           type=float)
    building_age   = request.args.get("building_age",   type=int)
    floor_plan     = request.args.get("floor_plan",     "")
    district       = request.args.get("district",       "")
    station_dist   = request.args.get("station_dist",   type=float)
    hazard_risk    = request.args.get("hazard_risk",    "指定なし")
    conv_score_min = request.args.get("conv_score_min", type=float)

    conditions = ["trade_price IS NOT NULL", "trade_price > 0"]
    params     = []

    if city_name:
        conditions.append("city_name = ?");        params.append(city_name)
    if trade_type:
        conditions.append("trade_type LIKE ?");    params.append("%" + trade_type + "%")
    if area:
        # ±40%の範囲で類似物件を検索
        conditions.append("area BETWEEN ? AND ?"); params.append(area * 0.6); params.append(area * 1.4)
    if building_age is not None:
        year = 2025 - building_age
        conditions.append("building_year BETWEEN ? AND ?"); params.append(year - 8); params.append(year + 8)
    if floor_plan:
        conditions.append("floor_plan = ?");       params.append(floor_plan)
    if district:
        conditions.append("district = ?");         params.append(district)
    if station_dist:
        conditions.append("nearest_station_dist <= ?"); params.append(station_dist)
    if hazard_risk and hazard_risk != "指定なし":
        conditions.append("hazard_risk = ?");      params.append(hazard_risk)
    if conv_score_min:
        conditions.append("convenience_score >= ?"); params.append(conv_score_min)

    conn = sqlite3.connect(REALESTATE_DB)
    sql_base = "SELECT trade_price, area, building_year, nearest_station_name, nearest_station_dist, hazard_risk, convenience_score, district, year, floor_plan FROM csv_transactions WHERE "

    df = pd.read_sql(sql_base + " AND ".join(conditions) + " ORDER BY year DESC LIMIT 500", conn, params=params)

    # 件数が少ない場合、地区条件を外してリトライ
    if len(df) < 10 and district:
        conditions_fallback = [c for c in conditions if "district" not in c]
        params_fallback     = [params[i] for i, c in enumerate(conditions) if "district" not in c]
        df = pd.read_sql(sql_base + " AND ".join(conditions_fallback) + " ORDER BY year DESC LIMIT 500", conn, params=params_fallback)

    conn.close()

    if len(df) == 0:
        return jsonify({"error": "条件に一致するデータがありません。条件を緩めてみてください。"})

    prices              = df["trade_price"].dropna()
    df["price_per_sqm"] = df["trade_price"] / df["area"]

    samples = []
    for _, r in df.head(5).iterrows():
        samples.append({
            "trade_price_man":     round(float(r["trade_price"]) / 10000),
            "area":                float(r["area"]) if r["area"] else None,
            "age":                 int(2024 - r["building_year"]) if r["building_year"] else None,
            "nearest_station_name": r["nearest_station_name"],
            "station_dist_m":      round(float(r["nearest_station_dist"])) if r["nearest_station_dist"] else None,
            "hazard_risk":         r["hazard_risk"],
            "district":            r["district"],
            "floor_plan":          r["floor_plan"],
            "year":                int(r["year"]) if r["year"] else None,
        })

    return jsonify({
        "count":      int(len(prices)),
        "median":     round(float(prices.median())       / 10000, 1),
        "q25":        round(float(prices.quantile(0.25)) / 10000, 1),
        "q75":        round(float(prices.quantile(0.75)) / 10000, 1),
        "mean":       round(float(prices.mean())         / 10000, 1),
        "min":        round(float(prices.min())          / 10000, 1),
        "max":        round(float(prices.max())          / 10000, 1),
        "sqm_median": int(df["price_per_sqm"].median()),
        "samples":    samples,
    })


@app.route("/api/estimate_rf")
@login_required
def api_estimate_rf():
    """Random Forest による価格予測（マンション・宅地 別モデル）"""
    import numpy as np

    trade_type   = request.args.get("trade_type", "").strip()
    city_name    = request.args.get("city_name",  "").strip()
    district     = request.args.get("district",   "").strip()
    floor_plan   = request.args.get("floor_plan", "").strip()
    area         = request.args.get("area",         type=float)
    building_age = request.args.get("building_age", type=int)
    station_dist = request.args.get("station_dist", type=float)
    hazard_risk  = request.args.get("hazard_risk",  "不明")
    conv_score   = request.args.get("conv_score",   type=float)

    if not all([city_name, trade_type, area]):
        return jsonify({"error": "city_name, trade_type, area は必須です。"}), 400

    is_mansion = "マンション" in trade_type

    if is_mansion:
        bundle = get_rf_mansion()
    else:
        bundle = get_rf_land()

    if bundle is None:
        return jsonify({"error": "モデルが未学習です。train_model.py を実行してください。"}), 503

    def safe_enc(le, val):
        val = val if (val and val in le.classes_) else le.classes_[0]
        return int(le.transform([val])[0])

    city_enc     = safe_enc(bundle["le_city"],     city_name)
    district_enc = safe_enc(bundle["le_district"],  district or "不明")
    hazard_enc   = safe_enc(bundle["le_hazard"],    hazard_risk or "不明")

    age  = building_age if building_age is not None else 20
    dist = station_dist if station_dist is not None else 1500
    conv = conv_score   if conv_score   is not None else 30

    if is_mansion:
        floor_enc = safe_enc(bundle["le_floor"], floor_plan or "不明")
        X = np.array([[city_enc, district_enc, floor_enc, area, age, dist, hazard_enc, conv]])
    else:
        X = np.array([[city_enc, district_enc, area, dist, hazard_enc, conv]])

    model    = bundle["model"]
    log_pred = model.predict(X)[0]

    # 宅地は㎡単価モデル → 総額に変換
    if bundle.get("predict_sqm") and not is_mansion:
        sqm_pred  = float(np.expm1(log_pred))
        predicted = sqm_pred * area
        tree_sqm  = np.expm1([t.predict(X)[0] for t in model.estimators_])
        std       = float(np.std(tree_sqm)) * area
    else:
        predicted  = float(np.expm1(log_pred))
        tree_preds = np.expm1([t.predict(X)[0] for t in model.estimators_])
        std        = float(np.std(tree_preds))

    return jsonify({
        "predicted_man": round(predicted / 10000, 1),
        "lower_man":     round(max(0, predicted - std) / 10000, 1),
        "upper_man":     round((predicted + std) / 10000, 1),
        "city_name":     city_name,
        "trade_type":    trade_type,
        "area":          area,
        "building_age":  age,
        "station_dist":  dist,
        "hazard_risk":   hazard_risk,
        "conv_score":    conv,
    })


# ── 管理者ルート ──────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_index():
    users   = User.query.order_by(User.created_at.desc()).all()
    total   = len(users)
    premium = sum(1 for u in users if u.plan == "premium")
    free    = sum(1 for u in users if u.plan == "free")
    return render_template("admin/index.html",
        users=users, total=total, premium=premium, free=free)


@app.route("/admin/user/<int:user_id>/plan", methods=["POST"])
@login_required
@admin_required
def admin_change_plan(user_id):
    user     = User.query.get_or_404(user_id)
    new_plan = request.form.get("plan")
    if new_plan in ("free", "premium", "admin"):
        user.plan = new_plan
        db.session.commit()
        flash(user.username + " のプランを " + new_plan + " に変更しました。", "success")
    return redirect(url_for("admin_index"))


@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.plan == "admin":
        flash("管理者ユーザーは削除できません。", "error")
        return redirect(url_for("admin_index"))
    db.session.delete(user)
    db.session.commit()
    flash(user.username + " を削除しました。", "success")
    return redirect(url_for("admin_index"))


@app.route("/admin/notice", methods=["GET", "POST"])
@login_required
@admin_required
def admin_notice():
    notice_path = os.path.join(os.path.dirname(__file__), "notice.txt")
    if request.method == "POST":
        notice_text = request.form.get("notice", "")
        with open(notice_path, "w", encoding="utf-8") as f:
            f.write(notice_text)
        flash("お知らせを更新しました。", "success")
        return redirect(url_for("admin_notice"))
    notice_text = ""
    if os.path.exists(notice_path):
        with open(notice_path, encoding="utf-8") as f:
            notice_text = f.read()
    return render_template("admin/notice.html", notice_text=notice_text)


@app.route("/admin/pages", methods=["GET", "POST"])
@login_required
@admin_required
def admin_pages():
    import json
    settings_path    = os.path.join(os.path.dirname(__file__), "page_settings.json")
    default_settings = {pid: {"visible": True, "plan": PAGES[pid]["plan"]} for pid in PAGES}
    if request.method == "POST":
        settings = {}
        for pid in PAGES:
            settings[pid] = {
                "visible": request.form.get(pid + "_visible") == "on",
                "plan":    request.form.get(pid + "_plan", PAGES[pid]["plan"]),
            }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)
        flash("ページ設定を更新しました。", "success")
        return redirect(url_for("admin_pages"))
    settings = default_settings
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            loaded = json.load(f)
            # 旧形式（bool）との互換
            for pid in PAGES:
                v = loaded.get(pid, default_settings[pid])
                if isinstance(v, bool):
                    settings[pid] = {"visible": v, "plan": PAGES[pid]["plan"]}
                else:
                    settings[pid] = v
    return render_template("admin/pages.html", pages=PAGES, settings=settings)


# ── Stripe 決済ルート ─────────────────────────────────────
@app.route("/stripe/create-checkout", methods=["POST"])
@login_required
def stripe_create_checkout():
    """Stripeチェックアウトセッションを作成してリダイレクト"""
    try:
        customer_id = current_user.stripe_customer_id
        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": current_user.id, "username": current_user.username}
            )
            customer_id = customer.id
            current_user.stripe_customer_id = customer_id
            db.session.commit()

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            mode="subscription",
            success_url=url_for("stripe_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("upgrade", _external=True),
            locale="ja",
        )
        return redirect(session.url, code=303)
    except Exception as e:
        flash(f"決済の開始に失敗しました: {str(e)}", "error")
        return redirect(url_for("upgrade"))


@app.route("/stripe/success")
@login_required
def stripe_success():
    """決済成功後のリダイレクト先"""
    session_id = request.args.get("session_id")
    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            sub_id  = session.get("subscription")
            if sub_id:
                current_user.stripe_subscription_id = sub_id
                current_user.plan = "premium"
                db.session.commit()
        except Exception:
            pass
    flash("プレミアムプランへのアップグレードが完了しました！", "success")
    return redirect(url_for("dashboard"))


@app.route("/stripe/cancel-subscription", methods=["POST"])
@login_required
def stripe_cancel_subscription():
    """サブスクリプションを期末でキャンセル"""
    sub_id = current_user.stripe_subscription_id
    if not sub_id:
        flash("有効なサブスクリプションが見つかりません。", "error")
        return redirect(url_for("account"))
    try:
        stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
        flash("サブスクリプションのキャンセルを受け付けました。現在の請求期間終了後に無効になります。", "success")
    except Exception as e:
        flash(f"キャンセル処理に失敗しました: {str(e)}", "error")
    return redirect(url_for("account"))


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """StripeからのWebhookを受信してプラン状態を同期"""
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return jsonify({"error": "invalid signature"}), 400

    etype = event["type"]
    data  = event["data"]["object"]

    if etype == "customer.subscription.deleted":
        user = User.query.filter_by(stripe_subscription_id=data["id"]).first()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            db.session.commit()

    elif etype == "customer.subscription.updated":
        user = User.query.filter_by(stripe_subscription_id=data["id"]).first()
        if user:
            status = data.get("status")
            if status == "active":
                user.plan = "premium"
            elif status in ("canceled", "unpaid", "past_due"):
                user.plan = "free"
            db.session.commit()

    elif etype == "invoice.payment_failed":
        cus_id = data.get("customer")
        user   = User.query.filter_by(stripe_customer_id=cus_id).first()
        if user:
            user.plan = "free"
            db.session.commit()

    return jsonify({"status": "ok"})


# ── エリアレポート API ────────────────────────────────────
@app.route("/api/districts")
@api_login_required
def api_districts():
    """市区町村に紐づく地区一覧を返す"""
    city_name = request.args.get("city_name", "").strip()
    if not city_name:
        return jsonify({"districts": []})
    conn = sqlite3.connect(REALESTATE_DB)
    rows = conn.execute("""
        SELECT DISTINCT district FROM csv_transactions
        WHERE city_name=? AND district IS NOT NULL AND district != ''
        ORDER BY district
    """, (city_name,)).fetchall()
    conn.close()
    return jsonify({"districts": [r[0] for r in rows]})


@app.route("/api/city_report_cities")
@api_login_required
def api_city_report_cities():
    conn   = sqlite3.connect(REALESTATE_DB)
    cities = [row[0] for row in conn.execute(
        "SELECT DISTINCT city_name FROM csv_transactions WHERE city_name IS NOT NULL ORDER BY city_name"
    ).fetchall()]
    conn.close()
    return jsonify({"cities": cities})


@app.route("/api/city_report")
@api_login_required
def api_city_report():
    city_name = request.args.get("city_name", "").strip()
    if not city_name:
        return jsonify({"error": "city_nameが必要です"})

    conn = sqlite3.connect(REALESTATE_DB)

    mansion = conn.execute("""
        SELECT COUNT(*), ROUND(AVG(trade_price)/10000,1), ROUND(AVG(price_per_sqm)),
               ROUND(AVG(2025 - building_year), 1)
        FROM csv_transactions
        WHERE city_name=? AND trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL AND trade_price>0
    """, (city_name,)).fetchone()

    mansion_vals = [r[0] for r in conn.execute("""
        SELECT trade_price/10000 FROM csv_transactions
        WHERE city_name=? AND trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL AND trade_price>0 ORDER BY trade_price
    """, (city_name,)).fetchall()]
    mansion_median = mansion_vals[len(mansion_vals)//2] if mansion_vals else None

    land = conn.execute("""
        SELECT COUNT(*) FROM csv_transactions
        WHERE city_name=? AND trade_type LIKE '%宅地%'
          AND trade_price IS NOT NULL AND trade_price>0
    """, (city_name,)).fetchone()

    land_sqm_vals = [r[0] for r in conn.execute("""
        SELECT price_per_sqm FROM csv_transactions
        WHERE city_name=? AND trade_type LIKE '%宅地%'
          AND price_per_sqm IS NOT NULL AND price_per_sqm>0 ORDER BY price_per_sqm
    """, (city_name,)).fetchall()]
    land_median_sqm = land_sqm_vals[len(land_sqm_vals)//2] if land_sqm_vals else None

    station_row = conn.execute("""
        SELECT ROUND(AVG(nearest_station_dist)) FROM csv_transactions
        WHERE city_name=? AND nearest_station_dist IS NOT NULL
    """, (city_name,)).fetchone()

    top_stations = [r[0] for r in conn.execute("""
        SELECT nearest_station_name, COUNT(*) AS cnt FROM csv_transactions
        WHERE city_name=? AND nearest_station_name IS NOT NULL
        GROUP BY nearest_station_name ORDER BY cnt DESC LIMIT 3
    """, (city_name,)).fetchall()]

    hazard_row = conn.execute("""
        SELECT SUM(CASE WHEN hazard_risk IN ('なし','低') THEN 1 ELSE 0 END)*100.0/COUNT(*)
        FROM csv_transactions WHERE city_name=? AND hazard_risk IS NOT NULL
    """, (city_name,)).fetchone()
    hazard_safe_pct = round(hazard_row[0]) if hazard_row and hazard_row[0] is not None else None

    conv_row = conn.execute("""
        SELECT ROUND(AVG(convenience_score),2) FROM csv_transactions
        WHERE city_name=? AND convenience_score IS NOT NULL
    """, (city_name,)).fetchone()

    trend_row = conn.execute("""
        SELECT year, ROUND(AVG(trade_price)/10000,1) FROM csv_transactions
        WHERE city_name=? AND trade_price IS NOT NULL AND year IS NOT NULL
        GROUP BY year ORDER BY year
    """, (city_name,)).fetchall()
    price_trend_pct = None
    if len(trend_row) >= 2:
        old_p, new_p = trend_row[0][1], trend_row[-1][1]
        if old_p and old_p > 0:
            price_trend_pct = round((new_p - old_p) / old_p * 100, 1)

    total_row = conn.execute("""
        SELECT COUNT(*) FROM csv_transactions
        WHERE city_name=? AND trade_price IS NOT NULL AND trade_price>0
    """, (city_name,)).fetchone()

    # 人口データ（最新年）
    pop_row = conn.execute("""
        SELECT population, pop_change_rate, pop_density, households, area_km2, year
        FROM population
        WHERE city_name=?
        ORDER BY year DESC LIMIT 1
    """, (city_name,)).fetchone()

    conn.close()

    pop_data = {}
    if pop_row:
        pop_data = {
            "population":       int(pop_row[0]) if pop_row[0] else None,
            "pop_change_rate":  float(pop_row[1]) if pop_row[1] else None,
            "pop_density":      float(pop_row[2]) if pop_row[2] else None,
            "households":       int(pop_row[3]) if pop_row[3] else None,
            "area_km2":         float(pop_row[4]) if pop_row[4] else None,
            "pop_year":         int(pop_row[5]) if pop_row[5] else None,
        }

    return jsonify({
        "city":            city_name,
        "mansion_count":   int(mansion[0]) if mansion[0] else 0,
        "mansion_median":  mansion_median,
        "avg_building_age": float(mansion[3]) if mansion and mansion[3] else None,
        "land_count":      int(land[0]) if land and land[0] else 0,
        "land_median_sqm": land_median_sqm,
        "avg_station_dist": float(station_row[0]) if station_row and station_row[0] else None,
        "top_stations":    top_stations,
        "hazard_safe_pct": hazard_safe_pct,
        "avg_conv_score":  float(conv_row[0]) if conv_row and conv_row[0] else None,
        "price_trend_pct": price_trend_pct,
        "total_count":     int(total_row[0]) if total_row else 0,
        **pop_data,
    })


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
