# Phase 3 – Step 0: Pydantic data models shared by the agents and the Streamlit UI
# (moved out of planner.py so they can be imported without side effects).

import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator

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
# Phase 3 – Step 2: added Field constraints so the UI gets clear validation errors
class Traveler(BaseModel):
    """A traveler with a name, age, and list of interests."""
    name: str = Field(min_length=1)
    age: int = Field(ge=0, le=120)
    interests: List[Interest] = Field(min_length=1)


# Phase 3 – Step 0: the full trip request (travelers, destination, dates, budget)
# Phase 3 – Step 2: added constraints and a date-order check
class VacationInfo(BaseModel):
    """Vacation information including travelers, destination, dates, and budget.

    budget is in fictional currency units.
    """
    travelers: List[Traveler] = Field(min_length=1)
    destination: str
    date_of_arrival: datetime.date
    date_of_departure: datetime.date
    budget: int = Field(gt=0)

    # Phase 3 – Step 2: a check that involves two fields runs after the fields are parsed
    @model_validator(mode="after")
    def check_dates(self) -> "VacationInfo":
        if self.date_of_departure < self.date_of_arrival:
            raise ValueError("date_of_departure must be on or after date_of_arrival")
        return self


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
