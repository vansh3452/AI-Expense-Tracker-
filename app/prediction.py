import numpy as np
from sklearn.linear_model import LinearRegression
from .models import Expense
from flask import current_app

def predict_next_month(user_id):
    try:
        expenses = Expense.query.filter_by(user_id=user_id).all()
        if not expenses:
            return None
        
        monthly_totals = {}
        for e in expenses:
            if e.date:
                month = e.date.strftime("%Y-%m")
                monthly_totals[month] = monthly_totals.get(month, 0) + e.amount
        
        if len(monthly_totals) < 2:
            current_app.logger.info(f"Only {len(monthly_totals)} months of data, need at least 2")
            return None
        
        months = sorted(monthly_totals.keys())
        X = [[i] for i in range(len(months))]
        y = [monthly_totals[m] for m in months]
        
        model = LinearRegression()
        model.fit(X, y)
        next_idx = [[len(months)]]
        pred = model.predict(next_idx)[0]
        return round(pred, 2)
    except Exception as e:
        current_app.logger.error(f"Prediction error: {e}")
        return None