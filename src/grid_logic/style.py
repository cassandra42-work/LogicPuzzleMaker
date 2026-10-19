APP_NAME = "Grid Logic Puzzle Maker"

CATEGORY_COLORS = [
    "#FFF3B0",  #yellow
    "#FAD1EE",  #pink
    "#C9EEF7",  #blue
    "#CDEBC8",  #green
    "#FDDBB4",  #orange
    "#E0D6F5",  #lavender
]

MARK_COLORS = {
    "X": "#B3261E",  #red
    "O": "#1E7B34",  #green
}


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    red = int(color[1:3], 16) / 255
    green = int(color[3:5], 16) / 255
    blue = int(color[5:7], 16) / 255
    return (red, green, blue)

def category_color(index: int) -> str:
    return CATEGORY_COLORS[index % len(CATEGORY_COLORS)]
