# Phase 3 – Step 0: command-line demo of Part A. The models, client, and agent now live in
# models.py, llm.py, and agents/itinerary.py; run this file directly to try them:
#     python planner.py

from pprint import pprint

from agents.itinerary import ItineraryAgent
from llm import get_client, get_default_model
from models import VacationInfo

# Sample trip. Mock weather/activity data exists only for 2025-06-10 … 2025-06-15.
# Possible interests: art, cooking, comedy, dancing, fitness, gardening, hiking, movies,
# music, photography, reading, sports, technology, theatre, tennis, writing
VACATION_INFO_DICT = {
    "travelers": [
        {"name": "Yuri", "age": 30, "interests": ["tennis", "cooking", "comedy", "technology"]},
        {"name": "Hiro", "age": 25, "interests": ["reading", "music", "theatre", "art"]},
    ],
    "destination": "AgentsVille",
    "date_of_arrival": "2025-06-10",
    "date_of_departure": "2025-06-12",
    "budget": 130,  # fictional currency units
}


# Phase 3 – Step 0: validate the sample trip, generate an itinerary, and print it
def main() -> None:
    vacation_info = VacationInfo.model_validate(VACATION_INFO_DICT)
    print("✅ VacationInfo data structure is valid!")

    model = get_default_model()
    agent = ItineraryAgent(client=get_client(), model=model)
    travel_plan = agent.get_itinerary(vacation_info=vacation_info, model=model)

    print("✅ Initial itinerary generated successfully.")
    pprint(travel_plan.model_dump())


if __name__ == "__main__":
    main()
