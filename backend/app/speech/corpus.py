"""Harvard sentences and command templates for speech test generation."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Harvard Sentences — Lists 1-10 (10 sentences each, 100 total)
# Classic phonetically balanced sentence set used in speech/audio research.
# ---------------------------------------------------------------------------

HARVARD_SENTENCES: list[str] = [
    # List 1
    "The birch canoe slid on the smooth planks.",
    "Glue the sheet to the dark blue background.",
    "It's easy to tell the depth of a well.",
    "These days a chicken leg is a rare dish.",
    "Rice is often served in round bowls.",
    "The juice of lemons makes fine punch.",
    "The box was thrown beside the parked truck.",
    "The hogs were fed chopped corn and garbage.",
    "Four hours of steady work faced us.",
    "A large size in stockings is hard to sell.",
    # List 2
    "The boy was there when the sun rose.",
    "A rod is used to catch pink salmon.",
    "The source of the huge river is the clear spring.",
    "Kick the ball straight and follow through.",
    "Help the woman get back to her feet.",
    "A pot of tea helps to pass the evening.",
    "Smoky fires lack flame and heat.",
    "The soft cushion broke the man's fall.",
    "The salt breeze came across from the sea.",
    "The girl at the booth sold fifty bonds.",
    # List 3
    "The small pup gnawed a hole in the sock.",
    "The fish twisted and turned on the bent hook.",
    "Press the pants and sew a button on the vest.",
    "The swan dive was far short of perfect.",
    "The beauty of the view stunned the young boy.",
    "Two blue fish swam in the tank.",
    "Her purse was full of useless trash.",
    "The colt reared and threw the tall rider.",
    "It snowed, rained, and hailed the same morning.",
    "Read verse out loud for pleasure.",
    # List 4
    "Hoist the load to your left shoulder.",
    "Take the winding path to reach the lake.",
    "Note closely the size of the gas tank.",
    "Wipe the grease off his dirty face.",
    "Mend the coat before you go out.",
    "The wrist was badly strained and hung limp.",
    "The stray cat gave birth to kittens.",
    "The young girl gave no clear response.",
    "The meal was cooked before the bell rang.",
    "What joy there is in living.",
    # List 5
    "A king ruled the state in the early days.",
    "The ship was torn apart on the sharp reef.",
    "Sickness kept him home the third week.",
    "The wide road shimmered in the hot sun.",
    "The lazy cow lay in the cool grass.",
    "Lift the square stone over the fence.",
    "The rope will bind the seven books at once.",
    "Hop over the fence and plunge in.",
    "The friendly gang left the drug store.",
    "Mesh wire keeps chicks inside.",
    # List 6
    "The frosty air passed through the coat.",
    "The crooked maze puzzled the young girl.",
    "Adding fast leads to wrong sums.",
    "The show was a flop from the very start.",
    "A saw is a tool used for making boards.",
    "The wagon moved on well oiled wheels.",
    "March the soldiers past the next hill.",
    "A cup of sugar makes sweet fudge.",
    "Place a rosebud in her hair.",
    "Both lost their lives in the raging storm.",
    # List 7
    "We talked of the side show in the circus.",
    "Use a pencil to write the first draft.",
    "He ran half way to the hardware store.",
    "The clock struck to mark the third period.",
    "A small creek cut across the field.",
    "Cars and busses stalled in snow drifts.",
    "The set of china hit the floor with a crash.",
    "This is a grand season for hikes on the road.",
    "The dune rose from the edge of the water.",
    "Those words were the cue for the actor to leave.",
    # List 8
    "A yacht slid around the point into the bay.",
    "The two met while playing on the sand.",
    "The ink stain dried on the finished page.",
    "The walled town was seized without a fight.",
    "The lease said the rent was due every month.",
    "A tame squirrel makes a nice pet.",
    "The horn of the car woke the sleeping cop.",
    "The heart beat strongly and with firm strokes.",
    "The pearl was worn in a thin silver ring.",
    "The fruit peel was cut in thick slices.",
    # List 9
    "The navy attacked the big task force.",
    "See the cat glaring at the scared mouse.",
    "There are more than two factors here.",
    "The hat brim was wide and too droopy.",
    "The lawyer tried to lose his case.",
    "The grass curled around the fence post.",
    "Cut the pie into large parts.",
    "Men strive but seldom get rich.",
    "Always close the barn door tight.",
    "He lay prone and hardly moved a limb.",
    # List 10
    "The slush melted on the hard floor.",
    "A dog pulled the sleigh across the snow.",
    "The blinds were drawn to keep out the light.",
    "The team text was a good source of help.",
    "The sun shone brightly on the tin roof.",
    "Slide the tray across the glass top.",
    "The cloud moved in a stately way and was gone.",
    "Light maple sugar is made from sap.",
    "Bring your best compass to the third class.",
    "Rain dripped from the eaves all day long.",
]

# ---------------------------------------------------------------------------
# Command Templates
# ---------------------------------------------------------------------------

COMMAND_TEMPLATES: dict[str, list[str]] = {
    "navigation": [
        "Navigate to {destination}",
        "How far is {destination}",
        "Find the nearest {poi_type}",
        "Take me to {destination}",
        "What's the fastest route to {destination}",
    ],
    "media": [
        "Play {song} by {artist}",
        "Turn up the volume",
        "Skip this song",
        "Play my {playlist} playlist",
        "What song is this",
    ],
    "climate": [
        "Set temperature to {temp} degrees",
        "Turn on the AC",
        "Turn off the heater",
        "Make it warmer",
        "Make it cooler",
    ],
    "phone": [
        "Call {contact}",
        "Read my messages",
        "Send a text to {contact}",
        "Answer the call",
        "Dial {phone_number}",
    ],
    "general": [
        "What's the weather like",
        "Set a timer for {duration}",
        "What time is it",
        "Remind me to {task} at {time}",
        "Tell me a joke",
    ],
}

# ---------------------------------------------------------------------------
# Template fill values
# ---------------------------------------------------------------------------

TEMPLATE_VALUES: dict[str, list[str]] = {
    "destination": [
        "home",
        "work",
        "the airport",
        "downtown",
        "123 Main Street",
        "the nearest hospital",
        "Mom's house",
        "the grocery store",
        "Central Park",
        "the mall",
    ],
    "poi_type": [
        "gas station",
        "restaurant",
        "coffee shop",
        "parking lot",
        "pharmacy",
        "hospital",
        "ATM",
        "hotel",
        "EV charging station",
        "rest stop",
    ],
    "song": [
        "Bohemian Rhapsody",
        "Hotel California",
        "Shape of You",
        "Blinding Lights",
        "Yesterday",
        "Billie Jean",
        "Rolling in the Deep",
        "Stairway to Heaven",
        "Lose Yourself",
        "Sweet Child O' Mine",
    ],
    "artist": [
        "Queen",
        "The Eagles",
        "Ed Sheeran",
        "The Weeknd",
        "The Beatles",
        "Michael Jackson",
        "Adele",
        "Led Zeppelin",
        "Eminem",
        "Guns N' Roses",
    ],
    "playlist": [
        "road trip",
        "chill vibes",
        "workout",
        "morning commute",
        "favorites",
        "jazz",
        "classical",
        "top hits",
        "throwback",
        "party",
    ],
    "temp": [
        "68",
        "70",
        "72",
        "65",
        "75",
        "60",
        "78",
        "74",
        "66",
        "80",
    ],
    "contact": [
        "Mom",
        "Dad",
        "John",
        "Sarah",
        "the office",
        "Mike",
        "Emily",
        "Doctor Smith",
        "Alice",
        "Bob",
    ],
    "phone_number": [
        "555-1234",
        "555-0100",
        "911",
        "555-6789",
        "555-4321",
        "1-800-555-0199",
        "555-0042",
        "555-8888",
        "555-2468",
        "555-1357",
    ],
    "duration": [
        "5 minutes",
        "10 minutes",
        "15 minutes",
        "30 minutes",
        "1 hour",
        "2 minutes",
        "45 minutes",
        "20 minutes",
        "3 minutes",
        "90 seconds",
    ],
    "task": [
        "pick up groceries",
        "call the dentist",
        "charge the car",
        "take the medication",
        "check the mail",
        "walk the dog",
        "submit the report",
        "water the plants",
        "pay the electricity bill",
        "book a table",
    ],
    "time": [
        "3 PM",
        "5 PM",
        "noon",
        "8 AM",
        "tomorrow morning",
        "6 PM",
        "in an hour",
        "9 AM",
        "7 PM",
        "4:30 PM",
    ],
}

# ---------------------------------------------------------------------------
# Intent / action mapping for each category
# ---------------------------------------------------------------------------

_CATEGORY_INTENT: dict[str, str] = {
    "navigation": "navigation",
    "media": "media_control",
    "climate": "climate_control",
    "phone": "phone",
    "general": "general",
}

_TEMPLATE_ACTION: dict[str, str] = {
    "Navigate to {destination}": "navigate",
    "How far is {destination}": "distance_query",
    "Find the nearest {poi_type}": "poi_search",
    "Take me to {destination}": "navigate",
    "What's the fastest route to {destination}": "route_query",
    "Play {song} by {artist}": "play_music",
    "Turn up the volume": "volume_up",
    "Skip this song": "skip_track",
    "Play my {playlist} playlist": "play_playlist",
    "What song is this": "identify_song",
    "Set temperature to {temp} degrees": "set_temperature",
    "Turn on the AC": "ac_on",
    "Turn off the heater": "heater_off",
    "Make it warmer": "increase_temp",
    "Make it cooler": "decrease_temp",
    "Call {contact}": "call_contact",
    "Read my messages": "read_messages",
    "Send a text to {contact}": "send_text",
    "Answer the call": "answer_call",
    "Dial {phone_number}": "dial_number",
    "What's the weather like": "weather_query",
    "Set a timer for {duration}": "set_timer",
    "What time is it": "time_query",
    "Remind me to {task} at {time}": "set_reminder",
    "Tell me a joke": "tell_joke",
}


def _fill_template(template: str) -> str:
    """Replace all ``{placeholder}`` tokens with randomly chosen values."""
    result = template
    # Keep replacing until no placeholders remain (handles multiple in one template).
    while "{" in result:
        start = result.index("{")
        end = result.index("}", start)
        key = result[start + 1 : end]
        values = TEMPLATE_VALUES.get(key)
        if values is None:
            break
        result = result[:start] + random.choice(values) + result[end + 1 :]
    return result


def expand_templates(
    category: str,
    count: int,
) -> list[tuple[str, str, str]]:
    """Generate *count* filled command strings for *category*.

    Returns a list of ``(text, expected_intent, expected_action)`` tuples.
    Templates are cycled if *count* exceeds the number of templates in the
    category.
    """
    templates = COMMAND_TEMPLATES.get(category)
    if templates is None:
        raise ValueError(f"Unknown category: {category!r}")

    intent = _CATEGORY_INTENT[category]
    results: list[tuple[str, str, str]] = []

    for i in range(count):
        template = templates[i % len(templates)]
        text = _fill_template(template)
        action = _TEMPLATE_ACTION.get(template, "unknown")
        results.append((text, intent, action))

    return results
