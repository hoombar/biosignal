"""Environmental data providers and normalization."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import math
from zoneinfo import ZoneInfo

import httpx


@dataclass(frozen=True)
class EnvironmentalMetricValue:
    """Normalized daily environmental metric emitted by a provider."""

    source: str
    metric_key: str
    value: float
    unit: str
    category: str
    raw_metadata: dict | None = None


def location_key(latitude: float, longitude: float) -> str:
    """Stable key for a configured point location."""
    return f"{latitude:.4f},{longitude:.4f}"


class AstronomyProvider:
    """Deterministic daylight metrics for a point location."""

    source = "astronomy"

    def daily_metrics(
        self,
        target_date: date,
        tz: ZoneInfo,
        latitude: float,
        longitude: float,
    ) -> list[EnvironmentalMetricValue]:
        sunrise_utc = _sun_event_utc(target_date, latitude, longitude, is_sunrise=True)
        sunset_utc = _sun_event_utc(target_date, latitude, longitude, is_sunrise=False)

        if sunrise_utc is None or sunset_utc is None:
            return []

        sunrise_local = sunrise_utc.astimezone(tz)
        sunset_local = sunset_utc.astimezone(tz)
        daylight_minutes = (sunset_utc - sunrise_utc).total_seconds() / 60
        solar_noon_local = sunrise_local + (sunset_local - sunrise_local) / 2

        metadata = {
            "latitude": latitude,
            "longitude": longitude,
            "algorithm": "NOAA sunrise equation",
        }

        return [
            EnvironmentalMetricValue(
                source=self.source,
                metric_key="daylight_minutes",
                value=round(daylight_minutes, 2),
                unit="minutes",
                category="Light",
                raw_metadata=metadata,
            ),
            EnvironmentalMetricValue(
                source=self.source,
                metric_key="sunrise_minutes_after_midnight",
                value=round(_minutes_after_midnight(sunrise_local), 2),
                unit="minutes",
                category="Light",
                raw_metadata=metadata,
            ),
            EnvironmentalMetricValue(
                source=self.source,
                metric_key="sunset_minutes_after_midnight",
                value=round(_minutes_after_midnight(sunset_local), 2),
                unit="minutes",
                category="Light",
                raw_metadata=metadata,
            ),
            EnvironmentalMetricValue(
                source=self.source,
                metric_key="solar_noon_minutes_after_midnight",
                value=round(_minutes_after_midnight(solar_noon_local), 2),
                unit="minutes",
                category="Light",
                raw_metadata=metadata,
            ),
        ]


class OpenMeteoPollenProvider:
    """Hourly pollen metrics from Open-Meteo Air Quality API."""

    source = "open_meteo_air_quality"
    base_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    pollen_variables = (
        "alder_pollen",
        "birch_pollen",
        "grass_pollen",
        "mugwort_pollen",
        "olive_pollen",
        "ragweed_pollen",
    )

    def __init__(self, client_factory=None):
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=20.0))

    async def daily_metrics(
        self,
        target_date: date,
        tz: ZoneInfo,
        latitude: float,
        longitude: float,
    ) -> list[EnvironmentalMetricValue]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(self.pollen_variables),
            "timezone": tz.key,
            "start_date": target_date.isoformat(),
            "end_date": target_date.isoformat(),
        }

        async with self.client_factory() as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()

        hourly = payload.get("hourly") or {}
        hourly_units = payload.get("hourly_units") or {}
        metrics: list[EnvironmentalMetricValue] = []

        for variable in self.pollen_variables:
            values = [
                float(value)
                for value in hourly.get(variable, [])
                if value is not None
            ]
            if not values:
                continue

            hourly_unit = hourly_units.get(variable, "grains/m3")
            metadata = {
                "provider_url": self.base_url,
                "provider_params": params,
                "grid_latitude": payload.get("latitude"),
                "grid_longitude": payload.get("longitude"),
                "timezone": payload.get("timezone"),
                "hourly_unit": hourly_unit,
            }
            metrics.extend([
                EnvironmentalMetricValue(
                    source=self.source,
                    metric_key=f"{variable}_avg",
                    value=round(sum(values) / len(values), 4),
                    unit="grains/m3",
                    category="Pollen",
                    raw_metadata=metadata,
                ),
                EnvironmentalMetricValue(
                    source=self.source,
                    metric_key=f"{variable}_max",
                    value=round(max(values), 4),
                    unit="grains/m3",
                    category="Pollen",
                    raw_metadata=metadata,
                ),
            ])

        return metrics


class OpenMeteoWeatherProvider:
    """Hourly home weather metrics from Open-Meteo Forecast API."""

    source = "open_meteo_weather"
    base_url = "https://api.open-meteo.com/v1/forecast"
    weather_variables = (
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "dew_point_2m",
        "precipitation",
        "rain",
        "wind_speed_10m",
        "cloud_cover",
    )

    def __init__(self, client_factory=None):
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=20.0))

    async def daily_metrics(
        self,
        target_date: date,
        tz: ZoneInfo,
        latitude: float,
        longitude: float,
    ) -> list[EnvironmentalMetricValue]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(self.weather_variables),
            "timezone": tz.key,
            "start_date": target_date.isoformat(),
            "end_date": target_date.isoformat(),
        }

        async with self.client_factory() as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()

        hourly = payload.get("hourly") or {}
        hourly_units = payload.get("hourly_units") or {}
        metrics: list[EnvironmentalMetricValue] = []

        def values_for(variable: str) -> list[float]:
            return [float(value) for value in hourly.get(variable, []) if value is not None]

        metadata_base = {
            "provider_url": self.base_url,
            "provider_params": params,
            "grid_latitude": payload.get("latitude"),
            "grid_longitude": payload.get("longitude"),
            "timezone": payload.get("timezone"),
        }

        def add_metric(metric_key: str, value: float, unit: str, variable: str) -> None:
            metadata = {
                **metadata_base,
                "hourly_unit": hourly_units.get(variable, unit),
            }
            metrics.append(EnvironmentalMetricValue(
                source=self.source,
                metric_key=metric_key,
                value=round(value, 4),
                unit=unit,
                category="Weather",
                raw_metadata=metadata,
            ))

        temperature = values_for("temperature_2m")
        if temperature:
            add_metric("temperature_2m_avg", sum(temperature) / len(temperature), "degC", "temperature_2m")
            add_metric("temperature_2m_min", min(temperature), "degC", "temperature_2m")
            add_metric("temperature_2m_max", max(temperature), "degC", "temperature_2m")

        apparent_temperature = values_for("apparent_temperature")
        if apparent_temperature:
            add_metric(
                "apparent_temperature_avg",
                sum(apparent_temperature) / len(apparent_temperature),
                "degC",
                "apparent_temperature",
            )
            add_metric("apparent_temperature_max", max(apparent_temperature), "degC", "apparent_temperature")

        humidity = values_for("relative_humidity_2m")
        if humidity:
            add_metric("relative_humidity_2m_avg", sum(humidity) / len(humidity), "%", "relative_humidity_2m")
            add_metric("relative_humidity_2m_max", max(humidity), "%", "relative_humidity_2m")

        dew_point = values_for("dew_point_2m")
        if dew_point:
            add_metric("dew_point_2m_avg", sum(dew_point) / len(dew_point), "degC", "dew_point_2m")

        precipitation = values_for("precipitation")
        if precipitation:
            add_metric("precipitation_sum", sum(precipitation), "mm", "precipitation")
            add_metric("precipitation_hours", float(sum(1 for value in precipitation if value > 0)), "hours", "precipitation")

        rain = values_for("rain")
        if rain:
            add_metric("rain_sum", sum(rain), "mm", "rain")

        wind_speed = values_for("wind_speed_10m")
        if wind_speed:
            add_metric("wind_speed_10m_max", max(wind_speed), "km/h", "wind_speed_10m")

        cloud_cover = values_for("cloud_cover")
        if cloud_cover:
            add_metric("cloud_cover_avg", sum(cloud_cover) / len(cloud_cover), "%", "cloud_cover")

        return metrics


def _minutes_after_midnight(dt: datetime) -> float:
    midnight = datetime.combine(dt.date(), time.min, tzinfo=dt.tzinfo)
    return (dt - midnight).total_seconds() / 60


def _normalize_degrees(value: float) -> float:
    return value % 360


def _sun_event_utc(
    target_date: date,
    latitude: float,
    longitude: float,
    is_sunrise: bool,
) -> datetime | None:
    """Approximate sunrise/sunset UTC using the NOAA sunrise equation."""
    day_of_year = target_date.timetuple().tm_yday
    longitude_hour = longitude / 15
    event_hour = 6 if is_sunrise else 18
    t = day_of_year + ((event_hour - longitude_hour) / 24)

    mean_anomaly = (0.9856 * t) - 3.289
    true_longitude = _normalize_degrees(
        mean_anomaly
        + (1.916 * math.sin(math.radians(mean_anomaly)))
        + (0.020 * math.sin(math.radians(2 * mean_anomaly)))
        + 282.634
    )

    right_ascension = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_longitude))))
    right_ascension = _normalize_degrees(right_ascension)
    longitude_quadrant = math.floor(true_longitude / 90) * 90
    ascension_quadrant = math.floor(right_ascension / 90) * 90
    right_ascension = (right_ascension + longitude_quadrant - ascension_quadrant) / 15

    sin_declination = 0.39782 * math.sin(math.radians(true_longitude))
    cos_declination = math.cos(math.asin(sin_declination))
    cos_hour_angle = (
        math.cos(math.radians(90.833))
        - (sin_declination * math.sin(math.radians(latitude)))
    ) / (cos_declination * math.cos(math.radians(latitude)))

    if cos_hour_angle > 1 or cos_hour_angle < -1:
        return None

    hour_angle = math.degrees(math.acos(cos_hour_angle))
    if is_sunrise:
        hour_angle = 360 - hour_angle
    hour_angle /= 15

    local_mean_time = hour_angle + right_ascension - (0.06571 * t) - 6.622
    utc_hour = (local_mean_time - longitude_hour) % 24

    utc_midnight = datetime.combine(target_date, time.min, tzinfo=ZoneInfo("UTC"))
    return utc_midnight + timedelta(hours=utc_hour)
