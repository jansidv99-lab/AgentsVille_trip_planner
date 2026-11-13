# Phase 3 – Step 0: Pydantic data models shared by the agents and the Streamlit UI
# (moved out of planner.py so they can be imported without side effects).

import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel

from project_lib import Interest


# Phase 3 – Step 0: models the user can pick from in the UI
class OpenAIModel(str, Enum):
    GPT_41 = "gpt-4.1"  # Strongest; general-purpose reasoning and demanding tasks.
    GPT_41_MINI = "gpt-4.1-mini"  # Default. Fast and affordable.
    GPT_41_NANO = "gpt-4.1-nano"  # Fastest and cheapest; lightweight tasks.


# ---------------------------------------------------------------------------
# Input: what the traveler tells us
# ---------------------------------------------------------------------------

# Phase 3 – Step 0: one traveler and their interests
class Traveler(BaseModel):
    """A traveler with a name, age, and list of interests."""
    name: str
    age: int
    interests: List[Interest]


# Phase 3 – Step 0: the full trip request (travelers, destination, dates, budget)
class VacationInfo(BaseModel):
    """Vacation information including travelers, destination, dates, and budget.

    budget is in fictional currency units.
    """
    travelers: List[Traveler]
    destination: str
    date_of_arrival: datetime.date
    date_of_departure: datetime.date
    budget: int


# ---------------------------------------------------------------------------
# Output: the itinerary the LLM must return
# ---------------------------------------------------------------------------

# Phase 3 – Step 0: weather for one day
class Weather(BaseModel):
    temperature: float
    temperature_unit: str
    condition: str


# Phase 3 – Step 0: one bookable activity (mirrors the mocked activities API)
class Activity(BaseModel):
    activity_id: str
    name: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    location: str
    description: str
    price: int
    related_interests: List[Interest]


# Phase 3 – Step 0: an activity plus why the agent picked it
class ActivityRecommendation(BaseModel):
    activity: Activity
    reasons_for_recommendation: List[str]


# Phase 3 – Step 0: one day of the itinerary
class ItineraryDay(BaseModel):
    date: datetime.date
    weather: Weather
    activity_recommendations: List[ActivityRecommendation]


# Phase 3 – Step 0: the complete plan returned by the itinerary agent
class TravelPlan(BaseModel):
    city: str
    start_date: datetime.date
    end_date: datetime.date
    total_cost: int
    itinerary_days: List[ItineraryDay]
