from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from .models import Expense, User
from collections import defaultdict
from .prediction import predict_next_month
from . import db
from datetime import datetime, timedelta

main = Blueprint('main', __name__)

@main.route("/")
@login_required
def home():
    try:
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        expenses = Expense.query.filter_by(user_id=current_user.id).all()
        current_month_expenses = Expense.query.filter(
            Expense.user_id == current_user.id,
            Expense.date >= start_of_month
        ).all()
        total = sum(e.amount for e in expenses)
        monthly_total = sum(e.amount for e in current_month_expenses)
        category_data = defaultdict(float)
        for e in expenses:
            category_data[e.category] += e.amount
        categories = list(category_data.keys())
        amounts = list(category_data.values())
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_expenses = Expense.query.filter(
            Expense.user_id == current_user.id,
            Expense.date >= thirty_days_ago
        ).order_by(Expense.date.desc()).limit(10).all()
        prediction = predict_next_month(current_user.id)
        print(f"DEBUG: Prediction for user {current_user.id} = {prediction}")
        budget_alert = None
        if prediction and current_user.budgets:
            total_budget = sum(b.amount for b in current_user.budgets if b.category is None)
            if total_budget and prediction > total_budget:
                budget_alert = f"Your predicted spending (₹{prediction}) exceeds your monthly budget!"
        return render_template(
            "index.html",
            total=round(total, 2),
            monthly_total=round(monthly_total, 2),
            prediction=prediction,
            categories=categories,
            amounts=amounts,
            recent_expenses=recent_expenses,
            budget_alert=budget_alert
        )
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return render_template("index.html", total=0, monthly_total=0, categories=[], amounts=[])

@main.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        abort(403)
    search = request.args.get('search', '').strip()
    users = User.query.all()
    query = Expense.query
    if search:
        query = query.filter(
            db.or_(
                Expense.category.ilike(f'%{search}%'),
                Expense.description.ilike(f'%{search}%'),
                Expense.amount.cast(db.String).ilike(f'%{search}%'),
                Expense.user.has(User.username.ilike(f'%{search}%'))
            )
        )
    all_expenses = query.order_by(Expense.date.desc()).all()
    total_users = len(users)
    total_expenses = len(all_expenses)
    total_amount = sum(e.amount for e in all_expenses)
    avg_expense = total_amount / total_expenses if total_expenses > 0 else 0
    return render_template(
        "admin.html",
        users=users,
        all_expenses=all_expenses,
        total_users=total_users,
        total_expenses=total_expenses,
        total_amount=round(total_amount, 2),
        avg_expense=round(avg_expense, 2),
        search_term=search
    )

@main.route("/delete_expense_admin/<int:id>")
@login_required
def delete_expense_admin(id):
    if not current_user.is_admin:
        abort(403)
    expense = Expense.query.get_or_404(id)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted successfully.", "success")
    return redirect(url_for("main.admin"))

@main.route("/bulk_delete_expenses_admin", methods=["POST"])
@login_required
def bulk_delete_expenses_admin():
    if not current_user.is_admin:
        abort(403)
    expense_ids = request.form.getlist("expense_ids")
    if not expense_ids:
        flash("No expenses selected", "warning")
        return redirect(url_for("main.admin"))
    expenses = Expense.query.filter(Expense.id.in_(expense_ids)).all()
    count = len(expenses)
    for exp in expenses:
        db.session.delete(exp)
    db.session.commit()
    flash(f"Successfully deleted {count} expense(s)", "success")
    return redirect(url_for("main.admin"))

@main.route("/delete_user/<int:id>")
@login_required
def delete_user(id):
    if not current_user.is_admin:
        abort(403)
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully!", "success")
    return redirect(url_for("main.admin"))

@main.route("/delete_all_expenses", methods=["POST"])
@login_required
def delete_all_expenses():
    if not current_user.is_admin:
        abort(403)
    count = Expense.query.count()
    Expense.query.delete()
    db.session.commit()
    flash(f"Deleted ALL {count} expenses from the system.", "success")
    return redirect(url_for("main.admin"))