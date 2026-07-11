from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, current_app
from flask_login import login_required, current_user
from datetime import datetime
from datetime import datetime, date, timedelta
from utils import preprocess_text
from .models import Expense, User
from . import db
import csv
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import re
import cv2
import numpy as np
from PIL import Image
import pytesseract
import pandas as pd
import pickle
import os
from .ml_model import preprocess_text   # or define it directly
# Configure tesseract path (adjust for your system)

tesseract_path = os.getenv("TESSERACT_CMD")

if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

expenses = Blueprint('expenses', __name__)

# Load ML model
model_path = os.path.join(os.path.dirname(__file__), 'expense_model.pkl')
vectorizer_path = os.path.join(os.path.dirname(__file__), 'vectorizer.pkl')

try:
    with open(model_path, 'rb') as f:
        model = pickle.load(f)
    with open(vectorizer_path, 'rb') as f:
        vectorizer = pickle.load(f)
except Exception as e:
    print(f"Error loading ML model: {e}")
    model = None
    vectorizer = None
# Load label encoder
label_encoder_path = os.path.join(os.path.dirname(__file__), 'label_encoder.pkl')
try:
    with open(label_encoder_path, 'rb') as f:
        label_encoder = pickle.load(f)
except Exception as e:
    print(f"Error loading label encoder: {e}")
    label_encoder = None

def predict_category(text):
    """Predict category using trained ML model with fallback."""
    global model, vectorizer, label_encoder
    
    # If model not loaded, fallback to keyword matching
    if model is None or vectorizer is None or label_encoder is None:
        text_lower = text.lower()
        if any(word in text_lower for word in ['food', 'restaurant', 'cafe', 'burger', 'pizza', 'dinner', 'lunch']):
            return 'Food'
        elif any(word in text_lower for word in ['grocery', 'mart', 'supermarket', 'store', 'aldi', 'walmart']):
            return 'Groceries'
        elif any(word in text_lower for word in ['uber', 'taxi', 'fuel', 'petrol', 'bus', 'train', 'metro', 'ola', 'irctc']):
            return 'Transport'
        elif any(word in text_lower for word in ['shop', 'mall', 'amazon', 'flipkart', 'myntra', 'clothing']):
            return 'Shopping'
        elif any(word in text_lower for word in ['medical', 'pharmacy', 'hospital', 'clinic', 'doctor', 'dental']):
            return 'Health'
        elif any(word in text_lower for word in ['netflix', 'spotify', 'movie', 'cinema', 'entertainment']):
            return 'Entertainment'
        elif any(word in text_lower for word in ['bill', 'electricity', 'water', 'gas', 'mobile', 'internet']):
            return 'Bills'
        elif any(word in text_lower for word in ['salary', 'credit', 'refund', 'income']):
            return 'Income'
        else:
            return 'Other'
    
    try:
        processed = preprocess_text(text)   # you need to import this function or define it
        vec = vectorizer.transform([processed])
        pred_id = model.predict(vec)[0]
        category = label_encoder.inverse_transform([pred_id])[0]
        return category
    except Exception as e:
        current_app.logger.error(f"Prediction error: {e}")
        return 'Other'
    

@expenses.route("/add_expense", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        try:
            amount_str = request.form.get("amount", "0")
            amount = re.sub(r"[^\d.]", "", amount_str)
            amount = float(amount) if amount else 0
            
            if amount <= 0:
                flash("Amount must be greater than 0", "danger")
                return render_template("add_expense.html")
            
            category = request.form.get("category")
            description = request.form.get("description", "").strip()
            
            # Get date from form, default to today if not provided or invalid
            expense_date_str = request.form.get("date", "")
            if expense_date_str:
                try:
                    expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d")
                except ValueError:
                    expense_date = datetime.now()
            else:
                expense_date = datetime.now()
            
            if not category:
                flash("Please select a category", "danger")
                return render_template("add_expense.html")
            
            expense = Expense(
                amount=amount,
                category=category,
                description=description,
                date=expense_date,
                user_id=current_user.id
            )
            db.session.add(expense)
            db.session.commit()
            flash("Expense added successfully!", "success")
            return redirect(url_for("expenses.view_expenses"))
        except ValueError:
            flash("Invalid amount format", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding expense: {str(e)}", "danger")
    
    # Pre-fill from query parameters (from scan receipt)
    pre_amount = request.args.get('amount', '')
    pre_category = request.args.get('category', '')
    pre_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    return render_template("add_expense.html", 
                          pre_amount=pre_amount, 
                          pre_category=pre_category,
                          pre_date=pre_date)

@expenses.route("/expenses")
@login_required
def view_expenses():
    # Add pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    pagination = Expense.query.filter_by(user_id=current_user.id)\
        .order_by(Expense.date.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    expenses = pagination.items
    total_expenses = sum(e.amount for e in pagination.items if hasattr(e, 'amount'))
    
    return render_template("expense.html", 
                         expenses=expenses, 
                         pagination=pagination,
                         total_expenses=round(total_expenses, 2))

@expenses.route("/delete_expense/<int:id>")
@login_required
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    
    if expense.user_id != current_user.id and not current_user.is_admin:
        flash("You don't have permission to delete this expense", "danger")
        return redirect(url_for("expenses.view_expenses"))
    
    try:
        db.session.delete(expense)
        db.session.commit()
        flash("Expense deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting expense: {str(e)}", "danger")
    
    return redirect(url_for("expenses.view_expenses"))

@expenses.route("/edit_expense/<int:id>", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    expense = Expense.query.get_or_404(id)
    
    if expense.user_id != current_user.id and not current_user.is_admin:
        flash("You don't have permission to edit this expense", "danger")
        return redirect(url_for("expenses.view_expenses"))
    
    if request.method == "POST":
        try:
            amount_str = request.form.get("amount", "0")
            amount = re.sub(r"[^\d.]", "", amount_str)
            expense.amount = float(amount) if amount else 0
            expense.category = request.form.get("category")
            expense.description = request.form.get("description", "").strip()
            
            if expense.amount <= 0:
                flash("Amount must be greater than 0", "danger")
                return render_template("edit_expense.html", expense=expense)
            
            db.session.commit()
            flash("Expense updated successfully!", "success")
            return redirect(url_for("expenses.view_expenses"))
        except ValueError:
            flash("Invalid amount format", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating expense: {str(e)}", "danger")
    
    return render_template("edit_expense.html", expense=expense)

@expenses.route("/export_csv")
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    
    def generate():
        # Write header
        yield "Category,Amount,Description,Date\n"
        
        for e in expenses:
            yield f"{e.category},{e.amount},{e.description.replace(',', ' ')},{e.date.strftime('%Y-%m-%d %H:%M')}\n"
    
    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=expenses_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@expenses.route("/export_pdf")
@login_required
def export_pdf():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, f"Expense Report - {current_user.username}")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Table data
    data = [["Category", "Amount (₹)", "Description", "Date"]]
    total = 0
    
    y = height - 100
    for e in expenses:
        data.append([e.category, f"₹{e.amount:.2f}", e.description[:30], e.date.strftime('%Y-%m-%d')])
        total += e.amount
        y -= 20
        
        if y < 50:  # New page if needed
            p.showPage()
            y = height - 50
    
    # Add total row
    data.append(["TOTAL", f"₹{total:.2f}", "", ""])
    
    # Create table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    table.wrapOn(p, width, height)
    table.drawOn(p, 50, y - len(data) * 20)
    
    p.save()
    buffer.seek(0)
    
    return Response(
        buffer,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename=expenses_{datetime.now().strftime('%Y%m%d')}.pdf"}
    )

def preprocess_receipt(image_file):
    """Preprocess receipt image for better OCR"""
    try:
        file_bytes = np.frombuffer(image_file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Could not read image")
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Resize for better OCR
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        
        # Remove noise
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Apply threshold
        thresh = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )
        
        return thresh
    except Exception as e:
        current_app.logger.error(f"Image preprocessing error: {e}")
        raise

def parse_receipt_data(text):
    """Parse receipt text to extract information"""
    data = {
        "store": None,
        "date": None,
        "items": [],
        "tax": None,
        "total": None
    }
    
    lines = text.split("\n")
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        
        # Detect store name (first non-empty line that's not too long)
        if not data["store"] and len(line_clean) > 3 and len(line_clean) < 50:
            data["store"] = line_clean
        
        # Detect date (multiple formats)
        date_patterns = [
            r'\d{2}/\d{2}/\d{4}',
            r'\d{2}-\d{2}-\d{4}',
            r'\d{4}-\d{2}-\d{2}'
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, line_clean)
            if date_match:
                data["date"] = date_match.group()
                break
        
        # Detect total amount
        total_keywords = ['total', 'amount due', 'grand total', 'bill total']
        if any(keyword in line_clean.lower() for keyword in total_keywords):
            amounts = re.findall(r'(\d+\.?\d{0,2})', line_clean)
            if amounts:
                data["total"] = amounts[-1]
        
        # Detect tax
        if 'tax' in line_clean.lower() or 'gst' in line_clean.lower():
            amounts = re.findall(r'(\d+\.?\d{0,2})', line_clean)
            if amounts:
                data["tax"] = amounts[0]
    
    return data

@expenses.route("/scan_receipt", methods=["GET", "POST"])
@login_required
def scan_receipt():
    extracted_text = ""
    detected_amount = None
    detected_category = None
    detected_date = None
    receipt_data = {}
    
    if request.method == "POST":
        file = request.files.get("receipt")
        if not file:
            flash("Please select a receipt image", "warning")
            return render_template("scan_receipt.html")
        
        if file.filename == '':
            flash("No file selected", "warning")
            return render_template("scan_receipt.html")
        
        try:
            # Process image
            processed_image = preprocess_receipt(file)
            
            # Extract text using Tesseract
            extracted_text = pytesseract.image_to_string(
                processed_image,
                config="--psm 6 --oem 3"
            )
            
            if not extracted_text.strip():
                flash("Could not extract text from image. Please try a clearer image.", "warning")
                return render_template("scan_receipt.html")
            
            # Parse receipt data
            receipt_data = parse_receipt_data(extracted_text)
            
            # Detect category
            search_text = extracted_text[:500].lower()
            detected_category = predict_category(search_text)
            
            # Extract date
            if receipt_data.get("date"):
                detected_date = receipt_data["date"]
                # Try to convert to YYYY-MM-DD format for the form
                try:
                    # Handle common formats
                    date_str = detected_date
                    if '/' in date_str:
                        parts = date_str.split('/')
                        if len(parts) == 3:
                            detected_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                    elif '-' in date_str:
                        parts = date_str.split('-')
                        if len(parts) == 3 and len(parts[0]) == 4:
                            pass  # already YYYY-MM-DD
                        elif len(parts) == 3 and len(parts[0]) == 2:
                            detected_date = f"20{parts[2]}-{parts[1]}-{parts[0]}"
                except:
                    pass
            
            if receipt_data.get("total"):
                detected_amount = receipt_data["total"]
                flash(f"Receipt scanned successfully! Detected amount: ₹{detected_amount}", "success")
            else:
                flash("Receipt scanned but could not detect total amount. Please enter manually.", "info")
        
        except Exception as e:
            current_app.logger.error(f"Receipt scanning error: {e}")
            flash(f"Error scanning receipt: {str(e)}", "danger")
    
    return render_template(
        "scan_receipt.html",
        text=extracted_text,
        amount=detected_amount,
        category=detected_category,
        date=detected_date,
        receipt=receipt_data
    )

@expenses.route("/import_bank", methods=["GET", "POST"])
@login_required
def import_bank():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == '':
            flash("Please select a CSV file", "warning")
            return render_template("import_bank.html")
        if not file.filename.endswith('.csv'):
            flash("Please upload a CSV file", "warning")
            return render_template("import_bank.html")
        
        try:
            content = file.read().decode('utf-8-sig')
            from io import StringIO
            df = pd.read_csv(StringIO(content))
            
            # Required columns: Description, Amount, and optionally Date
            required = ['Description', 'Amount']
            df.columns = [col.strip() for col in df.columns]
            if not all(col in df.columns for col in required):
                flash(f"CSV must contain columns: {', '.join(required)}", "danger")
                return render_template("import_bank.html")
            
            imported_count = 0
            skipped_count = 0
            
            for idx, row in df.iterrows():
                try:
                    # Parse amount
                    amount_str = str(row["Amount"]).strip()
                    amount_str = re.sub(r'[^\d.-]', '', amount_str)
                    if not amount_str or amount_str == '-':
                        skipped_count += 1
                        continue
                    amount = abs(float(amount_str))
                    if amount <= 0:
                        skipped_count += 1
                        continue
                    
                    # Parse description
                    description = str(row["Description"]).strip()
                    if not description:
                        skipped_count += 1
                        continue
                    
                    # Parse date: look for 'Date' column, fallback to today
                    expense_date = datetime.now()
                    if 'Date' in df.columns:
                        date_str = str(row["Date"]).strip()
                        if date_str:
                            try:
                                # Try common date formats
                                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                                    try:
                                        expense_date = datetime.strptime(date_str, fmt)
                                        break
                                    except ValueError:
                                        continue
                            except:
                                pass
                    
                    # Predict category
                    category = predict_category(description)
                    if not category:
                        category = "Other"
                    
                    expense = Expense(
                        amount=amount,
                        category=category,
                        description=description[:200],
                        date=expense_date,
                        user_id=current_user.id
                    )
                    db.session.add(expense)
                    imported_count += 1
                    
                except Exception as e:
                    skipped_count += 1
                    current_app.logger.error(f"Import row {idx} error: {e}")
                    continue
            
            db.session.commit()
            
            if imported_count > 0:
                flash(f"Successfully imported {imported_count} transactions.", "success")
            else:
                flash(f"No transactions imported. {skipped_count} rows skipped.", "warning")
            return redirect(url_for("expenses.view_expenses"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error reading file: {str(e)}", "danger")
            current_app.logger.error(f"Import error: {e}")
    
    return render_template("import_bank.html")

def sync_bank_transactions():
    """Background job to sync bank transactions"""
    from datetime import datetime
    
    try:
        bank_file = os.path.join(os.path.dirname(__file__), 'bank_statement.csv')
        
        if not os.path.exists(bank_file):
            return
        
        df = pd.read_csv(bank_file)
        
        # Get all users (or specific user)
        users = User.query.all()
        
        for _, row in df.iterrows():
            amount = abs(float(row["Amount"]))
            description = str(row["Description"])
            date = pd.to_datetime(row.get("Date", datetime.now()))
            
            category = predict_category(description)
            
            # Add expense for each user (or modify as needed)
            for user in users:
                # Check if expense already exists (simple duplicate check)
                existing = Expense.query.filter_by(
                    user_id=user.id,
                    amount=amount,
                    description=description
                ).first()
                
                if not existing:
                    expense = Expense(
                        amount=amount,
                        category=category,
                        description=description[:200],
                        date=date,
                        user_id=user.id
                    )
                    db.session.add(expense)
        
        db.session.commit()
        print(f"Bank transactions synced at {datetime.now()}")
    
    except Exception as e:
        print(f"Bank sync error: {e}")
        db.session.rollback()
@expenses.route("/bulk_delete_expenses", methods=["POST"])
@login_required
def bulk_delete_expenses():
    delete_all = request.form.get("delete_all") == "1"
    if delete_all:
        # Delete ALL expenses for the current user
        expenses = Expense.query.filter_by(user_id=current_user.id).all()
        count = len(expenses)
        for expense in expenses:
            db.session.delete(expense)
        db.session.commit()
        flash(f"Successfully deleted ALL {count} expenses", "success")
        return redirect(url_for("expenses.view_expenses"))
    
    # Normal per‑page selection
    expense_ids = request.form.getlist("expense_ids")
    if not expense_ids:
        flash("No expenses selected", "warning")
        return redirect(url_for("expenses.view_expenses"))
    
    expenses = Expense.query.filter(Expense.id.in_(expense_ids), Expense.user_id == current_user.id).all()
    count = len(expenses)
    for expense in expenses:
        db.session.delete(expense)
    db.session.commit()
    flash(f"Successfully deleted {count} expense(s)", "success")
    return redirect(url_for("expenses.view_expenses"))