import streamlit as st

st.set_page_config(page_title="RoRo Yield Optimizer", page_icon="🚢", layout="wide")

from app import game_view, lab_view, reveal_view  # noqa: E402
from app.state import get_stage, set_stage  # noqa: E402

STEPS = {"game": "① Play", "reveal": "② Reveal", "lab": "③ Lab"}

st.title("🚢 RoRo Yield Optimizer")
st.markdown(
    "**Can you load a Ro-Ro ferry better than an algorithm?** Ferry space is perishable: once the ship sails, "
    "an empty lane-metre is lost revenue. Play the booking planner, then see what a MILP optimizer would have done."
)
st.caption("Synthetic but realistic data — not DFDS data.")

stage = get_stage()
nav = st.columns([4, 1])
nav[0].markdown(" → ".join(f"**{label}**" if key == stage else label for key, label in STEPS.items()))
if stage == "game":
    nav[1].button("Skip to the Lab", key="skip_to_lab", type="tertiary", on_click=set_stage, args=("lab",))
elif stage == "lab":
    nav[1].button("← Back to the game", key="back_to_game", type="tertiary", on_click=set_stage, args=("game",))
st.divider()

{"game": game_view, "reveal": reveal_view, "lab": lab_view}[stage].render()
