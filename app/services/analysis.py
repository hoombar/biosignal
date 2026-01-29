"""Correlation and pattern analysis engine."""

import logging
from datetime import date, timedelta
import numpy as np
from scipy import stats
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.features import compute_features_range

logger = logging.getLogger(__name__)


def _to_numeric(value) -> float | None:
    """Convert value to numeric, handling booleans and None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def compute_correlations(
    session: AsyncSession,
    timezone: str = "Europe/London",
    min_days: int = 7
) -> list[dict]:
    """
    Compute correlations between all features and pm_slump.

    Args:
        session: Database session
        timezone: Timezone string
        min_days: Minimum number of days required for analysis

    Returns:
        List of correlation results, sorted by |r| descending.
    """
    # Get all available data
    end_date = date.today()
    start_date = end_date - timedelta(days=365)  # Look back 1 year max

    features_list = await compute_features_range(session, start_date, end_date, timezone)

    # Filter to days with pm_slump data
    fog_data = [f for f in features_list if f.get("pm_slump") is not None]

    if len(fog_data) < min_days:
        logger.warning(f"Insufficient data: {len(fog_data)} days (need {min_days})")
        return []

    # Extract pm_slump values
    pm_slump_values = [_to_numeric(f["pm_slump"]) for f in fog_data]

    # Separate fog and clear days for mean comparisons
    fog_days = [f for f in fog_data if f.get("pm_slump") is True]
    clear_days = [f for f in fog_data if f.get("pm_slump") is False]

    results = []

    # Get all numeric features (excluding date and pm_slump itself)
    sample_features = fog_data[0]
    feature_names = [k for k in sample_features.keys() if k not in ["date", "pm_slump"]]

    for feature_name in feature_names:
        # Extract feature values
        feature_values = [_to_numeric(f.get(feature_name)) for f in fog_data]

        # Filter out None values
        valid_pairs = [(s, f) for s, f in zip(pm_slump_values, feature_values) if s is not None and f is not None]

        if len(valid_pairs) < min_days:
            continue

        slump_vals, feat_vals = zip(*valid_pairs)

        # Check for variance (can't correlate if all values are the same)
        if np.std(feat_vals) == 0 or np.std(slump_vals) == 0:
            continue

        # Calculate Pearson correlation
        try:
            r, p_value = stats.pearsonr(slump_vals, feat_vals)
        except Exception as e:
            logger.warning(f"Correlation failed for {feature_name}: {e}")
            continue

        # Calculate means for fog vs clear days
        fog_values = [_to_numeric(f.get(feature_name)) for f in fog_days]
        fog_values = [v for v in fog_values if v is not None]
        fog_avg = np.mean(fog_values) if fog_values else None

        clear_values = [_to_numeric(f.get(feature_name)) for f in clear_days]
        clear_values = [v for v in clear_values if v is not None]
        clear_avg = np.mean(clear_values) if clear_values else None

        # Calculate difference percentage
        diff_pct = None
        if fog_avg is not None and clear_avg is not None and clear_avg != 0:
            diff_pct = ((fog_avg - clear_avg) / clear_avg) * 100

        # Classify strength
        abs_r = abs(r)
        if abs_r > 0.5:
            strength = "strong"
        elif abs_r > 0.3:
            strength = "moderate"
        else:
            strength = "weak"

        results.append({
            "metric": feature_name,
            "coefficient": float(r),
            "p_value": float(p_value),
            "n": len(valid_pairs),
            "strength": strength,
            "fog_day_avg": float(fog_avg) if fog_avg is not None else None,
            "clear_day_avg": float(clear_avg) if clear_avg is not None else None,
            "difference_pct": float(diff_pct) if diff_pct is not None else None,
        })

    # Sort by absolute correlation coefficient
    results.sort(key=lambda x: abs(x["coefficient"]), reverse=True)

    logger.info(f"Computed correlations for {len(results)} features")
    return results


async def compute_patterns(
    session: AsyncSession,
    timezone: str = "Europe/London"
) -> list[dict]:
    """
    Detect specific patterns using conditional probabilities.

    Returns:
        List of pattern results with probabilities and relative risk.
    """
    # Get all available data
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    features_list = await compute_features_range(session, start_date, end_date, timezone)

    # Filter to days with pm_slump data
    fog_data = [f for f in features_list if f.get("pm_slump") is not None]

    if len(fog_data) < 7:
        return []

    # Calculate baseline fog probability
    fog_count = sum(1 for f in fog_data if f.get("pm_slump") is True)
    baseline_prob = fog_count / len(fog_data)

    patterns = []

    # Pattern: Sleep < 7 hours
    sleep_low = [f for f in fog_data if f.get("sleep_hours") is not None and f["sleep_hours"] < 7]
    if len(sleep_low) >= 5:
        fog_in_pattern = sum(1 for f in sleep_low if f.get("pm_slump") is True)
        prob = fog_in_pattern / len(sleep_low)
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0

        patterns.append({
            "description": "Sleep less than 7 hours",
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(sleep_low),
        })

    # Pattern: Beer count > 2
    beer_high = [f for f in fog_data if f.get("beer_count") is not None and f["beer_count"] > 2]
    if len(beer_high) >= 5:
        fog_in_pattern = sum(1 for f in beer_high if f.get("pm_slump") is True)
        prob = fog_in_pattern / len(beer_high)
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0

        patterns.append({
            "description": "More than 2 alcoholic drinks previous evening",
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(beer_high),
        })

    # Pattern: Coffee > 3
    coffee_high = [f for f in fog_data if f.get("coffee_count") is not None and f["coffee_count"] > 3]
    if len(coffee_high) >= 5:
        fog_in_pattern = sum(1 for f in coffee_high if f.get("pm_slump") is True)
        prob = fog_in_pattern / len(coffee_high)
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0

        patterns.append({
            "description": "More than 3 coffees",
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(coffee_high),
        })

    # Pattern: Carb-heavy lunch
    carb_heavy = [f for f in fog_data if f.get("carb_heavy_lunch") is True]
    if len(carb_heavy) >= 5:
        fog_in_pattern = sum(1 for f in carb_heavy if f.get("pm_slump") is True)
        prob = fog_in_pattern / len(carb_heavy)
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0

        patterns.append({
            "description": "Carb-heavy lunch",
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(carb_heavy),
        })

    # Pattern: Body battery at 9am < 50
    bb_low = [f for f in fog_data if f.get("bb_9am") is not None and f["bb_9am"] < 50]
    if len(bb_low) >= 5:
        fog_in_pattern = sum(1 for f in bb_low if f.get("pm_slump") is True)
        prob = fog_in_pattern / len(bb_low)
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0

        patterns.append({
            "description": "Body Battery below 50 at 9am",
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(bb_low),
        })

    # Pattern: Had training (inverse - does training REDUCE fog?)
    had_training = [f for f in fog_data if f.get("had_training") is True]
    if len(had_training) >= 5:
        fog_in_pattern = sum(1 for f in had_training if f.get("pm_slump") is True)
        prob = fog_in_pattern / len(had_training)
        rel_risk = prob / baseline_prob if baseline_prob > 0 else 0

        patterns.append({
            "description": "Training day (previous day or same day)",
            "probability": float(prob),
            "baseline_probability": float(baseline_prob),
            "relative_risk": float(rel_risk),
            "sample_size": len(had_training),
        })

    # Sort by relative risk (descending)
    patterns.sort(key=lambda x: x["relative_risk"], reverse=True)

    logger.info(f"Identified {len(patterns)} patterns")
    return patterns


async def generate_insights(
    session: AsyncSession,
    timezone: str = "Europe/London"
) -> list[dict]:
    """
    Generate plain-English insights from correlations and patterns.

    Returns:
        List of insights with confidence ratings.
    """
    correlations = await compute_correlations(session, timezone)
    patterns = await compute_patterns(session, timezone)

    insights = []

    # Insights from patterns (high confidence if relative risk is significant)
    for pattern in patterns:
        if pattern["sample_size"] < 5:
            continue

        rel_risk = pattern["relative_risk"]
        prob = pattern["probability"]
        baseline = pattern["baseline_probability"]

        if rel_risk > 1.5 and prob > 0.5:
            # Increases fog risk
            text = (
                f"You're {rel_risk:.1f}x more likely to experience brain fog "
                f"when {pattern['description'].lower()}. "
                f"({prob*100:.0f}% vs {baseline*100:.0f}% baseline)"
            )
            confidence = "high" if pattern["sample_size"] >= 10 else "medium"

            insights.append({
                "text": text,
                "confidence": confidence,
                "supporting_metric": pattern["description"],
                "effect_size": rel_risk,
            })

        elif rel_risk < 0.7 and prob < baseline:
            # Reduces fog risk
            text = (
                f"Days with {pattern['description'].lower()} show "
                f"{(1-rel_risk)*100:.0f}% less brain fog. "
                f"({prob*100:.0f}% vs {baseline*100:.0f}% baseline)"
            )
            confidence = "high" if pattern["sample_size"] >= 10 else "medium"

            insights.append({
                "text": text,
                "confidence": confidence,
                "supporting_metric": pattern["description"],
                "effect_size": 1 - rel_risk,
            })

    # Insights from top correlations
    for corr in correlations[:3]:  # Top 3
        if abs(corr["coefficient"]) < 0.3:
            continue

        direction = "higher" if corr["coefficient"] > 0 else "lower"
        metric_name = corr["metric"].replace("_", " ")

        text = (
            f"{metric_name.capitalize()} is associated with "
            f"{'more' if corr['coefficient'] > 0 else 'fewer'} fog days "
            f"(r={corr['coefficient']:.2f})"
        )

        confidence = "medium" if corr["n"] >= 14 else "low"

        insights.append({
            "text": text,
            "confidence": confidence,
            "supporting_metric": corr["metric"],
            "effect_size": abs(corr["coefficient"]),
        })

    # Sort by confidence and effect size
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    insights.sort(
        key=lambda x: (confidence_order[x["confidence"]], x.get("effect_size", 0)),
        reverse=True
    )

    logger.info(f"Generated {len(insights)} insights")
    return insights
