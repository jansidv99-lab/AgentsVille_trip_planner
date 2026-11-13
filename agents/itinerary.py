# Phase 3 – Step 0: Part A – the Expert Planner. Builds the chain-of-thought prompt from the
# trip's dates and asks the LLM for a TravelPlan JSON object.

import datetime
import json
from typing import Optional

from models import OpenAIModel, TravelPlan, VacationInfo
from project_lib import (
    ChatAgent,
    call_activities_api_mocked,
    call_weather_api_mocked,
    print_in_box,
)


# Phase 3 – Step 0: every date from arrival to departure, inclusive, as YYYY-MM-DD strings
def trip_dates(vacation_info: VacationInfo) -> list[str]:
    days = (vacation_info.date_of_departure - vacation_info.date_of_arrival).days
    return [
        (vacation_info.date_of_arrival + datetime.timedelta(days=i)).isoformat()
        for i in range(days + 1)
    ]


# Phase 3 – Step 0: fetch mocked weather and activities for the trip's dates
def fetch_context(vacation_info: VacationInfo) -> tuple[list[dict], list[dict]]:
    city = vacation_info.destination
    dates = trip_dates(vacation_info)
    weather = [call_weather_api_mocked(date=d, city=city) for d in dates]
    activities = [a for d in dates for a in call_activities_api_mocked(date=d, city=city)]
    return weather, activities


# Phase 3 – Step 0: the system prompt, with weather/activities for *this* trip as context
def build_system_prompt(vacation_info: VacationInfo) -> str:
    weather, activities = fetch_context(vacation_info)
    return f"""
Role: You are an expert travel planner and itinerary specialist with extensive experience creating personalized travel experiences.

Task:
  Create a comprehensive day-by-day travel itinerary based on the provided vacation information, weather conditions, and available activities. Follow these requirements:

  1. **Weather Considerations**: Avoid scheduling outdoor-only activities during rain or thunderstorms
  2. **Interest Matching**: Select activities that match the travelers' interests and preferences
  3. **Budget Compliance**: Ensure the total cost does not exceed the specified budget
  4. **Activity Requirements**: Include at least one activity per day
  5. **Realistic Planning**: Consider travel time, activity duration, and logical flow
  6. **CRITICAL: Use Exact Activity Data**: You MUST use the exact activity IDs, names, times, prices, and details from the provided activity list.
                 Activity IDs follow the format "event-YYYY-MM-DD-N" (e.g., "event-2025-06-10-0"). NEVER use activity names as IDs.
                 NEVER create, modify, or abbreviate activity IDs. Copy all activity information exactly as provided.

  Use a step-by-step approach to analyze the requirements and create an optimal itinerary.

Output Format:
    Respond using two sections (ANALYSIS AND FINAL OUTPUT) in the following format:

    ANALYSIS:
    1. Weather Analysis: Review weather conditions for each day
    2. Interest Mapping: Identify activities matching each traveler's interests
    3. Budget Planning: Calculate costs and ensure budget compliance
    4. Day-by-Day Planning: Create logical flow for each day
    5. Validation: Verify all requirements are met


FINAL OUTPUT: Strictly respond with a JSON object that adheres to this TravelPlan JSON schema
(use exactly these field names):

    ```json
    {json.dumps(TravelPlan.model_json_schema(), indent=2)}
    ```

Context:
Weather data:
{json.dumps(weather, indent=2)}

Activities data:
{json.dumps(activities, indent=2)}

Vacation information will be provided in the user message.
"""  # noqa: E501


# Phase 3 – Step 0: pull the JSON block out of the "ANALYSIS ... FINAL OUTPUT" response
def extract_json(response: str) -> str:
    text = response.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    return text


# Phase 3 – Step 0: the itinerary agent; the system prompt is rebuilt per trip
class ItineraryAgent(ChatAgent):
    """An agent that plans itineraries based on vacation information, weather, and activities."""

    # Phase 3 – Step 0: generate and validate a TravelPlan for one trip request
    def get_itinerary(
        self, vacation_info: VacationInfo, model: Optional[OpenAIModel] = None
    ) -> TravelPlan:
        """Generate a travel itinerary for vacation_info.

        Raises pydantic.ValidationError if the LLM's JSON doesn't match TravelPlan.
        """
        self.system_prompt = build_system_prompt(vacation_info)
        self.reset()  # start a fresh conversation with the new system prompt

        response = (
            self.chat(
                user_message=vacation_info.model_dump_json(indent=2),
                add_to_messages=False,
                model=model or self.model,
            )
            or ""
        ).strip()
        print_in_box(response, "Raw Response")

        return TravelPlan.model_validate_json(extract_json(response))
