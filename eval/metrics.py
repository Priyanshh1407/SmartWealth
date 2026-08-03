from typing import List, Dict, Any

def calculate_metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, float]:
    """
    Calculates precision, recall, and F1 score for a list of predictions against ground truth.
    This works for both categorization (multi-class) and deductibility (binary).
    """
    if not y_true or not y_pred:
        return {"precision": 0.0, "recall": 0.0, "f1_score": 0.0}
        
    classes = set(y_true + y_pred)
    total_precision = 0.0
    total_recall = 0.0
    
    # Calculate macro-averaged precision and recall
    for cls in classes:
        true_positives = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cls and yp == cls)
        false_positives = sum(1 for yt, yp in zip(y_true, y_pred) if yt != cls and yp == cls)
        false_negatives = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cls and yp != cls)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        
        total_precision += precision
        total_recall += recall
        
    macro_precision = total_precision / len(classes) if classes else 0.0
    macro_recall = total_recall / len(classes) if classes else 0.0
    
    f1_score = (2 * macro_precision * macro_recall) / (macro_precision + macro_recall) if (macro_precision + macro_recall) > 0 else 0.0
    
    return {
        "precision": round(macro_precision, 4),
        "recall": round(macro_recall, 4),
        "f1_score": round(f1_score, 4),
        "accuracy": round(sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp) / len(y_true), 4)
    }

def format_metrics_report(cat_metrics: Dict[str, float], ded_metrics: Dict[str, float], total_samples: int) -> str:
    """Formats the calculated metrics into a markdown string."""
    return f"""# Evaluation Report

**Total Samples Evaluated:** {total_samples}

## Categorization Metrics
- **Accuracy:** {cat_metrics['accuracy']:.2%}
- **Precision (Macro):** {cat_metrics['precision']:.2%}
- **Recall (Macro):** {cat_metrics['recall']:.2%}
- **F1 Score:** {cat_metrics['f1_score']:.2%}

## Deductibility Metrics
- **Accuracy:** {ded_metrics['accuracy']:.2%}
- **Precision (Macro):** {ded_metrics['precision']:.2%}
- **Recall (Macro):** {ded_metrics['recall']:.2%}
- **F1 Score:** {ded_metrics['f1_score']:.2%}
"""
