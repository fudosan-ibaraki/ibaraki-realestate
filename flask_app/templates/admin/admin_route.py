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


# ── 管理者ページ ──────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_index():
    users      = User.query.order_by(User.created_at.desc()).all()
    total      = len(users)
    premium    = sum(1 for u in users if u.plan == "premium")
    free       = sum(1 for u in users if u.plan == "free")
    return render_template("admin/index.html",
        users=users, total=total, premium=premium, free=free)


@app.route("/admin/user/<int:user_id>/plan", methods=["POST"])
@login_required
@admin_required
def admin_change_plan(user_id):
    user = User.query.get_or_404(user_id)
    new_plan = request.form.get("plan")
    if new_plan in ("free", "premium", "admin"):
        user.plan = new_plan
        db.session.commit()
        flash(f"{user.username} のプランを {new_plan} に変更しました。", "success")
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
    flash(f"{user.username} を削除しました。", "success")
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
    settings_path = os.path.join(os.path.dirname(__file__), "page_settings.json")
    import json

    # デフォルト設定
    default_settings = {pid: True for pid in PAGES}

    if request.method == "POST":
        settings = {}
        for pid in PAGES:
            settings[pid] = request.form.get(pid) == "on"
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)
        flash("ページ設定を更新しました。", "success")
        return redirect(url_for("admin_pages"))

    settings = default_settings
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

    return render_template("admin/pages.html", pages=PAGES, settings=settings)
