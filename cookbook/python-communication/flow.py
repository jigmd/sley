from nodes import count_words, read_text, show_stats
from sley import Flow


def build_flow() -> Flow:
    read_text.link(count_words, "count")
    count_words.link(show_stats, "show")
    show_stats.link(read_text, "continue")
    return Flow(read_text)


word_counter = build_flow()
