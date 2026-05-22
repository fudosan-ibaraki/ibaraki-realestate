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
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"]              = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

db            = SQLAlchemy(app)
login_manager = LoginManager(app)

# Render等のWSGI環境でもテーブルを自動作成
with app.app_context():
    db.create_all()
login_manager.login_view    = "login"
login_manager.login_message = "ログインが必要です。"

REALESTATE_DB = os.path.join(os.path.dirname(__file__), "..", "ibaraki_realestate.db")


# ── モデル ────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id         = db.Column(db.Integer,     primary_key=True)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    username   = db.Column(db.String(80),  unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)
    plan       = db.Column(db.String(20),  default="free")
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

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


class PageView(db.Model):
    id          = db.Column(db.Integer,  primary_key=True)
    page        = db.Column(db.String(20), nullable=False, index=True)
    user_id     = db.Column(db.Integer,  db.ForeignKey("user.id"), nullable=True)
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


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
    # アクセス記録（admin除外・別スレッドで実行してレスポンスを遅延させない）
    if current_user.plan != "admin":
        user_id = current_user.id
        def _record():
            with app.app_context():
                db.session.add(PageView(page=page, user_id=user_id))
                db.session.commit()
        import threading
        threading.Thread(target=_record, daemon=True).start()
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
    area_min       = request.args.get("area_min",       type=float)
    area_max       = request.args.get("area_max",       type=float)
    age_min        = request.args.get("age_min",        type=int)
    age_max        = request.args.get("age_max",        type=int)
    station_dist   = request.args.get("station_dist",   type=float)
    hazard_risk    = request.args.get("hazard_risk",    "指定なし")
    conv_score_min = request.args.get("conv_score_min", type=float)

    conditions = ["trade_price IS NOT NULL", "trade_price > 0"]
    params     = []

    if city_name:
        conditions.append("city_name = ?");        params.append(city_name)
    if trade_type:
        conditions.append("trade_type LIKE ?");    params.append("%" + trade_type + "%")
    if area_min:
        conditions.append("area >= ?");            params.append(area_min)
    if area_max:
        conditions.append("area <= ?");            params.append(area_max)
    if age_min:
        conditions.append("building_year <= ?");   params.append(2024 - age_min)
    if age_max:
        conditions.append("building_year >= ?");   params.append(2024 - age_max)
    if station_dist:
        conditions.append("nearest_station_dist <= ?"); params.append(station_dist)
    if hazard_risk and hazard_risk != "指定なし":
        conditions.append("hazard_risk = ?");      params.append(hazard_risk)
    if conv_score_min:
        conditions.append("convenience_score >= ?"); params.append(conv_score_min)

    conn = sqlite3.connect(REALESTATE_DB)
    df   = pd.read_sql(
        "SELECT trade_price, area, building_year, nearest_station_name, nearest_station_dist, hazard_risk, convenience_score, district, year, floor_plan FROM csv_transactions WHERE " + " AND ".join(conditions) + " ORDER BY year DESC LIMIT 500",
        conn, params=params
    )
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


# ── 管理者ルート ──────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_index():
    users   = User.query.order_by(User.created_at.desc()).all()
    total   = len(users)
    premium = sum(1 for u in users if u.plan == "premium")
    free    = sum(1 for u in users if u.plan == "free")

    # アクセス集計（ページ別総数 & 直近30日）
    from sqlalchemy import func, text
    from datetime import timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    pv_total = db.session.query(
        PageView.page, func.count(PageView.id).label("cnt")
    ).group_by(PageView.page).all()
    pv_total_dict = {row.page: row.cnt for row in pv_total}

    pv_recent = db.session.query(
        PageView.page, func.count(PageView.id).label("cnt")
    ).filter(PageView.accessed_at >= thirty_days_ago).group_by(PageView.page).all()
    pv_recent_dict = {row.page: row.cnt for row in pv_recent}

    total_pv       = sum(pv_total_dict.values())
    total_pv_recent = sum(pv_recent_dict.values())

    page_stats = []
    for pid, info in PAGES.items():
        page_stats.append({
            "id":     pid,
            "title":  info["title"],
            "total":  pv_total_dict.get(pid, 0),
            "recent": pv_recent_dict.get(pid, 0),
        })
    page_stats.sort(key=lambda x: x["total"], reverse=True)

    return render_template("admin/index.html",
        users=users, total=total, premium=premium, free=free,
        total_pv=total_pv, total_pv_recent=total_pv_recent, page_stats=page_stats)


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


# ── 起動 ─────────────────────────────────────────────────
# ── 管理者機能 ── app.pyに追記する内容 ──────────────────
# 以下を app.py の最後（if __name__ == "__main__": の前）に追記してください

# ── 管理者チェックデコレータ ─────────────────────────────
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.plan != "admin":
            flash("管理者権限が必要です。", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)

# ── エリアレポート API ────────────────────────────────────
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
