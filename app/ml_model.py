"""
Expense Category Classification - Trained on 1000+ real bank transactions
Uses TF-IDF + Logistic Regression with high accuracy.
"""

import pandas as pd
import numpy as np
import pickle
import re
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings('ignore')

# Configuration
DATA_FILE = "bank_transactions_1000.csv"   # training data
MODEL_FILE = "expense_model.pkl"
VECTORIZER_FILE = "vectorizer.pkl"
LABEL_ENCODER_FILE = "label_encoder.pkl"
RANDOM_STATE = 42

def preprocess_text(text):
    """Clean and normalize text."""
    if not isinstance(text, str):
        text = str(text)
    text = text.lower()
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    text = ' '.join(text.split())
    return text

def load_and_prepare_data(filepath):
    """Load bank CSV, combine Description + Type, drop missing categories."""
    df = pd.read_csv(filepath)
    
    # Use Description and Type together as input
    df['combined'] = df['Description'].fillna('') + ' ' + df['Type'].fillna('')
    df['combined'] = df['combined'].apply(preprocess_text)
    
    # Drop rows without a valid category
    df = df.dropna(subset=['Category'])
    df = df[df['Category'].str.strip() != '']
    
    # Map all categories to consistent names (they already are, but ensure)
    # Keep only the most frequent categories (optional, but helps with rare ones)
    category_counts = df['Category'].value_counts()
    print(f"Total samples: {len(df)}")
    print(f"Categories found: {list(category_counts.index)}")
    print("Category distribution:\n", category_counts)
    
    # For very rare categories (<5 samples), map to 'Other'
    rare_threshold = 5
    rare_cats = category_counts[category_counts < rare_threshold].index.tolist()
    if rare_cats:
        print(f"\nMapping rare categories to 'Other': {rare_cats}")
        df['Category'] = df['Category'].apply(lambda x: 'Other' if x in rare_cats else x)
    
    # Encode labels
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(df['Category'])
    
    X = df['combined']
    
    print(f"\nFinal classes: {list(label_encoder.classes_)}")
    return X, y, label_encoder

def train_model(X, y, label_encoder):
    """Train TF-IDF + Logistic Regression."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )
    
    vectorizer = TfidfVectorizer(
        lowercase=True,
        analyzer='word',
        ngram_range=(1, 2),
        stop_words='english',
        max_features=10000
    )
    
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    
    # Use Logistic Regression with balanced class weights
    model = LogisticRegression(
        max_iter=1000,
        random_state=RANDOM_STATE,
        class_weight='balanced',
        C=1.0
    )
    model.fit(X_train_vec, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test_vec)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"\nTest Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=label_encoder.classes_))
    
    # Cross-validation
    cv_scores = cross_val_score(model, vectorizer.transform(X), y, cv=5)
    print(f"\n5‑fold CV scores: {cv_scores}")
    print(f"Mean CV accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f})")
    
    return model, vectorizer

def save_model(model, vectorizer, label_encoder, model_path, vec_path, enc_path):
    for path in [model_path, vec_path, enc_path]:
        if os.path.exists(path):
            os.rename(path, f"{path}.backup")
            print(f"Backed up {path}")
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)
    with open(vec_path, 'wb') as f:
        pickle.dump(vectorizer, f)
    with open(enc_path, 'wb') as f:
        pickle.dump(label_encoder, f)
    print(f"\nModel saved to {model_path}")
    print(f"Vectorizer saved to {vec_path}")
    print(f"Label encoder saved to {enc_path}")

def test_predictions(model, vectorizer, label_encoder):
    """Test on a few example descriptions."""
    test_texts = [
        "uber ride", "netflix subscription", "amazon shopping", "electricity bill",
        "local grocery store", "movie tickets", "salary credit", "atm withdrawal",
        "dominios pizza", "irctc train ticket", "flipkart order", "refund received"
    ]
    print("\n" + "="*60)
    print("Sample predictions (using trained model):")
    for text in test_texts:
        processed = preprocess_text(text)
        vec = vectorizer.transform([processed])
        pred_id = model.predict(vec)[0]
        pred_cat = label_encoder.inverse_transform([pred_id])[0]
        prob = max(model.predict_proba(vec)[0])
        print(f"{text:25} -> {pred_cat:15} (confidence: {prob:.2f})")

if __name__ == "__main__":
    print("Training Expense Model on 1000+ Bank Transactions")
    print("="*60)
    try:
        X, y, label_encoder = load_and_prepare_data(DATA_FILE)
        model, vectorizer = train_model(X, y, label_encoder)
        save_model(model, vectorizer, label_encoder, MODEL_FILE, VECTORIZER_FILE, LABEL_ENCODER_FILE)
        test_predictions(model, vectorizer, label_encoder)
        print("\n✅ Training completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        raise